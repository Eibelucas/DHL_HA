"""Small async client for the DHL Shipment Tracking - Unified API."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import aiohttp

from .const import DHL_API_URL, STATUS_UNKNOWN, STATUSES

_LOGGER = logging.getLogger(__name__)


class DhlApiError(Exception):
    """Generic API failure."""


class DhlAuthError(DhlApiError):
    """API key rejected."""


class DhlRateLimitError(DhlApiError):
    """Daily or per second quota reached."""


@dataclass
class TrackingInfo:
    """What DHL knows about one parcel."""

    found: bool
    status_code: str = STATUS_UNKNOWN
    status_text: str | None = None
    description: str | None = None
    last_update: datetime | None = None
    location: str | None = None
    estimated_delivery: datetime | None = None
    estimated_from: datetime | None = None
    estimated_through: datetime | None = None
    events: list[dict[str, Any]] = field(default_factory=list)


def _dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _location(obj: dict[str, Any] | None) -> str | None:
    if not obj:
        return None
    address = (obj.get("location") or {}).get("address") or {}
    return address.get("addressLocality")


def parse_response(payload: dict[str, Any]) -> TrackingInfo:
    """Turn DHL's JSON into TrackingInfo."""
    shipments = payload.get("shipments") or []
    if not shipments:
        return TrackingInfo(found=False)
    ship = shipments[0]
    status = ship.get("status") or {}
    code = status.get("statusCode") or STATUS_UNKNOWN
    if code not in STATUSES:
        code = STATUS_UNKNOWN
    frame = ship.get("estimatedDeliveryTimeFrame") or {}
    events = [
        {
            "time": ev.get("timestamp"),
            "location": _location(ev),
            "description": ev.get("description") or ev.get("status"),
        }
        for ev in (ship.get("events") or [])[:10]
    ]
    return TrackingInfo(
        found=True,
        status_code=code,
        status_text=status.get("status"),
        description=status.get("description"),
        last_update=_dt(status.get("timestamp")),
        location=_location(status),
        estimated_delivery=_dt(ship.get("estimatedTimeOfDelivery")),
        estimated_from=_dt(frame.get("estimatedFrom")),
        estimated_through=_dt(frame.get("estimatedThrough")),
        events=events,
    )


class DhlClient:
    """DHL tracking API client."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str, language: str = "de") -> None:
        self._session = session
        self._api_key = api_key
        self._language = language
        self._lock = asyncio.Lock()

    async def track(self, tracking_number: str) -> TrackingInfo:
        """Return the tracking info for one number."""
        params = {"trackingNumber": tracking_number, "language": self._language}
        headers = {"DHL-API-Key": self._api_key, "Accept": "application/json"}
        # The free plan allows one call per second at most; serialize calls.
        async with self._lock:
            try:
                async with self._session.get(
                    DHL_API_URL,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status == 404:
                        return TrackingInfo(found=False)
                    if resp.status in (401, 403):
                        raise DhlAuthError("DHL API key rejected")
                    if resp.status == 429:
                        raise DhlRateLimitError("DHL API quota reached")
                    if resp.status >= 400:
                        raise DhlApiError(f"DHL API returned HTTP {resp.status}")
                    payload = await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise DhlApiError(f"Cannot reach DHL API: {err}") from err
            finally:
                await asyncio.sleep(1.1)
        return parse_response(payload)

    async def validate(self) -> None:
        """Raise DhlAuthError when the key is bad. An unknown number is fine."""
        await self.track("00340434721045331774")
