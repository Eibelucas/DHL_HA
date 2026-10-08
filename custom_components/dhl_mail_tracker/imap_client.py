"""Blocking IMAP access. Always run these functions in an executor."""
from __future__ import annotations

import imaplib
import logging
import ssl
from datetime import date, timedelta

from .parser import FoundShipment, parse_message

_LOGGER = logging.getLogger(__name__)

_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


class ImapError(Exception):
    """Could not talk to the IMAP server."""


class ImapAuthError(ImapError):
    """Login refused."""


def _imap_date(day: date) -> str:
    return f"{day.day:02d}-{_MONTHS[day.month - 1]}-{day.year}"


def _connect(server: str, port: int, username: str, password: str) -> imaplib.IMAP4_SSL:
    try:
        conn = imaplib.IMAP4_SSL(server, port, ssl_context=ssl.create_default_context(), timeout=30)
    except (OSError, imaplib.IMAP4.error) as err:
        raise ImapError(f"Cannot connect to {server}:{port}: {err}") from err
    try:
        conn.login(username, password)
    except imaplib.IMAP4.error as err:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
        raise ImapAuthError(str(err)) from err
    return conn


def test_login(server: str, port: int, username: str, password: str, folder: str) -> None:
    """Raise if login or folder selection fails."""
    conn = _connect(server, port, username, password)
    try:
        status, _ = conn.select(_quote(folder), readonly=True)
        if status != "OK":
            raise ImapError(f"Folder {folder} not found")
    finally:
        _logout(conn)


def _quote(folder: str) -> str:
    if folder.startswith('"'):
        return folder
    return '"' + folder.replace('"', '\\"') + '"'


def _logout(conn: imaplib.IMAP4_SSL) -> None:
    try:
        conn.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        conn.logout()
    except Exception:  # noqa: BLE001
        pass


def fetch_shipments(
    server: str,
    port: int,
    username: str,
    password: str,
    folder: str,
    days_back: int,
    seen_uids: set[str],
) -> tuple[list[FoundShipment], set[str]]:
    """Scan mails of the last days for DHL numbers.

    Only mails mentioning DHL are downloaded (server side search), and mails
    whose UID is in ``seen_uids`` are skipped. Returns the shipments found
    and the UIDs that were looked at, so the caller can remember them.
    """
    conn = _connect(server, port, username, password)
    found: list[FoundShipment] = []
    checked: set[str] = set()
    try:
        status, data = conn.select(_quote(folder), readonly=True)
        if status != "OK":
            raise ImapError(f"Folder {folder} not found")
        uidvalidity = ""
        status, resp = conn.response("UIDVALIDITY")
        if resp and resp[0]:
            uidvalidity = resp[0].decode() if isinstance(resp[0], bytes) else str(resp[0])

        since = _imap_date(date.today() - timedelta(days=days_back))
        status, data = conn.uid("search", None, "SINCE", since, "TEXT", "DHL")
        if status != "OK":
            raise ImapError(f"Search failed: {data}")
        uids = data[0].split() if data and data[0] else []
        _LOGGER.debug("IMAP search returned %d mails mentioning DHL", len(uids))

        for raw_uid in uids:
            uid = raw_uid.decode()
            key = f"{uidvalidity}:{uid}"
            if key in seen_uids:
                continue
            status, msg_data = conn.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK" or not msg_data:
                continue
            for item in msg_data:
                if isinstance(item, tuple) and len(item) == 2:
                    try:
                        found.extend(parse_message(item[1]))
                    except Exception:  # noqa: BLE001
                        _LOGGER.debug("Could not parse mail %s", uid, exc_info=True)
            checked.add(key)
    except (OSError, imaplib.IMAP4.error) as err:
        raise ImapError(str(err)) from err
    finally:
        _logout(conn)
    return found, checked
