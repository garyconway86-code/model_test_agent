"""Main LangGraph workflow — orchestrates the full pipeline.

    ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
    │  extract          │───▶│  classification   │───▶│  debug            │
    │  (target-dir)     │    │  (Subgraph)       │    │  (Subgraph+retry) │
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

import hashlib
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
from model_test_agent.tools.source_context import SourceContextResolver


# ------------------------------------------------------------------
# Node functions
# ------------------------------------------------------------------

def _extract(state: AgentState) -> dict[str, Any]:
    """Node 1: extract errors from logs and load model configs."""
    target_dir = state.get("target_dir", "")
    target_layout_path = state.get("target_layout_path", "")

    models: list[ModelInfo] = []
    source_info: dict[str, str] = {}
    if target_dir:
        reader = ConfigReader()
        models = reader.read_target_directory(target_dir, layout_path=target_layout_path)
        source_info = reader.describe_target_layout(target_dir, layout_path=target_layout_path)

    extractor = LogExtractor()
    errors: list[ErrorEntry] = []
    explicit_logs = [m for m in models if m.log_path]
    if explicit_logs:
        for model in explicit_logs:
            errors.extend(extractor.extract_from_file(model.log_path, model_name=model.name))
    elif target_dir:
        errors = extractor.extract_from_target_directory(target_dir)

    return {"errors": errors, "models": models, "source_info": source_info}


def _enrich_source_context(state: AgentState) -> dict[str, Any]:
    """Resolve source file locations from logs and load nearby code context."""
    errors = state.get("errors", [])
    resolver = SourceContextResolver(
        codebase_root=state.get("codebase_root", ""),
        docker_script_path=state.get("docker_script_path", ""),
    )
    for err in errors:
        file_path, line_num = resolver.extract_error_location(err.raw_context or err.message)
        err.error_file_path = file_path
        err.error_line_num = line_num
        err.source_code_context = resolver.retrieve_code_context(file_path, line_num)

    source_info = dict(state.get("source_info") or {})
    if source_info:
        source_info["codebase_root"] = resolver.describe_codebase_root()
    return {"errors": errors, "source_info": source_info}


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
    all_model_names = sorted(known_models | error_models)

    for model_name in all_model_names:
        errs = model_errors.get(model_name, [])
        m = models_map.get(model_name)
        if not errs:
            rows.append(ReportRow(
                model_name=model_name,
                package_summary=_load_package_summary(m),
                quantization=m.quantization if m else "",
                has_test_data="是" if (m and m.has_test_data) else "否",
                config_hints=_config_hints(m),
                error_category="no_error",
                error_count=0,
                key_log_snippet="No error detected",
                history_match="否",
                suggested_fix="",
                fix_executed="否",
                fix_result="success",
                status="success",
                checked_by="",
            ))
            continue

        categories = list(dict.fromkeys(err.category for err in errs if err.category))
        results = [dr_map[category] for category in categories if category in dr_map]
        lead_error = min(errs, key=lambda err: (err.line_number or 0, err.log_path))

        rows.append(ReportRow(
            model_name=model_name,
            log_path=lead_error.log_path,
            log_line=lead_error.line_number,
            package_summary=_load_package_summary(m),
            quantization=m.quantization if m else "",
            has_test_data="是" if (m and m.has_test_data) else "否",
            config_hints=_config_hints(m),
            error_category=", ".join(categories) or "unknown",
            error_count=len(errs),
            key_log_snippet=_summarize_error_messages(errs),
            history_match="是" if any(dr.history_match_id for dr in results) else "否",
            suggested_fix=_summarize_suggested_fixes(results),
            fix_executed="是" if any(dr.fix_command for dr in results) else "否",
            fix_result=_summarize_fix_results(results),
            status=_aggregate_status(results),
            checked_by="",
        ))

    passed_models = sum(1 for row in rows if row.status == "success")
    summary = {
        "total_models": len(rows),
        "passed_models": passed_models,
        "failed_models": len(rows) - passed_models,
    }
    agent_info = _build_agent_info(state.get("llm_config_path", ""))
    source_info = state.get("source_info") or {
        "target_dir": state.get("target_dir") or "-",
        "layout_config": "built-in defaults",
        "discovery_rule": "{model_name}.yaml + package_info.json + latest file in Converter_result/convert/.log",
        "source_tree": (
            "target-dir/\n"
            "  <model-dir>/\n"
            "    <model-name>.yaml\n"
            "    package_info.json\n"
            "    Converter_result/convert/.log/\n"
            "      latest log file"
        ),
    }

    report_dir = _report_output_dir(state.get("output_dir", "."), state.get("target_dir", ""))
    gen = ReportGenerator(output_dir=report_dir)
    xlsx_path = gen.generate_xlsx(rows, filename="report.xlsx")
    html_path = gen.generate_html(
        rows,
        filename="report.html",
        summary=summary,
        agent_info=agent_info,
        source_info=source_info,
    )

    return {
        "report_rows": rows,
        "report_path": str(xlsx_path),
        "report_html_path": str(html_path),
    }


def _aggregate_status(results: list[DebugResult]) -> str:
    if not results:
        return "pending"
    priorities = {
        FixStatus.FAILED.value: 0,
        FixStatus.RUNNING.value: 1,
        FixStatus.PENDING.value: 2,
        FixStatus.SKIPPED.value: 3,
        FixStatus.SUCCESS.value: 4,
    }
    return min((result.fix_status.value for result in results), key=lambda status: priorities.get(status, 99))


def _summarize_error_messages(errors: list[ErrorEntry], limit: int = 2) -> str:
    snippets: list[str] = []
    for error in errors:
        message = error.message.strip()
        if message and message not in snippets:
            snippets.append(message[:120])
        if len(snippets) >= limit:
            break
    return " | ".join(snippets)


def _summarize_suggested_fixes(results: list[DebugResult], limit: int = 3) -> str:
    suggestions: list[str] = []
    for result in results:
        suggestion = result.suggested_fix.strip()
        if not suggestion:
            continue
        label = f"{result.error_category}: {suggestion}"
        if label not in suggestions:
            suggestions.append(label)
        if len(suggestions) >= limit:
            break
    return " | ".join(suggestions)


def _summarize_fix_results(results: list[DebugResult], limit: int = 3) -> str:
    if not results:
        return ""
    statuses: list[str] = []
    for result in results:
        label = f"{result.error_category}:{result.fix_status.value}"
        if label not in statuses:
            statuses.append(label)
        if len(statuses) >= limit:
            break
    return ", ".join(statuses)
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


def _report_output_dir(output_dir: str, target_dir: str) -> Path:
    base = Path(output_dir or ".").resolve()
    if not target_dir:
        return base
    target_path = Path(target_dir).resolve()
    target_id = _stable_target_id(target_path)
    report_dir = base / target_id
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def _stable_target_id(target_path: Path) -> str:
    label = target_path.name or "target"
    digest = hashlib.sha1(str(target_path).encode("utf-8")).hexdigest()[:8]
    safe_label = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in label).strip("-")
    return f"{safe_label or 'target'}-{digest}"


def _config_hints(model: ModelInfo | None, limit: int = 4) -> str:
    if not model:
        return ""
    files = model.extra.get("config_context_files", [])
    model_dir = Path(str(model.extra.get("model_dir", ""))) if model.extra.get("model_dir") else None
    labels: list[str] = []
    for file_path in files[:limit]:
        path = Path(str(file_path))
        try:
            label = str(path.relative_to(model_dir)) if model_dir else path.name
        except ValueError:
            label = path.name
        if label not in labels:
            labels.append(label)
    return " | ".join(labels)


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
        "assisted_fields": "error_category, source_code_context, suggested_fix, root_cause",
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
    graph.add_node("source_context", _enrich_source_context)
    graph.add_node("classification", build_classification_subgraph().compile())
    graph.add_node("debug", build_debug_subgraph().compile())
    graph.add_node("save_history", _save_history)
    graph.add_node("report", _report)

    # --- Edges ---
    graph.set_entry_point("extract")
    graph.add_edge("extract", "source_context")
    graph.add_edge("source_context", "classification")
    graph.add_edge("classification", "debug")
    graph.add_edge("debug", "save_history")
    graph.add_edge("save_history", "report")
    graph.add_edge("report", END)

    return graph.compile() if compile else graph
