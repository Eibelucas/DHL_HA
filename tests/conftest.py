"""Fixtures."""
import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in all tests."""
    yield


@pytest.fixture(autouse=True)
def mock_clientsession():
    """Avoid real aiohttp sessions (their DNS resolver thread trips the test harness)."""
    from unittest.mock import MagicMock, patch

    with patch(
        "custom_components.dhl_mail_tracker.config_flow.async_get_clientsession",
        return_value=MagicMock(),
    ), patch(
        "custom_components.dhl_mail_tracker.coordinator.async_get_clientsession",
        return_value=MagicMock(),
    ):
        yield
