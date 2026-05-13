"""Adaptive evaluator node for ranking child-agent decision memos."""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel, Field

from schema import GraphState

logger = logging.getLogger(__name__)

llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview"),
    temperature=0.4,
)


class EvaluationScore(BaseModel):
    """Per-memo scoring dimensions emitted by the evaluator."""

    relevance: float = Field(description="0.0 to 1.0 relevance to the task")
    reasoning: float = Field(description="0.0 to 1.0 reasoning quality")
    constraint_satisfaction: float = Field(
        description="0.0 to 1.0 satisfaction of scenario constraints"
    )
    overall_score: float = Field(description="0.0 to 1.0 composed score")


class MemoEvaluation(BaseModel):
    """Evaluation for one memo perspective."""

    perspective: str
    score: EvaluationScore
    feedback: str = Field(description="Brief feedback on the memo")


class RankedStrategies(BaseModel):
    """Structured evaluator output for downstream strategy and causal synthesis."""

    evaluations: list[MemoEvaluation] = Field(description="Evaluation for each memo")
    ranked_perspectives: list[str] = Field(
        description="Ranked perspectives from best to worst"
    )
    final_recommendation: str = Field(
        description="Synthesized recommendation based on top strategies"
    )


DYNAMIC_EVALUATOR_PROMPT = """
You are an adaptive, expert evaluator.

ORIGINAL TASK:
{task_description}

INSTRUCTIONS:
1. Dynamically analyze the original task to determine implicit priorities.
2. Score memos against those priorities. Do not default to risk unless the task warrants it.
3. Ranking: Rank the perspectives based on your adaptive scoring.

Evaluate each memo, score it, rank perspectives, and provide a final recommendation.
"""

evaluator_prompt = ChatPromptTemplate.from_messages([
    ("system", DYNAMIC_EVALUATOR_PROMPT),
    ("user", "Memos:\n{memos_text}"),
])

structured_evaluator_llm = llm.with_structured_output(RankedStrategies)
evaluator_chain = evaluator_prompt | structured_evaluator_llm


def evaluate_memos_node(state: GraphState):
    """LangGraph node to evaluate and rank all collected memos."""

    logger.info("Evaluator running")
    memos = state.get("memos", [])
    if not memos:
        logger.info("No memos found to evaluate")
        return {
            "ranked_strategies": [],
            "final_recommendation": None,
            "evaluator_error": None,
        }

    memos_text = ""
    for i, memo in enumerate(memos):
        assumptions = _memo_value(memo, "assumptions", []) or []
        risks = _memo_value(memo, "risks", []) or []
        second_order_effects = _memo_value(memo, "second_order_effects", []) or []
        evidence_needs = _memo_value(memo, "evidence_needs", []) or []
        perspective = _memo_value(memo, "perspective", "unknown")
        strategy = _memo_value(memo, "strategy", "")
        memos_text += f"--- Memo {i + 1} ({perspective}) ---\n"
        memos_text += f"Strategy: {strategy}\n"
        memos_text += (
            "Assumptions: "
            f"{', '.join(assumptions) if assumptions else 'Not specified'}\n"
        )
        memos_text += f"Risks: {', '.join(risks) if risks else 'Not specified'}\n"
        memos_text += (
            "Second Order Effects: "
            f"{', '.join(second_order_effects) if second_order_effects else 'Not specified'}\n"
        )
        memos_text += (
            "Evidence Needs: "
            f"{', '.join(evidence_needs) if evidence_needs else 'Not specified'}\n\n"
        )

    try:
        result = evaluator_chain.invoke({
            "task_description": state.get("task_description", ""),
            "memos_text": memos_text,
        })
    except Exception as exc:
        logger.exception("Evaluator LLM call failed")
        return {
            "ranked_strategies": [],
            "final_recommendation": None,
            "evaluator_error": str(exc),
        }

    ranked_strategies = result.model_dump()

    logger.info("Evaluator completed")
    return {
        "ranked_strategies": [ranked_strategies],
        "final_recommendation": ranked_strategies.get("final_recommendation"),
        "evaluator_error": None,
    }


def _memo_value(memo: Any, field: str, default: Any) -> Any:
    """Read memo fields from either Pydantic models or dictionaries."""

    if isinstance(memo, dict):
        return memo.get(field, default)
    return getattr(memo, field, default)
