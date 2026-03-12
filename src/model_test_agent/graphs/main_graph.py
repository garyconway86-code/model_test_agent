"""Main LangGraph workflow — orchestrates the full pipeline.

    ┌─────────────┐    ┌──────────────────┐    ┌──────────────────┐
    │  extract     │───▶│  classification   │───▶│  load_history    │
    │  (Tool)      │    │  (Subgraph)       │    │  (Tool)          │
    └─────────────┘    └──────────────────┘    └──────────────────┘
                                                         │
                                                         ▼
    ┌─────────────┐    ┌──────────────────┐    ┌──────────────────┐
    │  report      │◀──│  save_history     │◀──│  debug            │
    │  (Tool)      │    │  (Tool)          │    │  (Subgraph+retry) │
    └─────────────┘    └──────────────────┘    └──────────────────┘

Each box is a LangGraph node.  Subgraphs are compiled child graphs added
as nodes, so they can also be invoked independently.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from model_test_agent.graphs.classification_subgraph import build_classification_subgraph
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

    extractor = LogExtractor()
    errors = extractor.extract_from_directory(log_dir) if log_dir else []

    models: list[ModelInfo] = []
    if config_path:
        reader = ConfigReader()
        models = reader.read_file(config_path)

    return {"errors": errors, "models": models}


def _load_history(state: AgentState) -> dict[str, Any]:
    """Node 3: load history — this is a pass-through that primes the store."""
    # The HistoryStore is loaded lazily by the DebugAnalyzerSkill.
    # This node exists as an explicit step for visibility in the graph.
    store = HistoryStore()
    _ = store.get_all()
    return {}


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
    models_map = {m.name: m for m in state.get("models", [])}
    error_groups = state.get("error_groups", {})

    # Build per-model report rows
    rows: list[ReportRow] = []
    model_errors: dict[str, list[ErrorEntry]] = {}
    for err in errors:
        model_errors.setdefault(err.model_name, []).append(err)

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

    gen = ReportGenerator()
    xlsx_path = gen.generate_xlsx(rows)
    html_path = gen.generate_html(rows)

    return {"report_rows": rows, "report_path": str(xlsx_path)}


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
    graph.add_node("load_history", _load_history)
    graph.add_node("debug", build_debug_subgraph().compile())
    graph.add_node("save_history", _save_history)
    graph.add_node("report", _report)

    # --- Edges ---
    graph.set_entry_point("extract")
    graph.add_edge("extract", "classification")
    graph.add_edge("classification", "load_history")
    graph.add_edge("load_history", "debug")
    graph.add_edge("debug", "save_history")
    graph.add_edge("save_history", "report")
    graph.add_edge("report", END)

    return graph.compile() if compile else graph
