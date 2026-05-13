"""Deterministic quality metrics for each HiveMind agent tier.

These metrics are not a replacement for human review, but they give the demo a
standardized scoreboard: every tier has an expected contract, an observed
signal, and a normalized score. That directly answers whether the orchestrator,
agents, evaluator, causal architect, and estimator are being tested consistently.
"""

from __future__ import annotations

from typing import Any, Iterable


def score_agent_tiers(final_state: dict[str, Any]) -> dict[str, Any]:
    """Score all workflow tiers from the final LangGraph state."""

    parent_configs = final_state.get("parent_configs", []) or []
    child_configs = final_state.get("child_configs", []) or []
    memos = final_state.get("memos", []) or []
    ranked = final_state.get("ranked_strategies", []) or []
    evaluator_error = final_state.get("evaluator_error")
    causal_payload = final_state.get("causal_payload") or {}
    estimate_report = final_state.get("causal_estimate_report") or {}

    metrics = {
        "orchestrator": _score_orchestrator(parent_configs),
        "parent_agents": _score_parent_agents(child_configs),
        "child_agents": _score_child_agents(memos),
        "evaluator": _score_evaluator(ranked, evaluator_error),
        "causal_architect": _score_causal_architect(causal_payload.get("graph", {})),
        "estimator": _score_estimator(estimate_report),
    }
    overall = sum(item["score"] for item in metrics.values()) / max(len(metrics), 1)
    return {
        "overall_score": round(overall, 3),
        "tiers": metrics,
    }


def _score_orchestrator(parent_configs: Iterable[Any]) -> dict[str, Any]:
    """Score whether the orchestrator produced the expected branch count."""

    parents = list(parent_configs)
    count = len(parents)
    score = 1.0 if 2 <= count <= 3 else 0.55 if count > 0 else 0.0
    return {
        "score": score,
        "observed": count,
        "target": "2-3 parent investigatory vectors",
    }


def _score_parent_agents(child_configs: Iterable[Any]) -> dict[str, Any]:
    """Score whether parent agents produced complete child tasks."""

    children = list(child_configs)
    complete = sum(
        1
        for child in children
        if _field(child, "persona") and _field(child, "focus_objective")
    )
    score = complete / max(len(children), 1) if children else 0.0
    if len(children) >= 4:
        score = min(1.0, score + 0.1)
    return {
        "score": round(score, 3),
        "observed": len(children),
        "target": "specialized children with persona and focus objective",
    }


def _score_child_agents(memos: Iterable[Any]) -> dict[str, Any]:
    """Score child-agent memo completeness."""

    memo_list = list(memos)
    if not memo_list:
        return {
            "score": 0.0,
            "observed": 0,
            "target": "memos with strategy, risks, assumptions, evidence needs",
        }

    field_scores: list[float] = []
    for memo in memo_list:
        fields_present = [
            bool(_field(memo, "strategy")),
            bool(_field(memo, "risks")),
            bool(_field(memo, "assumptions")),
            bool(_field(memo, "second_order_effects")),
            bool(_field(memo, "evidence_needs")),
        ]
        field_scores.append(sum(fields_present) / len(fields_present))

    return {
        "score": round(sum(field_scores) / len(field_scores), 3),
        "observed": len(memo_list),
        "target": "complete DecisionMemo fields",
    }


def _score_evaluator(
    ranked: list[dict[str, Any]],
    evaluator_error: str | None,
) -> dict[str, Any]:
    """Score evaluator output shape and failure handling."""

    if evaluator_error:
        return {
            "score": 0.0,
            "observed": "error",
            "target": "ranked strategies with final recommendation",
        }

    latest = ranked[-1] if ranked else {}
    has_evals = bool(latest.get("evaluations"))
    has_rank = bool(latest.get("ranked_perspectives"))
    has_recommendation = bool(latest.get("final_recommendation"))
    score = sum([has_evals, has_rank, has_recommendation]) / 3
    return {
        "score": round(score, 3),
        "observed": len(ranked),
        "target": "evaluations, rank order, final recommendation",
    }


def _score_causal_architect(graph: dict[str, Any]) -> dict[str, Any]:
    """Score graph validity, treatment/outcome clarity, and evidence tests."""

    nodes = graph.get("nodes", []) or []
    edges = graph.get("edges", []) or []
    treatment = graph.get("treatment_variable")
    outcome = graph.get("outcome_variable")
    has_path = _has_path(edges, treatment, outcome) if treatment and outcome else False
    acyclic = _is_acyclic(nodes, edges)
    edge_evidence = sum(
        1
        for edge in edges
        if edge.get("required_evidence") or edge.get("falsification_tests")
    )
    evidence_ratio = edge_evidence / max(len(edges), 1) if edges else 0.0
    score = sum(
        [
            bool(nodes),
            bool(edges),
            bool(treatment),
            bool(outcome),
            has_path,
            acyclic,
        ]
    ) / 6
    score = min(1.0, score * 0.8 + evidence_ratio * 0.2)
    return {
        "score": round(score, 3),
        "observed": {
            "nodes": len(nodes),
            "edges": len(edges),
            "acyclic": acyclic,
            "treatment_to_outcome_path": has_path,
        },
        "target": (
            "valid measurable DAG with treatment/outcome path and evidence "
            "requirements"
        ),
    }


def _score_estimator(report: dict[str, Any]) -> dict[str, Any]:
    """Score estimator readiness and statistical reporting completeness."""

    if not report:
        return {
            "score": 0.0,
            "observed": "missing",
            "target": "estimate report or explicit data-quality refusal",
        }

    if report.get("ate") is None:
        score = 0.55 if str(report.get("method", "")).startswith("withheld:") else 0.25
    else:
        score = 0.65
        if report.get("p_value") is not None:
            score += 0.15
        if report.get("ci_low") is not None and report.get("ci_high") is not None:
            score += 0.1
        if report.get("refuters"):
            score += 0.1

    return {
        "score": round(min(1.0, score), 3),
        "observed": {
            "method": report.get("method"),
            "n_rows": report.get("n_rows"),
            "has_p_value": report.get("p_value") is not None,
            "refuters": len(report.get("refuters", []) or []),
        },
        "target": "gated estimate with p-value, CI, and refuters when data permits",
    }


def _has_path(edges: list[dict[str, Any]], source: str, target: str) -> bool:
    """Return whether the graph contains a path from source to target."""

    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge.get("source"), []).append(edge.get("target"))

    stack = [source]
    seen = set()
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, []))
    return False


def _is_acyclic(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> bool:
    """Return whether directed graph edges are acyclic."""

    node_ids = {node.get("id") for node in nodes}
    indegree = {node_id: 0 for node_id in node_ids if node_id}
    adjacency = {node_id: [] for node_id in node_ids if node_id}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source in adjacency and target in indegree:
            adjacency[source].append(target)
            indegree[target] += 1

    queue = [node for node, degree in indegree.items() if degree == 0]
    visited = 0
    while queue:
        node = queue.pop()
        visited += 1
        for child in adjacency.get(node, []):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    return visited == len(indegree)


def _field(obj: Any, name: str) -> Any:
    """Read fields from Pydantic objects or dictionaries consistently."""

    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)
