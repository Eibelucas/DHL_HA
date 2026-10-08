"""End-to-end setup test with IMAP and DHL mocked."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dhl_mail_tracker.const import DOMAIN
from custom_components.dhl_mail_tracker.dhl_api import TrackingInfo
from custom_components.dhl_mail_tracker.parser import FoundShipment

DATA = {
    "username": "me@example.com",
    "password": "pw",
    "api_key": "key",
    "imap_server": "imap.example.com",
    "imap_port": 993,
    "folder": "INBOX",
}

FETCH = "custom_components.dhl_mail_tracker.coordinator.fetch_shipments"
TRACK = "custom_components.dhl_mail_tracker.coordinator.DhlClient.track"


async def test_parcel_from_mail_becomes_sensor(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id="me@example.com", title="me@example.com")
    entry.add_to_hass(hass)
    found = [FoundShipment("00340434721045331774", "Thalia Bücher GmbH", "Ihre Lieferung")]
    info = TrackingInfo(
        found=True,
        status_code="transit",
        status_text="In Zustellung",
        description="Im Zustellfahrzeug",
        last_update=datetime(2026, 10, 7, 5, 45, tzinfo=timezone.utc),
    )
    with patch(FETCH, return_value=(found, {"1:10"})), patch(TRACK, new=AsyncMock(return_value=info)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    summary = [s for s in hass.states.async_all("sensor") if s.attributes.get("parcels") is not None]
    assert len(summary) == 1
    assert summary[0].state == "1"

    parcels = [s for s in hass.states.async_all("sensor") if s.attributes.get("tracking_number")]
    assert len(parcels) == 1
    assert parcels[0].state == "transit"
    assert parcels[0].attributes["sender"] == "Thalia Bücher GmbH"

    # Removing via service drops the sensor and keeps it from coming back.
    with patch(FETCH, return_value=(found, set())), patch(TRACK, new=AsyncMock(return_value=info)):
        await hass.services.async_call(
            DOMAIN, "remove_tracking_number", {"tracking_number": "00340434721045331774"}, blocking=True
        )
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert "00340434721045331774" not in coordinator.data


async def test_delivered_parcel_is_cleaned_up(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id="me@example.com", options={"keep_delivered_hours": 0})
    entry.add_to_hass(hass)
    found = [FoundShipment("00340435087825295346", "Thalia", "Lieferung")]
    info = TrackingInfo(found=True, status_code="delivered", last_update=datetime(2026, 6, 1, tzinfo=timezone.utc))
    with patch(FETCH, return_value=(found, {"1:5"})), patch(TRACK, new=AsyncMock(return_value=info)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.runtime_data.data == {}
