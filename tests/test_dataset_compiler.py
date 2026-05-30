"""Tests for evidence compilation and estimator data gates."""

from __future__ import annotations

from dataset_compiler import compile_evidence_dataset, passes_estimation_gates


def test_compiler_builds_empirical_panel_with_provenance(
    patch_graph,
    patch_evidence,
):
    """Empirical evidence should compile into complete treatment/outcome rows."""

    compilation = compile_evidence_dataset(patch_graph, patch_evidence)
    profile = compilation.profile

    assert profile.data_mode == "empirical"
    assert profile.n_rows == 80
    assert profile.treated_count == 40
    assert profile.control_count == 40
    assert profile.treatment == "Patch_Applied"
    assert profile.outcome == "Lateral_Movement"
    assert profile.adjustment_set == ["Asset_Criticality"]
    assert profile.missingness == {
        "Patch_Applied": 0.0,
        "Lateral_Movement": 0.0,
        "Asset_Criticality": 0.0,
    }
    assert len(compilation.provenance) == 80
    assert compilation.provenance[0]["source_type"] == "siem"
    assert compilation.provenance[0]["raw_ref"] == "demo-row-000"


def test_synthetic_records_are_skipped_and_marked_simulation(
    patch_graph,
    synthetic_evidence,
):
    """Synthetic records should not become estimator rows."""

    compilation = compile_evidence_dataset(patch_graph, synthetic_evidence)
    profile = compilation.profile

    assert profile.data_mode == "synthetic_simulation"
    assert profile.n_rows == 0
    assert compilation.dataframe.empty
    assert compilation.provenance == []
    assert any("Skipped 80 synthetic" in warning for warning in profile.warnings)

    passed, warnings = passes_estimation_gates(profile, compilation.dataframe)

    assert passed is False
    assert any("Empirical data gate failed" in warning for warning in warnings)
    assert any("Minimum row gate failed" in warning for warning in warnings)


def test_no_evidence_fails_empirical_and_row_count_gates(patch_graph):
    """Empty evidence should be explicit insufficient data, not silent success."""

    compilation = compile_evidence_dataset(patch_graph, [])
    passed, warnings = passes_estimation_gates(
        compilation.profile,
        compilation.dataframe,
    )

    assert compilation.profile.data_mode == "insufficient_data"
    assert compilation.profile.n_rows == 0
    assert compilation.profile.treated_count == 0
    assert compilation.profile.control_count == 0
    assert compilation.provenance == []
    assert passed is False
    assert any("Empirical data gate failed" in warning for warning in warnings)
    assert any("Minimum row gate failed" in warning for warning in warnings)


def test_under_minimum_rows_fails_hard_gate(patch_graph, patch_evidence):
    """The 50-row minimum is an explicit gate, not just documentation."""

    compilation = compile_evidence_dataset(patch_graph, patch_evidence[:40])
    passed, warnings = passes_estimation_gates(
        compilation.profile,
        compilation.dataframe,
    )

    assert compilation.profile.data_mode == "empirical"
    assert compilation.profile.n_rows == 40
    assert passed is False
    assert any("Minimum row gate failed" in warning for warning in warnings)


def test_no_treatment_variation_fails_gate(patch_graph, patch_evidence):
    """A panel with no treatment variation must not produce ATE."""

    all_treated = []
    for record in patch_evidence:
        copy = dict(record)
        copy["extracted_fields"] = {
            **record["extracted_fields"],
            "Patch_Applied": 1,
        }
        all_treated.append(copy)

    compilation = compile_evidence_dataset(patch_graph, all_treated)
    passed, warnings = passes_estimation_gates(
        compilation.profile,
        compilation.dataframe,
    )

    assert compilation.profile.treated_count == 80
    assert compilation.profile.control_count == 0
    assert passed is False
    assert any("Treatment variation gate failed" in warning for warning in warnings)
    assert any("Treatment balance gate failed" in warning for warning in warnings)


def test_no_outcome_variation_fails_gate(patch_graph, patch_evidence):
    """A panel with a constant outcome must not produce ATE."""

    constant_outcome = []
    for record in patch_evidence:
        copy = dict(record)
        copy["extracted_fields"] = {
            **record["extracted_fields"],
            "Lateral_Movement": 0,
        }
        constant_outcome.append(copy)

    compilation = compile_evidence_dataset(patch_graph, constant_outcome)
    passed, warnings = passes_estimation_gates(
        compilation.profile,
        compilation.dataframe,
    )

    assert compilation.profile.data_mode == "empirical"
    assert compilation.profile.n_rows == 80
    assert passed is False
    assert any("Outcome variation gate failed" in warning for warning in warnings)
