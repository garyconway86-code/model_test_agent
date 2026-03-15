"""Imperative pipeline runner for CLI progress and error reporting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from model_test_agent.graphs.classification_subgraph import build_classification_subgraph
from model_test_agent.graphs.debug_subgraph import build_debug_subgraph
from model_test_agent.graphs.main_graph import _enrich_source_context, _extract, _report, _save_history
from model_test_agent.state import AgentState


@dataclass(frozen=True)
class PipelineStep:
    key: str
    runner: Callable[[AgentState], dict[str, Any]]


@dataclass(frozen=True)
class PipelineEvent:
    phase: str
    step_key: str
    step_index: int
    total_steps: int
    state: AgentState
    error: str = ""


class PipelineExecutionError(RuntimeError):
    """Raised when one pipeline step fails."""

    def __init__(self, step_key: str, original_error: Exception) -> None:
        super().__init__(str(original_error))
        self.step_key = step_key
        self.original_error = original_error


def _build_steps() -> list[PipelineStep]:
    classification = build_classification_subgraph().compile()
    debug = build_debug_subgraph().compile()
    return [
        PipelineStep("extract", _extract),
        PipelineStep("source_context", _enrich_source_context),
        PipelineStep("classification", classification.invoke),
        PipelineStep("debug", debug.invoke),
        PipelineStep("save_history", _save_history),
        PipelineStep("report", _report),
    ]


def run_main_pipeline(
    initial_state: AgentState,
    on_event: Callable[[PipelineEvent], None] | None = None,
) -> AgentState:
    """Run the full pipeline with per-step callbacks."""
    return run_pipeline_steps(initial_state, [step.key for step in _build_steps()], on_event=on_event)


def run_pipeline_steps(
    initial_state: AgentState,
    step_keys: list[str],
    on_event: Callable[[PipelineEvent], None] | None = None,
) -> AgentState:
    """Run a selected subset of pipeline steps with per-step callbacks."""
    state: AgentState = dict(initial_state)
    step_map = {step.key: step for step in _build_steps()}
    steps = [step_map[key] for key in step_keys]
    total_steps = len(steps)

    for index, step in enumerate(steps, start=1):
        if on_event:
            on_event(PipelineEvent("start", step.key, index, total_steps, dict(state)))

        try:
            updates = step.runner(state) or {}
        except Exception as exc:
            if on_event:
                on_event(PipelineEvent("error", step.key, index, total_steps, dict(state), str(exc)))
            raise PipelineExecutionError(step.key, exc) from exc

        state.update(updates)
        if on_event:
            on_event(PipelineEvent("finish", step.key, index, total_steps, dict(state)))

    return state
