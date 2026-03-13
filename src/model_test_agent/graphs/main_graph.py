"""Main LangGraph workflow — orchestrates the full pipeline.

    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
    │  extract          │───▶│  classification   │───▶│  debug            │
    │  (logs + config)  │    │  (Subgraph)       │    │  (Subgraph+retry) │
    └──────────────────┘    └──────────────────┘    └──────────────────┘
                                                              │
                                                              ▼
                             ┌──────────────────┐    ┌──────────────────┐
                             │  report           │◀──│  save_history     │
                             │  (Tool)           │    │  (Tool)           │
                             └──────────────────┘    └──────────────────┘

Each box is a LangGraph node.  Subgraphs are compiled child graphs added
as nodes, so they can also be invoked independently.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from model_test_agent.graphs.classification_subgraph import build_classification_subgraph
from model_test_agent.llm.client import _load_profiles
from model_test_agent.graphs.debug_subgraph import build_debug_subgraph
from model_test_agent.state import (
    AgentState,
    DebugResult,
    ErrorEntry,
    FixStatus,
    ModelInfo,
    ReportRow,
)
from model_test_agent.tools.config_reader import ConfigReader
from model_test_agent.tools.history_store import HistoryStore
from model_test_agent.tools.log_extractor import LogExtractor
from model_test_agent.tools.report_generator import ReportGenerator


# ------------------------------------------------------------------
# Node functions
# ------------------------------------------------------------------

def _extract(state: AgentState) -> dict[str, Any]:
    """Node 1: extract errors from logs and load model configs."""
    log_dir = state.get("log_dir", "")
    config_path = state.get("config_path", "")

    models: list[ModelInfo] = []
    if config_path:
        reader = ConfigReader()
        models = reader.read_file(config_path)

    extractor = LogExtractor()
    errors: list[ErrorEntry] = []
    explicit_logs = [m for m in models if m.log_path]
    if explicit_logs:
        for model in explicit_logs:
            for path in _expand_paths(model.log_path):
                errors.extend(extractor.extract_from_file(path, model_name=model.name))
    elif log_dir:
        errors = extractor.extract_from_directory(log_dir)

    return {"errors": errors, "models": models}


def _save_history(state: AgentState) -> dict[str, Any]:
    """Node 5: persist successful debug results to history store."""
    store = HistoryStore()
    results = state.get("debug_results", [])
    models_map = {m.name: m for m in state.get("models", [])}

    for dr in results:
        if dr.fix_status == FixStatus.SUCCESS and dr.root_cause:
            model_name = dr.affected_models[0] if dr.affected_models else "unknown"
            m = models_map.get(model_name)
            store.add_case(
                error_category=dr.error_category,
                model_name=model_name,
                quantization=m.quantization if m else "",
                key_log=dr.root_cause[:200],
                root_cause=dr.root_cause,
                solution=dr.suggested_fix,
                effective=True,
            )
    return {}


def _report(state: AgentState) -> dict[str, Any]:
    """Node 6: generate the summary report (XLSX + HTML)."""
    debug_results = state.get("debug_results", [])
    errors = state.get("errors", [])
    models = state.get("models", [])
    models_map = {m.name: m for m in models}

    # Build per-model report rows
    rows: list[ReportRow] = []
    model_errors: dict[str, list[ErrorEntry]] = {}
    for err in errors:
        model_errors.setdefault(err.model_name, []).append(err)
    known_models = {m.name for m in models}
    error_models = set(model_errors)
    if not known_models:
        known_models = error_models

    # Map category → debug result
    dr_map: dict[str, DebugResult] = {dr.error_category: dr for dr in debug_results}

    for model_name, errs in sorted(model_errors.items()):
        m = models_map.get(model_name)
        # Group this model's errors by category
        cats: dict[str, list[ErrorEntry]] = {}
        for e in errs:
            cats.setdefault(e.category, []).append(e)

        for cat, cat_errs in cats.items():
            dr = dr_map.get(cat)
            rows.append(ReportRow(
                model_name=model_name,
                log_path=cat_errs[0].log_path if cat_errs else "",
                log_line=cat_errs[0].line_number if cat_errs else 0,
                package_summary=_load_package_summary(m),
                quantization=m.quantization if m else "",
                has_test_data="是" if (m and m.has_test_data) else "否",
                error_category=cat,
                error_count=len(cat_errs),
                key_log_snippet=cat_errs[0].message[:120] if cat_errs else "",
                history_match="是" if (dr and dr.history_match_id) else "否",
                suggested_fix=dr.suggested_fix[:200] if dr else "",
                fix_executed="是" if (dr and dr.fix_command) else "否",
                fix_result=dr.fix_status.value if dr else "",
                status=dr.fix_status.value if dr else "pending",
            ))

    for model_name in sorted(known_models - error_models):
        m = models_map.get(model_name)
        rows.append(ReportRow(
            model_name=model_name,
            package_summary=_load_package_summary(m),
            quantization=m.quantization if m else "",
            has_test_data="是" if (m and m.has_test_data) else "否",
            error_category="no_error",
            error_count=0,
            key_log_snippet="No error detected",
            history_match="否",
            suggested_fix="",
            fix_executed="否",
            fix_result="success",
            status="success",
        ))

    summary = {
        "total_models": len(known_models),
        "passed_models": len(known_models - error_models),
        "failed_models": len(error_models),
    }
    agent_info = _build_agent_info(state.get("llm_config_path", ""))

    gen = ReportGenerator(output_dir=state.get("output_dir", "."))
    xlsx_path = gen.generate_xlsx(rows)
    html_path = gen.generate_html(rows, summary=summary, agent_info=agent_info)

    return {
        "report_rows": rows,
        "report_path": str(xlsx_path),
        "report_html_path": str(html_path),
    }


def _expand_paths(path_pattern: str) -> list[Path]:
    if not any(token in path_pattern for token in "*?[]"):
        path = Path(path_pattern)
        return [path] if path.exists() else []
    return [Path(match) for match in sorted(glob.glob(path_pattern)) if Path(match).is_file()]


def _load_package_summary(model: ModelInfo | None) -> str:
    if not model:
        return ""
    package_path = model.package_info_path or _default_package_info_path(model.config_path)
    if not package_path:
        return ""
    try:
        data = json.loads(Path(package_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""

    parts = []
    name = data.get("package_name") or data.get("name")
    version = data.get("version")
    build = data.get("build")
    commit = data.get("git_commit") or data.get("commit")
    if name:
        parts.append(str(name))
    if version:
        parts.append(f"v{version}")
    if build:
        parts.append(f"build {build}")
    if commit:
        parts.append(f"commit {str(commit)[:8]}")
    return " | ".join(parts)


def _default_package_info_path(config_path: str) -> str:
    if not config_path:
        return ""
    path = Path(config_path)
    candidate = path.parent / "package_info.json"
    return str(candidate) if candidate.exists() else ""


def _build_agent_info(llm_config_path: str) -> dict[str, str]:
    try:
        profiles = _load_profiles(llm_config_path) if llm_config_path else _load_profiles()
    except Exception:
        profiles = {}
    classifier = profiles.get("classifier", {})
    debugger = profiles.get("debugger", {})
    return {
        "classifier_model": str(classifier.get("model", "-")),
        "debugger_model": str(debugger.get("model", "-")),
        "assisted_fields": "error_category, suggested_fix, root_cause",
    }


# ------------------------------------------------------------------
# Graph builder
# ------------------------------------------------------------------

def build_main_graph(compile: bool = True) -> Any:
    """Construct the full pipeline graph.

    Parameters
    ----------
    compile : bool
        If *True* (default), return a compiled graph ready for invocation.
        If *False*, return the :class:`StateGraph` for further modification.
    """
    graph = StateGraph(AgentState)

    # --- Nodes ---
    graph.add_node("extract", _extract)
    graph.add_node("classification", build_classification_subgraph().compile())
    graph.add_node("debug", build_debug_subgraph().compile())
    graph.add_node("save_history", _save_history)
    graph.add_node("report", _report)

    # --- Edges ---
    graph.set_entry_point("extract")
    graph.add_edge("extract", "classification")
    graph.add_edge("classification", "debug")
    graph.add_edge("debug", "save_history")
    graph.add_edge("save_history", "report")
    graph.add_edge("report", END)

    return graph.compile() if compile else graph
