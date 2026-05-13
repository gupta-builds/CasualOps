"""LangGraph assembly for HiveMind's investigation and causal workflow."""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.constants import Send
from langgraph.graph import END, START, StateGraph

from agents import child_agent_node, grand_orchestrator_node, parent_agent_node
from causal import causal_synthesis_node, dowhy_engine_node
from evaluator import evaluate_memos_node
from schema import GraphState

logger = logging.getLogger(__name__)


def route_to_parents(state: GraphState) -> list[Send]:
    """Route execution to parent agents selected by the orchestrator."""

    return [
        Send(
            "parent_agent",
            {
                "task_description": state["task_description"],
                "persona": config.persona,
                "focus_objective": config.focus_objective,
            },
        )
        for config in state.get("parent_configs", [])
    ]


def gather_children_node(state: GraphState) -> dict:
    """Barrier node that lets dynamically produced child configs converge."""

    logger.info(
        "Gathered %s child tasks",
        len(state.get("child_configs", [])),
    )
    return {}


def route_to_children(state: GraphState) -> list[Send]:
    """Route execution to each specialized child agent."""

    return [
        Send(
            "child_agent",
            {
                "task_description": state["task_description"],
                "parent_persona": config.parent_persona,
                "persona": config.persona,
                "focus_objective": config.focus_objective,
            },
        )
        for config in state.get("child_configs", [])
    ]


def conditional_refutation_check(
    state: GraphState,
) -> Literal["end", "causal_synthesis"]:
    """Stop when refuters pass or when estimation is explicitly withheld."""

    estimate_report = state.get("causal_estimate_report") or {}
    method = str(estimate_report.get("method", ""))
    attempts = int(state.get("causal_refutation_attempts", 0))
    if state.get("causal_refutation_passed", False) or method.startswith("withheld:"):
        return "end"
    if attempts >= 2:
        logger.info("Refutation failed after %s attempt(s); ending run", attempts)
        return "end"

    logger.info("Refutation failed; retrying causal synthesis")
    return "causal_synthesis"


def build_graph():
    """Build and compile the executable LangGraph workflow."""

    builder = StateGraph(GraphState)

    builder.add_node("orchestrator", grand_orchestrator_node)
    builder.add_node("parent_agent", parent_agent_node)
    builder.add_node("gather_children", gather_children_node)
    builder.add_node("child_agent", child_agent_node)
    builder.add_node("evaluate_memos", evaluate_memos_node)
    builder.add_node("causal_synthesis", causal_synthesis_node)
    builder.add_node("dowhy_engine", dowhy_engine_node)

    builder.add_edge(START, "orchestrator")
    builder.add_conditional_edges("orchestrator", route_to_parents, ["parent_agent"])
    builder.add_edge("parent_agent", "gather_children")
    builder.add_conditional_edges("gather_children", route_to_children, ["child_agent"])
    builder.add_edge("child_agent", "evaluate_memos")
    builder.add_edge("evaluate_memos", "causal_synthesis")
    builder.add_edge("causal_synthesis", "dowhy_engine")
    builder.add_conditional_edges(
        "dowhy_engine",
        conditional_refutation_check,
        {
            "end": END,
            "causal_synthesis": "causal_synthesis",
        },
    )

    return builder.compile()
