"""Config flow for DHL Mail Tracker."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

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
    DEFAULT_IMAP_PORT,
    DEFAULT_IMAP_SERVER,
    DEFAULT_KEEP_DELIVERED_HOURS,
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
    MIN_SCAN_INTERVAL_MIN,
)
from .dhl_api import DhlApiError, DhlAuthError, DhlClient
from .imap_client import ImapAuthError, ImapError, test_login

_LOGGER = logging.getLogger(__name__)

_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _user_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): TextSelector(
                TextSelectorConfig(type=TextSelectorType.EMAIL)
            ),
            vol.Required(CONF_PASSWORD): _PASSWORD,
            vol.Required(CONF_API_KEY): _PASSWORD,
            vol.Required(
                CONF_IMAP_SERVER, default=defaults.get(CONF_IMAP_SERVER, DEFAULT_IMAP_SERVER)
            ): str,
            vol.Required(
                CONF_IMAP_PORT, default=defaults.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT)
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required(CONF_FOLDER, default=defaults.get(CONF_FOLDER, DEFAULT_FOLDER)): str,
        }
    )


class DhlMailTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup."""

    VERSION = 1

    async def _validate(self, data: Mapping[str, Any]) -> dict[str, str]:
        errors: dict[str, str] = {}
        try:
            await self.hass.async_add_executor_job(
                test_login,
                data[CONF_IMAP_SERVER],
                data[CONF_IMAP_PORT],
                data[CONF_USERNAME],
                data[CONF_PASSWORD],
                data[CONF_FOLDER],
            )
        except ImapAuthError:
            errors[CONF_PASSWORD] = "invalid_imap_auth"
        except ImapError as err:
            _LOGGER.debug("IMAP check failed: %s", err)
            errors["base"] = "cannot_connect_imap"
        if errors:
            return errors
        client = DhlClient(async_get_clientsession(self.hass), data[CONF_API_KEY])
        try:
            await client.validate()
        except DhlAuthError:
            errors[CONF_API_KEY] = "invalid_api_key"
        except DhlApiError as err:
            _LOGGER.debug("DHL check failed: %s", err)
            errors["base"] = "cannot_connect_dhl"
        return errors

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_USERNAME] = user_input[CONF_USERNAME].strip()
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()
            errors = await self._validate(user_input)
            if not errors:
                return self.async_create_entry(title=user_input[CONF_USERNAME], data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(_user_schema(user_input or {}), user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            errors = await self._validate(data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): _PASSWORD,
                    vol.Required(CONF_API_KEY, default=entry.data.get(CONF_API_KEY, "")): _PASSWORD,
                }
            ),
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DhlMailTrackerOptionsFlow()


class DhlMailTrackerOptionsFlow(OptionsFlow):
    """Tweak intervals."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            for key in (CONF_SCAN_INTERVAL, CONF_DAYS_BACK, CONF_KEEP_DELIVERED_HOURS):
                user_input[key] = int(user_input[key])
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MIN),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_MIN, max=720, step=5,
                        unit_of_measurement="min", mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_DAYS_BACK, default=opts.get(CONF_DAYS_BACK, DEFAULT_DAYS_BACK)
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=90, step=1, unit_of_measurement="d", mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_KEEP_DELIVERED_HOURS,
                    default=opts.get(CONF_KEEP_DELIVERED_HOURS, DEFAULT_KEEP_DELIVERED_HOURS),
                ): NumberSelector(
                    NumberSelectorConfig(min=0, max=336, step=1, unit_of_measurement="h", mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_FOLDER,
                    default=opts.get(CONF_FOLDER, self.config_entry.data.get(CONF_FOLDER, DEFAULT_FOLDER)),
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
