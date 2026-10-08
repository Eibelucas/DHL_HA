"""Config flow tests."""
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.dhl_mail_tracker.const import DOMAIN
from custom_components.dhl_mail_tracker.dhl_api import DhlAuthError
from custom_components.dhl_mail_tracker.imap_client import ImapAuthError

INPUT = {
    "username": "me@example.com",
    "password": "app-password",
    "api_key": "key",
    "imap_server": "imap.example.com",
    "imap_port": 993,
    "folder": "INBOX",
}

LOGIN = "custom_components.dhl_mail_tracker.config_flow.test_login"
VALIDATE = "custom_components.dhl_mail_tracker.config_flow.DhlClient.validate"
SETUP = "custom_components.dhl_mail_tracker.async_setup_entry"


async def test_happy_path(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    with patch(LOGIN), patch(VALIDATE, new=AsyncMock()), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "me@example.com"
    assert result["data"]["api_key"] == "key"


async def test_bad_imap_password(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch(LOGIN, side_effect=ImapAuthError("nope")):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"password": "invalid_imap_auth"}


async def test_bad_api_key(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    with patch(LOGIN), patch(VALIDATE, new=AsyncMock(side_effect=DhlAuthError)):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], INPUT)
    assert result["errors"] == {"api_key": "invalid_api_key"}
