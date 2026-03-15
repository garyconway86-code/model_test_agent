"""Shared state definitions used across all graphs and subgraphs.

The state schema is the single source of truth for data flowing through the
LangGraph pipeline.  Every node reads from and writes to typed fields so that
subgraphs can run independently with a compatible subset of the full state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict


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
    log_path: str = ""
    package_info_path: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorEntry:
    """A single extracted error from the test log."""

    model_name: str
    line_number: int
    message: str
    log_path: str = ""
    raw_context: str = ""
    error_file_path: str = "Unknown"
    error_line_num: int = 0
    source_code_context: str = ""
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
    log_path: str = ""
    log_line: int = 0
    package_summary: str = ""
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
    checked_by: str = ""


class AgentState(TypedDict, total=False):
    """Full pipeline state.  Subgraphs may use a subset of these keys."""

    # --- Inputs ---
    target_dir: str
    log_dir: str
    config_path: str
    target_layout_path: str
    codebase_root: str
    output_dir: str
    llm_config_path: str
    auto_fix: bool
    source_info: dict[str, str]

    # --- Extracted data ---
    models: list[ModelInfo]
    errors: list[ErrorEntry]

    # --- Classification ---
    error_groups: dict[str, list[ErrorEntry]]

    # --- Debug ---
    debug_results: list[DebugResult]

    # --- Report ---
    report_rows: list[ReportRow]
    report_path: str
    report_html_path: str

    # --- Control flow ---
    current_category: str
    retry_count: int
    max_retries: int


# Convenience subsets for subgraphs that only need part of the state.

class ClassificationState(TypedDict, total=False):
    errors: list[ErrorEntry]
    error_groups: dict[str, list[ErrorEntry]]
    models: list[ModelInfo]
    llm_config_path: str


class DebugState(TypedDict, total=False):
    error_groups: dict[str, list[ErrorEntry]]
    debug_results: list[DebugResult]
    models: list[ModelInfo]
    current_category: str
    retry_count: int
    max_retries: int
    auto_fix: bool
    llm_config_path: str


class SNRState(TypedDict, total=False):
    """State for the layerwise SNR analysis subgraph."""

    models: list[ModelInfo]
    snr_results: dict[str, Any]
    log_dir: str
