"""Shared state definitions used across all graphs and subgraphs.

The state schema is the single source of truth for data flowing through the
LangGraph pipeline.  Every node reads from and writes to typed fields so that
subgraphs can run independently with a compatible subset of the full state.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, Any, TypedDict


# ------------------------------------------------------------------
# Domain value objects
# ------------------------------------------------------------------

class FixStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ModelInfo:
    """Metadata about one model under test."""

    name: str
    quantization: str = "fp32"
    has_test_data: bool = False
    config_path: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorEntry:
    """A single extracted error from the test log."""

    model_name: str
    line_number: int
    message: str
    raw_context: str = ""
    category: str = "unknown"
    matched_keyword: str = ""


@dataclass
class DebugResult:
    """The outcome of one debug analysis + optional fix attempt."""

    error_category: str
    affected_models: list[str] = field(default_factory=list)
    root_cause: str = ""
    suggested_fix: str = ""
    fix_command: str = ""
    fix_output: str = ""
    fix_status: FixStatus = FixStatus.PENDING
    retry_count: int = 0
    history_match_id: str = ""


@dataclass
class ReportRow:
    """One row in the final summary report."""

    model_name: str = ""
    quantization: str = ""
    has_test_data: str = ""
    error_category: str = ""
    error_count: int = 0
    key_log_snippet: str = ""
    history_match: str = ""
    suggested_fix: str = ""
    fix_executed: str = ""
    fix_result: str = ""
    status: str = ""


# ------------------------------------------------------------------
# LangGraph state — used as TypedDict for graph compatibility
# ------------------------------------------------------------------

def _merge_lists(left: list, right: list) -> list:
    """Reducer: append items from *right* onto *left*."""
    return left + right


def _merge_dicts(left: dict, right: dict) -> dict:
    """Reducer: shallow-merge *right* into *left*."""
    merged = {**left}
    for key, value in right.items():
        if key in merged and isinstance(merged[key], list) and isinstance(value, list):
            merged[key] = merged[key] + value
        else:
            merged[key] = value
    return merged


class AgentState(TypedDict, total=False):
    """Full pipeline state.  Subgraphs may use a subset of these keys."""

    # --- Inputs ---
    log_dir: str
    config_path: str

    # --- Extracted data ---
    models: Annotated[list[ModelInfo], _merge_lists]
    errors: Annotated[list[ErrorEntry], _merge_lists]

    # --- Classification ---
    error_groups: Annotated[dict[str, list[ErrorEntry]], _merge_dicts]

    # --- Debug ---
    debug_results: Annotated[list[DebugResult], _merge_lists]

    # --- Report ---
    report_rows: Annotated[list[ReportRow], _merge_lists]
    report_path: str

    # --- Control flow ---
    current_category: str
    retry_count: int
    max_retries: int


# Convenience subsets for subgraphs that only need part of the state.

class ClassificationState(TypedDict, total=False):
    errors: Annotated[list[ErrorEntry], _merge_lists]
    error_groups: Annotated[dict[str, list[ErrorEntry]], _merge_dicts]
    models: Annotated[list[ModelInfo], _merge_lists]


class DebugState(TypedDict, total=False):
    error_groups: Annotated[dict[str, list[ErrorEntry]], _merge_dicts]
    debug_results: Annotated[list[DebugResult], _merge_lists]
    models: Annotated[list[ModelInfo], _merge_lists]
    current_category: str
    retry_count: int
    max_retries: int


class SNRState(TypedDict, total=False):
    """State for the layerwise SNR analysis subgraph."""

    models: Annotated[list[ModelInfo], _merge_lists]
    snr_results: Annotated[dict[str, Any], _merge_dicts]
    log_dir: str
