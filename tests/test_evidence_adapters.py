"""Tests for external evidence normalization adapters."""

from __future__ import annotations

from evidence_adapters import (
    normalize_cve_records,
    normalize_incident_reports,
    normalize_sentinel_records,
)


def test_sentinel_adapter_preserves_provenance_and_measurement_fields():
    """Sentinel/SIEM exports should become evidence records with aliases."""

    records = list(
        normalize_sentinel_records(
            [
                {
                    "TimeGenerated": "2026-05-12T10:00:00Z",
                    "Computer": "host-001",
                    "AlertName": "Lateral movement detected",
                    "TechniqueId": "T1021",
                    "Severity": "High",
                    "Patch Applied": 1,
                    "Lateral_Movement": 0,
                }
            ],
            source_name="sentinel-prod-kql",
        )
    )

    record = records[0]

    assert record["source_type"] == "siem"
    assert record["source_name"] == "sentinel-prod-kql"
    assert record["asset_id"] == "host-001"
    assert record["event_type"] == "Lateral movement detected"
    assert record["technique_id"] == "T1021"
    assert record["severity"] == 8.0
    assert record["extracted_fields"]["Patch Applied"] == 1
    assert record["extracted_fields"]["Patch_Applied"] == 1


def test_cve_adapter_extracts_nested_nvd_fields():
    """NVD-style CVE records should expose CVE ID, CVSS, and description."""

    records = list(
        normalize_cve_records(
            [
                {
                    "cve": {
                        "id": "CVE-2026-0001",
                        "descriptions": [
                            {"lang": "en", "value": "Example vulnerable service."}
                        ],
                    },
                    "published": "2026-05-01",
                    "metrics": {
                        "cvssMetricV31": [
                            {"cvssData": {"baseScore": 9.1}},
                        ]
                    },
                }
            ]
        )
    )

    record = records[0]

    assert record["source_type"] == "cve"
    assert record["cve_id"] == "CVE-2026-0001"
    assert record["severity"] == 9.1
    assert record["raw_ref"] == "CVE-2026-0001"
    assert record["raw_text"] == "Example vulnerable service."


def test_incident_adapter_maps_case_management_fields():
    """Incident report exports should retain case and analyst context."""

    records = list(
        normalize_incident_reports(
            [
                {
                    "incident_id": "INC-42",
                    "created_at": "2026-05-12",
                    "asset_id": "host-001",
                    "user": "analyst@example.com",
                    "severity": "critical",
                    "summary": "Credential misuse followed by lateral movement.",
                }
            ]
        )
    )

    record = records[0]

    assert record["source_type"] == "incident_report"
    assert record["observed_at"] == "2026-05-12"
    assert record["asset_id"] == "host-001"
    assert record["user_id"] == "analyst@example.com"
    assert record["severity"] == 9.5
    assert record["raw_ref"] == "INC-42"
