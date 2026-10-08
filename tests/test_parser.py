"""Parser tests with synthetic mails modelled on real shop and DHL mails."""
from email.message import EmailMessage

from custom_components.dhl_mail_tracker.parser import parse_message


def _mail(sender: str, subject: str, html: str | None = None, text: str | None = None) -> bytes:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "me@example.com"
    msg["Subject"] = subject
    msg.set_content(text or "Bitte HTML aktivieren.")
    if html:
        msg.add_alternative(html, subtype="html")
    return bytes(msg)


def numbers(data: bytes) -> list[str]:
    return [s.tracking_number for s in parse_message(data)]


def test_dhl_notification_piececode_link():
    html = """
    <style>.a{width:111111111111px} .b{line-height:66666666666667%}</style>
    <p>Ihre Sendung ist unterwegs</p>
    <a href="https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?lang=de&amp;piececode=00340435073630130811&amp;utm=x">Live verfolgen</a>
    <img src="https://t.dhl.de/p.gif?ts=20260325101745">
    """
    data = _mail("DHL Paket <noreply@dhl.de>", "Ihre Shop Sendung ist unterwegs", html)
    assert numbers(data) == ["00340435073630130811"]


def test_shop_mail_with_label_ignores_isbn_and_order_number():
    html = """
    <p>Auftrag 1443667417</p>
    <p>Das Kochbuch der Apothekerin, ISBN 9783745934649</p>
    <p class="middlepos">Sendungsnummer: 00340434721045331774</p><br/>
    <p>https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?lang=de&idc=00340434721045331774</p>
    """
    data = _mail("Thalia Bücher GmbH <info@thalia.de>", "Ihre Lieferung zu Auftrag 1443667417", html)
    assert numbers(data) == ["00340434721045331774"]


def test_plain_text_versandmeldung_with_paketnummer():
    text = "Ihr Paket wurde an DHL übergeben. Ihre Paketnummer lautet: 123456789012\nDanke!"
    data = _mail("Shop Versand <info@shop.de>", "Versandmeldung", text=text)
    assert numbers(data) == ["123456789012"]


def test_jjd_number_anywhere():
    text = "DHL Sendung JJD000390012345678901 ist auf dem Weg."
    data = _mail("Shop <info@shop.de>", "Versand", text=text)
    assert numbers(data) == ["JJD000390012345678901"]


def test_warenpost_international():
    text = "Versand mit DHL Warenpost. Sendungsnummer: LX123456785DE"
    data = _mail("Shop <info@shop.de>", "Versand", text=text)
    assert numbers(data) == ["LX123456785DE"]


def test_newsletter_without_number_is_ignored():
    html = "<p>DHL feiert den Pride Month! Gutschein 123456789012345</p>"
    assert numbers(_mail("DHL Paket <paket@dhl.de>", "Liebe gewinnt!", html)) == []


def test_login_code_mail_is_ignored():
    text = "Ihr DHL Anmeldecode: 914180. Sendungsnummer: 00340434721045331774"
    assert numbers(_mail("DHL Login <noreply@dhl.de>", "Anmeldecode für DHL: 914180", text=text)) == []


def test_mail_without_dhl_is_ignored():
    text = "Sendungsnummer: 00340434721045331774 (Hermes)"
    assert numbers(_mail("Shop <info@shop.de>", "Versand mit Hermes", text=text)) == []


def test_bare_long_number_without_label_is_ignored():
    text = "DHL Bestellung 12345678901234567890 erhalten"
    assert numbers(_mail("Shop <info@shop.de>", "Bestellung", text=text)) == []


def test_duplicates_collapsed_and_sender_kept():
    html = (
        '<a href="https://dhl.de/x?piececode=00340434316083713677">a</a>'
        '<a href="https://dhl.de/x?idc=00340434316083713677">b</a>'
        "Paketnummer lautet: 00340434316083713677"
    )
    result = parse_message(_mail("ipc-computer.de Versand <info@ipc.de>", "Versandmeldung", html))
    assert [s.tracking_number for s in result] == ["00340434316083713677"]
    assert result[0].sender == "ipc-computer.de Versand"
