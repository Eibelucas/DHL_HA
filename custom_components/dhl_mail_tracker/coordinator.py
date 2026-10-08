"""Coordinator: scans the mailbox and refreshes parcel status."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_API_KEY,
    CONF_DAYS_BACK,
    CONF_FOLDER,
    CONF_IMAP_PORT,
    CONF_IMAP_SERVER,
    CONF_KEEP_DELIVERED_HOURS,
    CONF_SCAN_INTERVAL,
    DEFAULT_DAYS_BACK,
    DEFAULT_FOLDER,
    DEFAULT_KEEP_DELIVERED_HOURS,
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
    MIN_PARCEL_REFRESH,
    STATUS_DELIVERED,
    STORAGE_VERSION,
    UNKNOWN_EXPIRY,
)
from .dhl_api import DhlApiError, DhlAuthError, DhlClient, DhlRateLimitError, TrackingInfo
from .imap_client import ImapAuthError, ImapError, fetch_shipments

_LOGGER = logging.getLogger(__name__)

MAX_SEEN_UIDS = 3000


@dataclass
class Shipment:
    """A parcel being tracked."""

    tracking_number: str
    name: str | None = None
    sender: str | None = None
    subject: str | None = None
    source: str = "mail"
    added: str = field(default_factory=lambda: dt_util.utcnow().isoformat())
    last_checked: str | None = None
    delivered_at: str | None = None
    info: dict[str, Any] | None = None

    @property
    def tracking(self) -> TrackingInfo | None:
        if self.info is None:
            return None
        data = dict(self.info)
        for key in ("last_update", "estimated_delivery", "estimated_from", "estimated_through"):
            if data.get(key):
                data[key] = datetime.fromisoformat(data[key])
        return TrackingInfo(**data)

    @property
    def title(self) -> str:
        return self.name or self.sender or self.tracking_number


def _info_to_dict(info: TrackingInfo) -> dict[str, Any]:
    data = asdict(info)
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data


class DhlMailCoordinator(DataUpdateCoordinator[dict[str, Shipment]]):
    """Keeps the list of parcels and their DHL status."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MIN)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._client = DhlClient(
            async_get_clientsession(hass),
            entry.data[CONF_API_KEY],
            language=(hass.config.language or "de")[:2],
        )
        self.shipments: dict[str, Shipment] = {}
        self._seen_uids: list[str] = []
        self._ignored: set[str] = set()
        self.last_mail_scan: datetime | None = None
        self.last_error: str | None = None

    # ---------------------------------------------------------------- storage
    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.shipments = {
            num: Shipment(**raw) for num, raw in (data.get("shipments") or {}).items()
        }
        self._seen_uids = list(data.get("seen_uids") or [])
        self._ignored = set(data.get("ignored") or [])

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "shipments": {n: asdict(s) for n, s in self.shipments.items()},
                "seen_uids": self._seen_uids[-MAX_SEEN_UIDS:],
                "ignored": sorted(self._ignored),
            }
        )

    async def async_remove_store(self) -> None:
        await self._store.async_remove()

    # ---------------------------------------------------------------- public
    async def async_add(self, number: str, name: str | None = None) -> None:
        number = number.strip().upper().replace(" ", "")
        self._ignored.discard(number)
        if number in self.shipments:
            if name:
                self.shipments[number].name = name
        else:
            self.shipments[number] = Shipment(number, name=name, source="manual")
        await self._async_save()
        await self.async_request_refresh()

    async def async_remove(self, number: str) -> None:
        number = number.strip().upper().replace(" ", "")
        self.shipments.pop(number, None)
        self._ignored.add(number)
        await self._async_save()
        self.async_set_updated_data(dict(self.shipments))

    # ---------------------------------------------------------------- update
    async def _async_update_data(self) -> dict[str, Shipment]:
        errors: list[str] = []
        await self._scan_mailbox(errors)
        await self._refresh_parcels(errors)
        self._cleanup()
        await self._async_save()
        self.last_error = "; ".join(errors) or None
        if errors and not self.shipments and self.data is None:
            raise UpdateFailed(self.last_error)
        return dict(self.shipments)

    async def _scan_mailbox(self, errors: list[str]) -> None:
        data = self.config_entry.data
        opts = self.config_entry.options
        try:
            found, checked = await self.hass.async_add_executor_job(
                fetch_shipments,
                data[CONF_IMAP_SERVER],
                data[CONF_IMAP_PORT],
                data[CONF_USERNAME],
                data[CONF_PASSWORD],
                opts.get(CONF_FOLDER, data.get(CONF_FOLDER, DEFAULT_FOLDER)),
                opts.get(CONF_DAYS_BACK, DEFAULT_DAYS_BACK),
                set(self._seen_uids),
            )
        except ImapAuthError as err:
            raise ConfigEntryAuthFailed(f"IMAP login failed: {err}") from err
        except ImapError as err:
            _LOGGER.warning("Mailbox scan failed: %s", err)
            errors.append(f"IMAP: {err}")
            return
        self.last_mail_scan = dt_util.utcnow()
        self._seen_uids.extend(sorted(checked))
        for item in found:
            if item.tracking_number in self._ignored:
                continue
            if item.tracking_number not in self.shipments:
                _LOGGER.info("New DHL parcel %s from %s", item.tracking_number, item.sender)
                self.shipments[item.tracking_number] = Shipment(
                    item.tracking_number, sender=item.sender, subject=item.subject
                )
            else:
                ship = self.shipments[item.tracking_number]
                # Prefer the shop's name over "DHL Paket".
                if ship.sender and "dhl" in ship.sender.lower() and "dhl" not in item.sender.lower():
                    ship.sender = item.sender
                    ship.subject = item.subject

    async def _refresh_parcels(self, errors: list[str]) -> None:
        now = dt_util.utcnow()
        for ship in list(self.shipments.values()):
            if ship.delivered_at:
                continue
            if ship.last_checked and now - datetime.fromisoformat(ship.last_checked) < MIN_PARCEL_REFRESH:
                continue
            try:
                info = await self._client.track(ship.tracking_number)
            except DhlAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except DhlRateLimitError as err:
                errors.append(str(err))
                _LOGGER.warning("%s, trying again next cycle", err)
                return
            except DhlApiError as err:
                errors.append(str(err))
                _LOGGER.warning("Tracking %s failed: %s", ship.tracking_number, err)
                continue
            ship.last_checked = now.isoformat()
            # Keep the last known good data when DHL temporarily forgets a parcel.
            if info.found or ship.info is None:
                ship.info = _info_to_dict(info)
            if info.status_code == STATUS_DELIVERED and not ship.delivered_at:
                ship.delivered_at = (info.last_update or now).isoformat()

    def _cleanup(self) -> None:
        now = dt_util.utcnow()
        keep = timedelta(
            hours=self.config_entry.options.get(
                CONF_KEEP_DELIVERED_HOURS, DEFAULT_KEEP_DELIVERED_HOURS
            )
        )
        for number, ship in list(self.shipments.items()):
            if ship.delivered_at and now - datetime.fromisoformat(ship.delivered_at) > keep:
                _LOGGER.info("Parcel %s delivered, removing", number)
                self.shipments.pop(number)
                self._ignored.add(number)
                continue
            info = ship.tracking
            never_found = info is None or not info.found
            if never_found and now - datetime.fromisoformat(ship.added) > UNKNOWN_EXPIRY and ship.source == "mail":
                _LOGGER.info("Parcel %s unknown to DHL for too long, removing", number)
                self.shipments.pop(number)
                self._ignored.add(number)
