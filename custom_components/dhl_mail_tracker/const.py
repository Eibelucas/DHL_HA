"""Constants for DHL Mail Tracker."""
from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "dhl_mail_tracker"

CONF_IMAP_SERVER: Final = "imap_server"
CONF_IMAP_PORT: Final = "imap_port"
CONF_FOLDER: Final = "folder"
CONF_API_KEY: Final = "api_key"
CONF_DAYS_BACK: Final = "days_back"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_KEEP_DELIVERED_HOURS: Final = "keep_delivered_hours"

DEFAULT_IMAP_SERVER: Final = "imap.gmail.com"
DEFAULT_IMAP_PORT: Final = 993
DEFAULT_FOLDER: Final = "INBOX"
DEFAULT_DAYS_BACK: Final = 14
DEFAULT_SCAN_INTERVAL_MIN: Final = 30
MIN_SCAN_INTERVAL_MIN: Final = 10
DEFAULT_KEEP_DELIVERED_HOURS: Final = 24

# DHL's free API plan allows 250 calls a day; never query one parcel more
# often than this, whatever the scan interval is.
MIN_PARCEL_REFRESH: Final = timedelta(minutes=10)
# Give up on numbers DHL never knew about after this long.
UNKNOWN_EXPIRY: Final = timedelta(days=10)

DHL_API_URL: Final = "https://api-eu.dhl.com/track/shipments"

STORAGE_VERSION: Final = 1

SERVICE_ADD: Final = "add_tracking_number"
SERVICE_REMOVE: Final = "remove_tracking_number"
SERVICE_SCAN: Final = "scan_now"
ATTR_TRACKING_NUMBER: Final = "tracking_number"
ATTR_NAME: Final = "name"

STATUS_PRE_TRANSIT: Final = "pre-transit"
STATUS_TRANSIT: Final = "transit"
STATUS_DELIVERED: Final = "delivered"
STATUS_FAILURE: Final = "failure"
STATUS_UNKNOWN: Final = "unknown"
STATUSES: Final = [
    STATUS_PRE_TRANSIT,
    STATUS_TRANSIT,
    STATUS_DELIVERED,
    STATUS_FAILURE,
    STATUS_UNKNOWN,
]
