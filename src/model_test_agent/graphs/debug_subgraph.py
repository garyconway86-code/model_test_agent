"""Debug subgraph — analyze errors, suggest fixes, optionally execute and retry.

This subgraph implements a **loop/retry** pattern:

    analyze → execute_fix → check_result
                   ↑              │
                   └──── retry ───┘  (if failed and retries left)

It operates on :class:`DebugState` and can run independently.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from model_test_agent.skills.debug_analyzer import DebugAnalyzerSkill
from model_test_agent.state import DebugResult, DebugState, FixStatus
from model_test_agent.tools.docker_executor import DockerExecutor
from model_test_agent.tools.history_store import HistoryStore


def _analyze(state: DebugState) -> dict[str, Any]:
    """Run the DebugAnalyzerSkill on all error groups."""
    skill = DebugAnalyzerSkill()
    store = HistoryStore()
    history = store.get_all()

    error_groups = state.get("error_groups", {})
    models = state.get("models", [])

    results = skill.run(error_groups=error_groups, models=models, history_cases=history)
    return {"debug_results": results, "retry_count": 0}


def _execute_fix(state: DebugState) -> dict[str, Any]:
    """Execute fix commands via Docker for results that have a fix_command."""
    executor = DockerExecutor()
    results = state.get("debug_results", [])
    updated: list[DebugResult] = []

    for dr in results:
        if dr.fix_command and dr.fix_status in (FixStatus.PENDING, FixStatus.FAILED):
            dr.fix_status = FixStatus.RUNNING
            outcome = executor.run(dr.fix_command)
            dr.fix_output = outcome.output
            dr.fix_status = FixStatus.SUCCESS if outcome.success else FixStatus.FAILED
            dr.retry_count = state.get("retry_count", 0)
        updated.append(dr)

    return {"debug_results": updated}


def _check_result(state: DebugState) -> str:
    """Conditional edge: decide whether to retry or finish."""
    results = state.get("debug_results", [])
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)

    has_failed = any(dr.fix_status == FixStatus.FAILED for dr in results)
    if has_failed and retry_count < max_retries:
        return "retry"
    return "done"


def _increment_retry(state: DebugState) -> dict[str, Any]:
    """Bump the retry counter before looping back to analyze."""
    return {"retry_count": state.get("retry_count", 0) + 1}


def build_debug_subgraph() -> StateGraph:
    """Construct and return the debug subgraph (uncompiled).

    Nodes:
      1. ``analyze``          — LLM-based root cause analysis
      2. ``execute_fix``      — run fix commands in Docker
      3. ``increment_retry``  — bump counter before retry loop

    Conditional edges implement the retry loop.
    """
    graph = StateGraph(DebugState)

    graph.add_node("analyze", _analyze)
    graph.add_node("execute_fix", _execute_fix)
    graph.add_node("increment_retry", _increment_retry)

    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "execute_fix")
    graph.add_conditional_edges(
        "execute_fix",
        _check_result,
        {
            "retry": "increment_retry",
            "done": END,
        },
    )
    graph.add_edge("increment_retry", "analyze")

    return graph
