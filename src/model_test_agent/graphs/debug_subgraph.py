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

from model_test_agent.debug_config import load_debug_settings
from model_test_agent.skills.debug_analyzer import DebugAnalyzerSkill
from model_test_agent.state import DebugResult, DebugState, FixStatus
from model_test_agent.tools.docker_executor import DockerExecutor
from model_test_agent.tools.semantic_retriever import SemanticRetriever


def _analyze(state: DebugState) -> dict[str, Any]:
    """Run the DebugAnalyzerSkill on all error groups."""
    error_groups = state.get("error_groups", {})
    models = state.get("models", [])
    llm_config_path = state.get("llm_config_path")
    rag_dir = state.get("rag_dir", "")
    existing_results = {result.error_category: result for result in state.get("debug_results", [])}

    pending_groups = {
        category: errors
        for category, errors in error_groups.items()
        if existing_results.get(category, DebugResult(error_category=category)).fix_status in (
            FixStatus.PENDING,
            FixStatus.FAILED,
        )
    }
    if not pending_groups:
        return {"debug_results": list(existing_results.values())}

    retrieval_top_k = load_debug_settings().retrieval.top_k
    skill = DebugAnalyzerSkill(llm_config_path=llm_config_path)
    retriever = SemanticRetriever(config_path=llm_config_path, knowledge_dir=rag_dir)

    # Retrieve relevant history per category before calling the LLM.
    history_per_category = {
        category: retriever.find_similar(
            category,
            key_log=errors[0].message if errors else "",
            top_k=retrieval_top_k,
        )
        for category, errors in pending_groups.items()
    }

    refreshed_results = skill.run(
        error_groups=pending_groups,
        models=models,
        history_per_category=history_per_category,
    )
    results = [
        existing_results[category]
        for category in error_groups
        if category in existing_results and category not in pending_groups
    ]
    refreshed_map = {result.error_category: result for result in refreshed_results}
    for category in error_groups:
        if category in refreshed_map:
            results.append(refreshed_map[category])
    return {"debug_results": results}


def _execute_fix(state: DebugState) -> dict[str, Any]:
    """Execute fix commands via Docker for results that have a fix_command."""
    executor = DockerExecutor(docker_script_path=state.get("docker_script_path", ""))
    auto_fix = state.get("auto_fix", False)
    results = state.get("debug_results", [])
    updated: list[DebugResult] = []

    for dr in results:
        if dr.fix_command and not auto_fix and dr.fix_status == FixStatus.PENDING:
            dr.fix_status = FixStatus.SKIPPED
            dr.fix_output = "Auto-fix disabled; command not executed."
        elif dr.fix_command and dr.fix_status in (FixStatus.PENDING, FixStatus.FAILED):
            dr.fix_status = FixStatus.RUNNING
            outcome = executor.run(dr.fix_command)
            dr.fix_output = outcome.output
            dr.fix_status = FixStatus.SUCCESS if outcome.success else FixStatus.FAILED
            dr.retry_count = state.get("retry_count", 0)
        updated.append(dr)

    return {"debug_results": updated}


def _check_result(state: DebugState) -> str:
    """Conditional edge: decide whether to retry or finish."""
    if not state.get("auto_fix", False):
        return "done"

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
