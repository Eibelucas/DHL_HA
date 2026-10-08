"""Tests for DHL response parsing."""
from custom_components.dhl_mail_tracker.dhl_api import parse_response

SAMPLE = {
    "shipments": [
        {
            "id": "00340434721045331774",
            "service": "parcel-de",
            "status": {
                "timestamp": "2026-10-07T07:45:00+02:00",
                "location": {"address": {"addressLocality": "Mönchengladbach"}},
                "statusCode": "transit",
                "status": "In Zustellung",
                "description": "Die Sendung wurde in das Zustellfahrzeug geladen.",
            },
            "estimatedTimeOfDelivery": "2026-10-07T12:00:00+02:00",
            "estimatedDeliveryTimeFrame": {
                "estimatedFrom": "2026-10-07T10:00:00+02:00",
                "estimatedThrough": "2026-10-07T14:00:00+02:00",
            },
            "events": [
                {
                    "timestamp": "2026-10-07T07:45:00+02:00",
                    "location": {"address": {"addressLocality": "Mönchengladbach"}},
                    "description": "Die Sendung wurde in das Zustellfahrzeug geladen.",
                }
            ],
        }
    ]
}


def test_parse_transit():
    info = parse_response(SAMPLE)
    assert info.found
    assert info.status_code == "transit"
    assert info.location == "Mönchengladbach"
    assert info.estimated_delivery.hour == 12
    assert info.estimated_from.hour == 10
    assert info.events[0]["location"] == "Mönchengladbach"


def test_parse_empty():
    assert not parse_response({}).found


def test_unknown_status_code_maps_to_unknown():
    data = {"shipments": [{"status": {"statusCode": "weird"}}]}
    assert parse_response(data).status_code == "unknown"
