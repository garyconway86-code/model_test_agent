"""Classification subgraph — can run independently or as part of the main graph.

Pipeline:  errors → keyword pre-classify → LLM refine → group by category

This subgraph operates on :class:`ClassificationState`, a subset of the full
:class:`AgentState`, which means you can invoke it standalone with just an
``errors`` list.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from langgraph.graph import END, StateGraph

from model_test_agent.skills.error_classifier import ErrorClassifierSkill
from model_test_agent.state import ClassificationState, ErrorEntry


def _group_errors(state: ClassificationState) -> dict[str, Any]:
    """Group errors by their (possibly LLM-refined) category."""
    groups: dict[str, list[ErrorEntry]] = defaultdict(list)
    for err in state.get("errors", []):
        groups[err.category].append(err)
    return {"error_groups": dict(groups)}


def _llm_classify(state: ClassificationState) -> dict[str, Any]:
    """Invoke the ErrorClassifierSkill for LLM-based refinement."""
    skill = ErrorClassifierSkill()
    errors = state.get("errors", [])
    models = state.get("models", [])
    refined = skill.run(errors=errors, models=models)
    return {"errors": refined}


def build_classification_subgraph() -> StateGraph:
    """Construct and return the classification subgraph (uncompiled).

    Nodes:
      1. ``llm_classify`` — refine keyword categories with LLM
      2. ``group_errors``  — bucket errors by final category

    Returns a compiled graph that can be:
      - Added as a node in the main graph.
      - Invoked directly for standalone classification.
    """
    graph = StateGraph(ClassificationState)
    graph.add_node("llm_classify", _llm_classify)
    graph.add_node("group_errors", _group_errors)

    graph.set_entry_point("llm_classify")
    graph.add_edge("llm_classify", "group_errors")
    graph.add_edge("group_errors", END)

    return graph
