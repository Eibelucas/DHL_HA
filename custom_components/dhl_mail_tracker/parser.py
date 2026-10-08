"""Extract DHL tracking numbers from e-mails.

This module is pure Python (no Home Assistant imports) so it can be tested
and reused on its own.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import parseaddr

# Query parameters DHL uses in tracking links.
_URL_PARAM_RE = re.compile(
    r"(?i)[?&](?:piececode|idc|tracking-?id|trackingnumber|tracking-number|"
    r"submit_parcelno|parcelno)=([A-Z0-9]{10,35})"
)

# Number formats DHL Paket / Warenpost / DHL eCommerce use.
_NUMBER_PATTERNS = (
    r"JJD\d{16,24}",  # DHL Paket JJD...
    r"00340\d{15}",  # SSCC / NVE (most common in Germany)
    r"[A-Z]{2}\d{9}DE",  # UPU S10, e.g. Warenpost international
    r"\d{12}",  # classic 12 digit DHL Paket number
    r"\d{14}",
    r"\d{20}",
)
_NUMBER_RE = re.compile(r"\b(" + "|".join(_NUMBER_PATTERNS) + r")\b")

# Number must follow one of these labels to count when it is not in a link.
_LABEL_RE = re.compile(
    r"(?i)(sendungsnummer|sendungs-nr\.?|paketnummer|paket-nr\.?|"
    r"trackingnummer|tracking-nummer|tracking number|tracking id|"
    r"sendungsverfolgungsnummer|shipment number|piece code|"
    r"nummer\s+ihrer\s+sendung)"
)
_LABEL_WINDOW = 80

_DHL_HINT_RE = re.compile(r"(?i)\bdhl\b|dhl\.de|dhl\.com")

# Mails that mention DHL but never carry a parcel for the user.
_IGNORE_SUBJECT_RE = re.compile(r"(?i)anmeldecode|login|passwort|newsletter")

_TAG_RE = re.compile(r"<[^>]+>")
_STYLE_RE = re.compile(r"(?is)<(style|script)[^>]*>.*?</\1>")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class FoundShipment:
    """A tracking number found in a mail."""

    tracking_number: str
    sender: str
    subject: str


def _bodies(msg: EmailMessage) -> tuple[str, str]:
    """Return (raw_html_and_text, visible_text) of a message."""
    raw_parts: list[str] = []
    text_parts: list[str] = []
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        try:
            content = part.get_content()
        except (LookupError, UnicodeError, AssertionError):
            payload = part.get_payload(decode=True) or b""
            content = payload.decode("utf-8", "replace")
        raw_parts.append(content)
        if ctype == "text/html":
            content = _STYLE_RE.sub(" ", content)
            content = _TAG_RE.sub(" ", content)
            content = html.unescape(content)
        text_parts.append(content)
    return "\n".join(raw_parts), _WS_RE.sub(" ", "\n".join(text_parts))


def _valid(number: str) -> bool:
    """Reject obvious junk such as 111111111111."""
    if len(set(number)) <= 2:
        return False
    if number.isdigit() and len(number) == 14 and number.startswith("20"):
        # Looks like a timestamp (YYYYMMDDhhmmss).
        return False
    return True


def extract_tracking_numbers(subject: str, sender: str, raw: str, text: str) -> list[str]:
    """Return DHL tracking numbers found in a mail, in order of appearance."""
    if _IGNORE_SUBJECT_RE.search(subject or ""):
        return []
    haystack = f"{sender}\n{subject}\n{raw}"
    if not _DHL_HINT_RE.search(haystack):
        return []

    found: list[str] = []

    def add(number: str) -> None:
        number = number.upper()
        if _valid(number) and number not in found:
            found.append(number)

    # 1. Numbers inside DHL tracking links: highest confidence.
    for match in _URL_PARAM_RE.finditer(html.unescape(raw)):
        candidate = match.group(1)
        if _NUMBER_RE.fullmatch(candidate):
            add(candidate)

    # 2. Numbers right after a label like "Sendungsnummer:".
    for label in _LABEL_RE.finditer(text):
        window = text[label.end() : label.end() + _LABEL_WINDOW]
        number = _NUMBER_RE.search(window)
        if number:
            add(number.group(1))

    # 3. Unmistakable formats anywhere in the visible text.
    for match in re.finditer(r"\b(JJD\d{16,24}|00340\d{15})\b", text):
        add(match.group(1))

    return found


def parse_message(data: bytes) -> list[FoundShipment]:
    """Parse a raw RFC822 message and return the shipments in it."""
    msg = message_from_bytes(data, policy=policy.default)
    subject = str(msg.get("Subject", "") or "")
    name, addr = parseaddr(str(msg.get("From", "") or ""))
    sender = name or addr
    raw, text = _bodies(msg)  # type: ignore[arg-type]
    return [
        FoundShipment(number, sender, subject)
        for number in extract_tracking_numbers(subject, f"{name} {addr}", raw, text)
    ]
