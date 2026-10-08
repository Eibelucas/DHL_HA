"""Sensors: one per parcel plus a summary."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import DhlConfigEntry
from .const import DOMAIN, STATUS_DELIVERED, STATUS_UNKNOWN, STATUSES
from .coordinator import DhlMailCoordinator, Shipment

PARALLEL_UPDATES = 0

TRACKING_URL = "https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?piececode={}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DhlConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors and keep the parcel list in sync."""
    coordinator = entry.runtime_data
    known: dict[str, ParcelSensor] = {}
    registry = er.async_get(hass)

    async_add_entities([ParcelSummarySensor(coordinator)])

    @callback
    def sync() -> None:
        current = set(coordinator.data or {})
        new = [ParcelSensor(coordinator, n) for n in current - set(known)]
        for sensor in new:
            known[sensor.tracking_number] = sensor
        if new:
            async_add_entities(new)
        for number in set(known) - current:
            sensor = known.pop(number)
            if sensor.entity_id and registry.async_get(sensor.entity_id):
                registry.async_remove(sensor.entity_id)

    # Drop registry leftovers of parcels that are gone since the last run.
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.unique_id.startswith(f"{entry.entry_id}_parcel_"):
            number = reg_entry.unique_id.removeprefix(f"{entry.entry_id}_parcel_")
            if number not in (coordinator.data or {}):
                registry.async_remove(reg_entry.entity_id)

    sync()
    entry.async_on_unload(coordinator.async_add_listener(sync))


class _Base(CoordinatorEntity[DhlMailCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DhlMailCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="DHL Pakete",
            manufacturer="DHL Mail Tracker",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html",
        )


class ParcelSummarySensor(_Base, SensorEntity):
    """Number of parcels on their way."""

    _attr_translation_key = "summary"
    _attr_icon = "mdi:truck-delivery"
    _attr_native_unit_of_measurement = "Pakete"

    def __init__(self, coordinator: DhlMailCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_summary"

    def _open(self) -> list[Shipment]:
        return [
            s
            for s in (self.coordinator.data or {}).values()
            if not s.delivered_at
        ]

    @property
    def native_value(self) -> int:
        return len(self._open())

    def _delivering_today(self) -> int:
        today = dt_util.now().date()
        count = 0
        for ship in self._open():
            info = ship.tracking
            if not info:
                continue
            eta = info.estimated_delivery or info.estimated_from
            if eta and dt_util.as_local(eta).date() == today:
                count += 1
        return count

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        parcels = []
        for ship in (self.coordinator.data or {}).values():
            info = ship.tracking
            parcels.append(
                {
                    "tracking_number": ship.tracking_number,
                    "name": ship.title,
                    "status": info.status_code if info else STATUS_UNKNOWN,
                    "description": info.description if info else None,
                    "estimated_delivery": (
                        info.estimated_delivery.isoformat()
                        if info and info.estimated_delivery
                        else None
                    ),
                    "url": TRACKING_URL.format(ship.tracking_number),
                }
            )
        return {
            "parcels": parcels,
            "delivering_today": self._delivering_today(),
            "last_mail_scan": (
                self.coordinator.last_mail_scan.isoformat()
                if self.coordinator.last_mail_scan
                else None
            ),
            "last_error": self.coordinator.last_error,
        }


class ParcelSensor(_Base, SensorEntity):
    """Status of one parcel."""

    _attr_translation_key = "parcel"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES

    def __init__(self, coordinator: DhlMailCoordinator, tracking_number: str) -> None:
        super().__init__(coordinator)
        self.tracking_number = tracking_number
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_parcel_{tracking_number}"
        self._attr_translation_placeholders = {"name": self._ship.title if self._ship else tracking_number}

    @property
    def _ship(self) -> Shipment | None:
        return (self.coordinator.data or {}).get(self.tracking_number)

    @property
    def available(self) -> bool:
        return super().available and self._ship is not None

    @property
    def native_value(self) -> str:
        ship = self._ship
        info = ship.tracking if ship else None
        return info.status_code if info else STATUS_UNKNOWN

    @property
    def icon(self) -> str:
        return {
            "pre-transit": "mdi:package-variant",
            "transit": "mdi:truck-delivery",
            STATUS_DELIVERED: "mdi:package-variant-closed-check",
            "failure": "mdi:package-variant-remove",
        }.get(self.native_value, "mdi:package-variant-closed")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ship = self._ship
        if ship is None:
            return {}
        info = ship.tracking
        attrs: dict[str, Any] = {
            "tracking_number": ship.tracking_number,
            "sender": ship.sender,
            "mail_subject": ship.subject,
            "source": ship.source,
            "url": TRACKING_URL.format(ship.tracking_number),
            "known_to_dhl": bool(info and info.found),
        }
        if info:
            attrs.update(
                {
                    "status_text": info.status_text,
                    "description": info.description,
                    "location": info.location,
                    "last_update": info.last_update.isoformat() if info.last_update else None,
                    "estimated_delivery": (
                        info.estimated_delivery.isoformat() if info.estimated_delivery else None
                    ),
                    "estimated_from": info.estimated_from.isoformat() if info.estimated_from else None,
                    "estimated_through": (
                        info.estimated_through.isoformat() if info.estimated_through else None
                    ),
                    "events": info.events,
                }
            )
        if ship.delivered_at:
            attrs["delivered_at"] = ship.delivered_at
        return attrs
