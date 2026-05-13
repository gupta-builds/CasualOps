"""Execution engine for HiveMind runs.

This module is the backend boundary used by the HTTP API and the legacy
Streamlit demo. It runs the LangGraph workflow, composes a frontend-friendly
artifact, emits deterministic tier metrics, and persists the full run record.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from benchmarking import score_agent_tiers
from graph import build_graph

DATA_DIR = Path("../data")


def serialize_pydantic(obj: Any) -> Any:
    """Serialize Pydantic objects while leaving plain values untouched."""

    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj


async def run_hivemind(
    task_description: str,
    evidence_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the full HiveMind workflow and return a persisted artifact."""

    graph = build_graph()
    initial_state = {
        "task_description": task_description,
        "parent_configs": [],
        "child_configs": [],
        "memos": [],
        "ranked_strategies": [],
        "final_recommendation": None,
        "evaluator_error": None,
        "causal_payload": None,
        "dowhy_results": None,
        "causal_refutation_passed": False,
        "causal_refutation_attempts": 0,
        "evidence_records": evidence_records or [],
        "causal_dataset_profile": None,
        "causal_estimate_report": None,
    }

    final_state = await graph.ainvoke(initial_state)
    run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    DATA_DIR.mkdir(exist_ok=True)

    memos_raw = [serialize_pydantic(memo) for memo in final_state.get("memos", [])]
    strategies = [_strategy_card(i, memo) for i, memo in enumerate(memos_raw)]

    causal_payload = final_state.get("causal_payload") or {}
    causal_graph = causal_payload.get("graph", {})
    dowhy_results = final_state.get("dowhy_results") or {}
    causal_estimate_report = final_state.get("causal_estimate_report") or {}
    causal_dataset_profile = final_state.get("causal_dataset_profile") or {}
    agent_tier_metrics = score_agent_tiers(final_state)
    ate_estimate = _safe_float(dowhy_results.get("ate_estimate"), default=0.0)
    confidence = _impact_confidence(causal_estimate_report)

    artifact = {
        "run_id": run_id,
        "strategies": strategies,
        "ranked_strategies": final_state.get("ranked_strategies", []),
        "final_recommendation": final_state.get("final_recommendation"),
        "evaluator_error": final_state.get("evaluator_error"),
        "causal_graph": causal_graph,
        "impact": {
            "ate": ate_estimate,
            "confidence": confidence,
            "p_value": causal_estimate_report.get("p_value"),
            "ci_low": causal_estimate_report.get("ci_low"),
            "ci_high": causal_estimate_report.get("ci_high"),
            "n_rows": causal_estimate_report.get("n_rows", 0),
            "method": causal_estimate_report.get("method", "unknown"),
        },
        "causal_estimate_report": causal_estimate_report,
        "causal_dataset_profile": causal_dataset_profile,
        "agent_tier_metrics": agent_tier_metrics,
    }

    artifact_path = DATA_DIR / f"{run_id}.json"
    with artifact_path.open("w", encoding="utf-8") as handle:
        json.dump(artifact, handle, indent=2)

    return artifact


def _strategy_card(index: int, memo: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw decision memo into a compact UI strategy card."""

    memo_text = _memo_text(memo)
    lines = [line.strip() for line in memo_text.splitlines() if line.strip()]
    fallback_title = f"Strategy {index + 1}"
    title = lines[0][:50] + ("..." if lines and len(lines[0]) > 50 else "")
    return {
        "title": title or fallback_title,
        "summary": memo_text,
        "risk_score": _risk_score(memo),
        "cost_score": _stable_score(memo_text, "cost", 0.25, 0.75),
        "speed_score": _stable_score(memo_text, "speed", 0.25, 0.85),
    }


def _memo_text(memo: dict[str, Any]) -> str:
    """Return the most useful text view of a serialized memo."""

    if "content" in memo:
        return str(memo["content"])
    return json.dumps(memo, ensure_ascii=False)


def _risk_score(memo: dict[str, Any]) -> float:
    """Derive a deterministic display risk score from memo risk metadata."""

    risks = memo.get("risks", [])
    confidence = str(memo.get("confidence", "") or "").lower()
    base = min(0.85, 0.18 + 0.11 * len(risks or []))
    if confidence == "high":
        base -= 0.08
    elif confidence == "low":
        base += 0.08
    return round(max(0.05, min(0.95, base)), 2)


def _stable_score(text: str, salt: str, low: float, high: float) -> float:
    """Create a stable pseudo-score for UI dimensions without randomness."""

    digest = hashlib.sha256(f"{salt}:{text}".encode("utf-8")).hexdigest()
    value = int(digest[:8], 16) / 0xFFFFFFFF
    return round(low + (high - low) * value, 2)


def _impact_confidence(report: dict[str, Any]) -> str:
    """Map estimator diagnostics into a simple frontend confidence label."""

    if not report or report.get("ate") is None:
        return "insufficient_data"
    p_value = report.get("p_value")
    refuted = report.get("refutation_passed", False)
    if refuted and p_value is not None and p_value <= 0.05:
        return "high"
    if p_value is not None and p_value <= 0.1:
        return "medium"
    return "low"


def _safe_float(value: Any, default: float) -> float:
    """Convert estimator values to JSON-safe floats for the UI."""

    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
