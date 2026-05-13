"""Deterministic evidence fixtures for demos and smoke tests.

The fixture in this module is intentionally boring in the best possible way:
it provides a small, repeatable empirical panel where a patch intervention is
associated with reduced lateral movement while adjusting for asset criticality.
It exercises the same compiler, gatekeeper, DoWhy, statsmodels, and refuter
path that real evidence records use.
"""

from __future__ import annotations

from typing import Any


def patch_lateral_movement_graph() -> dict[str, Any]:
    """Return a measurable graph for the built-in evidence-backed demo."""

    return {
        "nodes": [
            {
                "id": "Patch_Applied",
                "label": "Patch Applied",
                "description": "Whether the vulnerable asset was patched.",
            },
            {
                "id": "Lateral_Movement",
                "label": "Lateral Movement",
                "description": "Whether downstream lateral movement was observed.",
            },
            {
                "id": "Asset_Criticality",
                "label": "Asset Criticality",
                "description": "Whether the asset belongs to a high-value tier.",
            },
        ],
        "edges": [
            {
                "source": "Asset_Criticality",
                "target": "Patch_Applied",
                "relationship": "Critical assets are prioritized for patching.",
                "required_evidence": ["asset inventory priority tier"],
                "falsification_tests": ["patch timing unrelated to priority"],
            },
            {
                "source": "Asset_Criticality",
                "target": "Lateral_Movement",
                "relationship": "Critical assets attract more adversary movement.",
                "required_evidence": ["EDR lateral movement alerts by tier"],
                "falsification_tests": ["equal movement rate across tiers"],
            },
            {
                "source": "Patch_Applied",
                "target": "Lateral_Movement",
                "relationship": "Patching reduces exploitability and movement.",
                "required_evidence": ["patch status before movement window"],
                "falsification_tests": ["movement started before patch opportunity"],
            },
        ],
        "treatment_variable": "Patch_Applied",
        "outcome_variable": "Lateral_Movement",
        "candidate_confounders": ["Asset_Criticality"],
    }


def patch_lateral_movement_evidence(n_rows: int = 80) -> list[dict[str, Any]]:
    """Return deterministic SIEM-style evidence records for demo estimation."""

    records: list[dict[str, Any]] = []
    for index in range(n_rows):
        treated = 1 if index % 2 == 0 else 0
        critical = 1 if index % 5 == 0 else 0
        outcome = int(
            (not treated and index % 3 == 0)
            or (critical and index % 7 == 0)
        )
        records.append(
            {
                "source_type": "siem",
                "source_name": "demo-sentinel-export",
                "observed_at": f"2026-05-12T{index % 24:02d}:00:00Z",
                "asset_id": f"host-{index:03d}",
                "event_type": "compiled_observation",
                "raw_ref": f"demo-row-{index:03d}",
                "extracted_fields": {
                    "Patch_Applied": treated,
                    "Lateral_Movement": outcome,
                    "Asset_Criticality": critical,
                },
                "confidence": 1.0,
            }
        )
    return records
