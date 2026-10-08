"""DHL Mail Tracker: finds DHL parcels in your mailbox and tracks them."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_NAME,
    ATTR_TRACKING_NUMBER,
    DOMAIN,
    SERVICE_ADD,
    SERVICE_REMOVE,
    SERVICE_SCAN,
)
from .coordinator import DhlMailCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type DhlConfigEntry = ConfigEntry[DhlMailCoordinator]

_ADD_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TRACKING_NUMBER): cv.string,
        vol.Optional(ATTR_NAME): cv.string,
    }
)
_REMOVE_SCHEMA = vol.Schema({vol.Required(ATTR_TRACKING_NUMBER): cv.string})


def _coordinators(hass: HomeAssistant) -> list[DhlMailCoordinator]:
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    return [entry.runtime_data for entry in entries]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services once."""

    async def add(call: ServiceCall) -> None:
        for coord in _coordinators(hass)[:1]:
            await coord.async_add(call.data[ATTR_TRACKING_NUMBER], call.data.get(ATTR_NAME))

    async def remove(call: ServiceCall) -> None:
        for coord in _coordinators(hass):
            await coord.async_remove(call.data[ATTR_TRACKING_NUMBER])

    async def scan(call: ServiceCall) -> None:
        for coord in _coordinators(hass):
            await coord.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_ADD, add, schema=_ADD_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE, remove, schema=_REMOVE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SCAN, scan)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: DhlConfigEntry) -> bool:
    """Set up from a config entry."""
    coordinator = DhlMailCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: DhlConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: DhlConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: DhlConfigEntry) -> None:
    """Delete stored parcels when the integration is removed."""
    coordinator = DhlMailCoordinator(hass, entry)
    await coordinator.async_remove_store()
