# DHL Mail Tracker für Home Assistant

Findet DHL-Sendungsnummern automatisch in deinem Postfach (IMAP) und verfolgt die Pakete über die offizielle DHL-API. Kein Abtippen von Sendungsnummern mehr: Bestellst du bei Thalia, Amazon & Co., taucht das Paket von selbst in Home Assistant auf und verschwindet nach der Zustellung wieder.

## Features

- 📬 Scannt per IMAP nur Mails, die "DHL" enthalten (serverseitige Suche), jede Mail nur einmal
- 🔎 Erkennt Sendungsnummern aus DHL-Links (`piececode`, `idc`, ...), nach Labels wie "Sendungsnummer:" / "Paketnummer lautet:" sowie JJD- und 00340-Nummern. ISBNs, Bestellnummern, Login-Codes und Newsletter werden ignoriert
- 📦 Ein Sensor pro Paket (Angekündigt / Unterwegs / Zugestellt / Problem) mit Ort, Zeitfenster, Absender und Verlauf
- 🔢 Sensor "Pakete unterwegs" mit Liste aller Pakete und `delivering_today`
- 🧹 Zugestellte Pakete werden nach einstellbarer Zeit automatisch entfernt
- ✍️ Services: `dhl_mail_tracker.add_tracking_number`, `remove_tracking_number`, `scan_now`
- 🔐 Reauth-Flow, wenn Passwort oder API-Key nicht mehr passen
- Schont das API-Limit (250 Abfragen/Tag im Free-Plan): jedes Paket höchstens alle 10 Minuten, zugestellte gar nicht mehr

## Voraussetzungen

1. **DHL API-Key (kostenlos):** Auf [developer.dhl.com](https://developer.dhl.com) registrieren → *My Apps* → *Create App* → API **"Shipment Tracking - Unified"** hinzufügen → den **API Key** kopieren.
2. **IMAP-Zugang zum Postfach.** Bei **Gmail**: 2-Faktor-Anmeldung muss aktiv sein, dann unter [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) ein App-Passwort erstellen. Das normale Google-Passwort funktioniert nicht.

## Installation

### HACS (empfohlen)
1. HACS → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/Eibelucas/DHL_HA`, Kategorie *Integration*
2. "DHL Mail Tracker" installieren und Home Assistant neu starten
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → DHL Mail Tracker*

### Manuell
Ordner `custom_components/dhl_mail_tracker` nach `config/custom_components/` kopieren, neu starten, Integration hinzufügen.

## Einrichtung

| Feld | Beispiel |
|---|---|
| E-Mail-Adresse | `du@gmail.com` |
| Passwort / App-Passwort | Gmail-App-Passwort |
| DHL API-Key | von developer.dhl.com |
| IMAP-Server / Port | `imap.gmail.com` / `993` (GMX: `imap.gmx.net`, Web.de: `imap.web.de`, Outlook: `outlook.office365.com`) |
| Ordner | `INBOX` |

Unter *Konfigurieren* lassen sich Intervall (Standard 30 min), Suchzeitraum (14 Tage) und Anzeigedauer zugestellter Pakete (24 h) ändern.

## Beispiel-Automation

```yaml
automation:
  - alias: "Paket kommt heute"
    triggers:
      - trigger: state
        entity_id: sensor.dhl_pakete_pakete_unterwegs
        attribute: delivering_today
    conditions:
      - condition: template
        value_template: "{{ trigger.to_state.attributes.delivering_today | int(0) > 0 }}"
    actions:
      - action: notify.notify
        data:
          message: "📦 Heute kommt ein DHL-Paket!"
```

## Datenschutz

Mails werden nur lokal in Home Assistant gelesen (read-only, nichts wird als gelesen markiert). An DHL geht ausschließlich die Sendungsnummer.

## Lizenz
MIT
