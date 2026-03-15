"""CLI entry point — ``python -m model_test_agent`` or ``model-test-agent``.

Provides both interactive (prompt-based) and non-interactive (argument-based)
modes, with full Chinese UI support.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from rich.console import Console

from model_test_agent.i18n import load_strings, t
from model_test_agent.pipeline import PipelineEvent, PipelineExecutionError, run_main_pipeline
from model_test_agent.viz.console import ConsoleUI
from model_test_agent.viz.prompt import InteractivePrompter

console = Console()
ui = ConsoleUI()
prompter = InteractivePrompter()
_PIPELINE_STEP_KEYS = ["extract", "source_context", "classification", "debug", "save_history", "report"]
_STEP_TITLES = {
    "extract": "step_extract",
    "source_context": "step_source",
    "classification": "step_classify",
    "debug": "step_debug",
    "save_history": "step_save",
    "report": "step_report",
    "charts": "step_charts",
}
_SNAPSHOT_TITLES = {
    "extract": "snapshot_extract",
    "source_context": "snapshot_source",
    "classification": "snapshot_classify",
    "debug": "snapshot_debug",
    "report": "snapshot_report",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="model-test-agent",
        description="模型转换测试分析 Agent — 自动化错误分析与修复建议",
    )
    parser.add_argument("--target-dir", type=str, help="目标目录路径（目录下每个子目录是一个测试模型）")
    parser.add_argument("--log-dir", type=str, help="日志目录路径（可替代 --target-dir）")
    parser.add_argument("--target-layout-config", type=str, default=None, help="target-dir 布局配置文件路径")
    parser.add_argument("--codebase-root", type=str, default=None, help="源码根目录（用于提取报错源码上下文）")
    parser.add_argument("--output", type=str, default="./output", help="输出目录（默认: ./output）")
    parser.add_argument(
        "--mode",
        choices=["full", "classify", "debug", "snr"],
        default="full",
        help="运行模式: full=完整流程, classify=仅分类, debug=仅调试, snr=仅SNR分析",
    )
    parser.add_argument("--auto-fix", action="store_true", help="自动执行修复命令")
    parser.add_argument("--locale", type=str, default=None, help="语言: zh / en")
    parser.add_argument("--llm-config", type=str, default=None, help="LLM 配置文件路径")
    parser.add_argument("--max-retries", type=int, default=2, help="修复重试次数（默认: 2）")
    parser.add_argument("--check-api", action="store_true", help="检查所有 LLM API 状态后退出")
    parser.add_argument("--skip-health-check", action="store_true", help="跳过启动前 LLM 预检")
    parser.add_argument("--show-graph", action="store_true", help="显示工作流图结构后退出")
    parser.add_argument("--export-graph", type=str, default=None, help="导出工作流图到文件（.md 或 .png）")
    return parser.parse_args()


def _interactive_setup() -> dict:
    """Prompt user for inputs interactively (Chinese UI)."""
    ui.show_banner()
    console.print()

    target_dir = prompter.ask_path(t("prompt_target_dir"), only_directories=True)
    output_dir = prompter.ask_path(t("prompt_output"), default="./output", only_directories=True)

    # Mode selection
    console.print(f"\n[bold]{t('prompt_subgraph')}:[/bold]")
    console.print(f"  1. {t('mode_full')}")
    console.print(f"  2. {t('mode_classify_only')}")
    console.print(f"  3. {t('mode_debug_only')}")
    console.print(f"  4. {t('mode_snr_only')}")
    mode_choice = prompter.ask_choice("选择", choices=["1", "2", "3", "4"], default="1")
    mode_map = {"1": "full", "2": "classify", "3": "debug", "4": "snr"}
    mode = mode_map[mode_choice]

    auto_fix = False
    if mode in ("full", "debug"):
        auto_fix = prompter.confirm(t("prompt_run_fix"), default=False)

    return {
        "target_dir": target_dir,
        "output_dir": output_dir,
        "llm_config_path": "",
        "target_layout_path": "",
        "codebase_root": "",
        "mode": mode,
        "auto_fix": auto_fix,
    }


def _show_llm_health(llm_config: str | None, timeout: int = 3) -> None:
    from model_test_agent.llm.client import check_all_profiles

    kwargs = {"config_path": llm_config} if llm_config else {}
    with console.status(f"[bold cyan]{t('llm_preflight')}[/bold cyan]", spinner="dots"):
        try:
            results = check_all_profiles(timeout=timeout, **kwargs)
        except Exception as exc:
            results = [{
                "ok": False,
                "profile": "config",
                "model": "-",
                "latency_ms": 0,
                "error": str(exc),
            }]
    ui.show_api_status(results)


def _step_title(step_key: str) -> str:
    return t(_STEP_TITLES.get(step_key, step_key))


def _step_detail(step_key: str, state: dict) -> str:
    if step_key == "extract":
        return f"{len(state.get('errors', []))} 条错误 · {len(state.get('models', []))} 个模型"
    if step_key == "classification":
        return f"{len(state.get('error_groups', {}))} 个错误类别"
    if step_key == "source_context":
        errors = state.get("errors", [])
        resolved = sum(1 for item in errors if item.error_file_path != "Unknown")
        return f"{resolved}/{len(errors)} 条错误定位到源码"
    if step_key == "debug":
        results = state.get("debug_results", [])
        failed = sum(1 for item in results if item.fix_status.value == "failed")
        skipped = sum(1 for item in results if item.fix_status.value == "skipped")
        return f"{len(results)} 条调试结果 · failed={failed} · skipped={skipped}"
    if step_key == "save_history":
        saved = sum(1 for item in state.get("debug_results", []) if item.fix_status.value == "success")
        return f"新增 {saved} 条有效历史记录"
    if step_key == "report":
        return f"{len(state.get('report_rows', []))} 行报告"
    if step_key == "charts":
        return "图表已生成"
    return ""


def _format_counts(counter: Counter, limit: int = 4) -> str:
    items = [f"{name}({count})" for name, count in counter.most_common(limit) if name]
    return ", ".join(items) if items else "-"


def _sample_errors(state: dict, limit: int = 3) -> list:
    def _priority(err) -> tuple[int, int]:
        message = err.message.lower()
        severity = 0 if any(token in message for token in ("error", "exception", "failed", "traceback")) else 1
        return severity, err.line_number

    return sorted(state.get("errors", []), key=_priority)[:limit]


def _format_error_sample(err) -> str:
    keyword = err.matched_keyword or "unknown"
    return f"{err.model_name}:{err.line_number} [{keyword}] {err.message[:72]}"


def _step_snapshot_lines(step_key: str, state: dict) -> list[str]:
    if step_key == "extract" and "errors" not in state and "models" not in state:
        source_dir = Path(state.get("target_dir") or state.get("log_dir", ""))
        model_dirs = [p.name for p in sorted(path for path in source_dir.iterdir() if path.is_dir())[:4]] if source_dir.is_dir() else []
        lines = [
            f"input_dir: {source_dir or '-'}",
        ]
        if state.get("target_layout_path"):
            lines.append(f"layout_config: {state['target_layout_path']}")
        if model_dirs:
            lines.append(f"model_dirs: {', '.join(model_dirs)}")
        return lines

    if step_key == "extract":
        errors = state.get("errors", [])
        models = state.get("models", [])
        per_model = Counter(e.model_name for e in errors)
        lines = [
            f"errors: {len(errors)}",
            f"models: {len(models)}",
            f"top_models: {_format_counts(per_model)}",
        ]
        sample_errors = _sample_errors(state)
        if sample_errors:
            lines.append("sample_hits:")
            lines.extend(f"  - {_format_error_sample(err)}" for err in sample_errors)
        return lines

    if step_key == "classification":
        errors = state.get("errors", [])
        groups = state.get("error_groups", {})
        keyword_counts = Counter(e.matched_keyword for e in errors if e.matched_keyword)
        category_counts = Counter({name: len(items) for name, items in groups.items()})
        lines = [
            f"categories: {_format_counts(category_counts)}",
            f"keywords: {_format_counts(keyword_counts)}",
        ]
        sample_errors = _sample_errors(state)
        if sample_errors:
            lines.append("classified_samples:")
            lines.extend(
                f"  - {_format_error_sample(err)} -> {err.category}"
                for err in sample_errors
            )
        return lines

    if step_key == "source_context":
        errors = state.get("errors", [])
        resolved = [err for err in errors if err.error_file_path != "Unknown"]
        source_hits = [
            err for err in resolved
            if err.source_code_context and "源码未找到" not in err.source_code_context
        ]
        lines = [
            f"resolved_paths: {len(resolved)}/{len(errors)}",
            f"source_hits: {len(source_hits)}/{len(errors)}",
        ]
        if state.get("codebase_root"):
            lines.append(f"codebase_root: {state['codebase_root']}")
        if resolved:
            lines.append("source_samples:")
            lines.extend(
                f"  - {err.error_file_path}:{err.error_line_num or '?'}"
                for err in resolved[:3]
            )
        return lines

    if step_key == "debug":
        results = state.get("debug_results", [])
        status_counts = Counter(item.fix_status.value for item in results)
        history_hits = sum(1 for item in results if item.history_match_id)
        return [
            f"statuses: {_format_counts(status_counts)}",
            f"history_hits: {history_hits}",
        ]

    if step_key == "report":
        report_html_path = state.get("report_html_path", "")
        viewer_path = Path(report_html_path).resolve().as_uri() if report_html_path else "-"
        return [
            f"report_rows: {len(state.get('report_rows', []))}",
            f"report_path: {state.get('report_path', '-')}",
            f"report_html: {report_html_path or '-'}",
            f"viewer: {viewer_path}",
        ]

    return []


def _step_snapshot_title(step_key: str, state: dict) -> str:
    if step_key == "extract" and "errors" not in state and "models" not in state:
        return t("snapshot_inputs")
    return t(_SNAPSHOT_TITLES.get(step_key, _STEP_TITLES.get(step_key, step_key)))


def _show_step_snapshot(step_key: str, state: dict) -> None:
    snapshot_lines = _step_snapshot_lines(step_key, state)
    if snapshot_lines:
        ui.show_step_snapshot(_step_snapshot_title(step_key, state), snapshot_lines)


def _extract_with_source_context(
    target_dir: str,
    target_layout_path: str,
    codebase_root: str,
    log_dir: str = "",
) -> dict:
    """Run extract + source context enrichment for direct CLI modes."""
    from model_test_agent.graphs.main_graph import _enrich_source_context, _extract

    initial_state = {
        "target_dir": target_dir,
        "target_layout_path": target_layout_path,
        "codebase_root": codebase_root,
        "log_dir": log_dir,
    }
    extracted = _extract(initial_state)
    extracted.update(_enrich_source_context({**initial_state, **extracted}))
    return extracted


def _run_classification(errors: list, models: list, llm_config_path: str) -> dict:
    """Execute the classification subgraph and return its state updates."""
    from model_test_agent.graphs.classification_subgraph import build_classification_subgraph

    graph = build_classification_subgraph().compile()
    return graph.invoke({
        "errors": errors,
        "models": models,
        "error_groups": {},
        "llm_config_path": llm_config_path,
    })


def _show_direct_extract_flow(
    target_dir: str,
    target_layout_path: str,
    codebase_root: str,
    log_dir: str = "",
) -> dict:
    """Display extract/source-context stages for classify/debug-only modes."""
    console.print(f"\n[bold blue]{t('step_extract')}...[/bold blue]")
    _show_step_snapshot(
        "extract",
        {"target_dir": target_dir, "target_layout_path": target_layout_path, "log_dir": log_dir},
    )
    extracted = _extract_with_source_context(target_dir, target_layout_path, codebase_root, log_dir)
    _show_step_snapshot("extract", extracted)
    _show_step_snapshot("source_context", {"errors": extracted.get("errors", []), "codebase_root": codebase_root})
    return extracted


def _run_full_pipeline(
    target_dir: str,
    output_dir: str,
    llm_config_path: str,
    target_layout_path: str,
    codebase_root: str,
    max_retries: int,
    auto_fix: bool,
    log_dir: str = "",
) -> None:
    """Execute the complete LangGraph pipeline with live progress."""
    progress = ui.create_progress()
    chart_paths: list[str] = []
    total_steps = len(_PIPELINE_STEP_KEYS) + 1
    with progress:
        task = progress.add_task(
            f"[1/{total_steps}] {_step_title('extract')}",
            total=total_steps,
            detail="等待开始",
        )

        initial_state = {
            "target_dir": target_dir,
            "log_dir": log_dir,
            "output_dir": output_dir,
            "llm_config_path": llm_config_path,
            "target_layout_path": target_layout_path,
            "codebase_root": codebase_root,
            "auto_fix": auto_fix,
            "max_retries": max_retries,
            "retry_count": 0,
        }

        def _on_event(event: PipelineEvent) -> None:
            step_number = event.step_index
            if event.phase == "start":
                progress.update(
                    task,
                    description=f"[{step_number}/{total_steps}] {_step_title(event.step_key)}",
                    detail="运行中",
                )
                if event.step_key == "extract":
                    _show_step_snapshot(event.step_key, event.state)
                return

            if event.phase == "finish":
                progress.update(
                    task,
                    advance=1,
                    detail=_step_detail(event.step_key, event.state),
                )
                _show_step_snapshot(event.step_key, event.state)
                return

            progress.update(
                task,
                description=f"[{step_number}/{total_steps}] {_step_title(event.step_key)}",
                detail=event.error[:80],
            )

        try:
            result = run_main_pipeline(initial_state, on_event=_on_event)
        except PipelineExecutionError as exc:
            ui.show_pipeline_error(_step_title(exc.step_key), str(exc.original_error))
            sys.exit(1)

        progress.update(task, description=f"[{total_steps}/{total_steps}] {_step_title('charts')}", detail="运行中")
        chart_paths = _generate_charts(
            result.get("errors", []),
            result.get("debug_results", []),
            result.get("report_rows", []),
            output_dir,
        )
        progress.update(task, advance=1, detail=_step_detail("charts", result))

    # Display results
    errors = result.get("errors", [])
    models = result.get("models", [])
    error_groups = result.get("error_groups", {})
    debug_results = result.get("debug_results", [])
    report_rows = result.get("report_rows", [])
    report_path = result.get("report_path", "")
    report_html_path = result.get("report_html_path", "")

    ui.show_extraction_summary(errors, models)
    if error_groups:
        ui.show_classification_tree(error_groups)
    if debug_results:
        ui.show_debug_results(debug_results)
    if report_rows:
        ui.show_report_table(report_rows)
    if chart_paths:
        console.print(f"  [dim]图表: {', '.join(chart_paths)}[/dim]")

    if report_path or report_html_path:
        ui.show_completion(report_path, report_html_path)


def _run_classify_only(
    target_dir: str,
    output_dir: str,
    llm_config_path: str,
    target_layout_path: str,
    codebase_root: str,
    log_dir: str = "",
) -> None:
    """Run only the classification subgraph."""
    extracted = _show_direct_extract_flow(target_dir, target_layout_path, codebase_root, log_dir)
    errors = extracted.get("errors", [])
    models = extracted.get("models", [])

    console.print(f"[bold blue]{t('step_classify')}...[/bold blue]")
    result = _run_classification(errors, models, llm_config_path)
    _show_step_snapshot("classification", {"errors": result.get("errors", errors), "error_groups": result.get("error_groups", {})})

    ui.show_extraction_summary(errors, models)
    ui.show_classification_tree(result.get("error_groups", {}))
    chart_paths = _generate_charts(errors, [], [], output_dir)
    if chart_paths:
        console.print(f"  [dim]图表: {', '.join(chart_paths)}[/dim]")


def _run_debug_only(
    target_dir: str,
    output_dir: str,
    llm_config_path: str,
    target_layout_path: str,
    codebase_root: str,
    max_retries: int,
    auto_fix: bool,
    log_dir: str = "",
) -> None:
    """Run classification + debug subgraph (skip reporting)."""
    from model_test_agent.graphs.debug_subgraph import build_debug_subgraph

    extracted = _show_direct_extract_flow(target_dir, target_layout_path, codebase_root, log_dir)
    errors = extracted.get("errors", [])
    models = extracted.get("models", [])

    console.print(f"[bold blue]{t('step_classify')}...[/bold blue]")
    cls_result = _run_classification(errors, models, llm_config_path)
    _show_step_snapshot("classification", {"errors": cls_result.get("errors", errors), "error_groups": cls_result.get("error_groups", {})})

    console.print(f"[bold blue]{t('step_debug')}...[/bold blue]")
    dbg_graph = build_debug_subgraph().compile()
    dbg_result = dbg_graph.invoke({
        "error_groups": cls_result.get("error_groups", {}),
        "models": models,
        "debug_results": [],
        "retry_count": 0,
        "max_retries": max_retries,
        "auto_fix": auto_fix,
        "llm_config_path": llm_config_path,
    })
    _show_step_snapshot("debug", {"debug_results": dbg_result.get("debug_results", [])})

    ui.show_extraction_summary(errors, models)
    ui.show_classification_tree(cls_result.get("error_groups", {}))
    ui.show_debug_results(dbg_result.get("debug_results", []))
    chart_paths = _generate_charts(errors, dbg_result.get("debug_results", []), [], output_dir)
    if chart_paths:
        console.print(f"  [dim]图表: {', '.join(chart_paths)}[/dim]")


def _run_snr_only(target_dir: str, target_layout_path: str = "") -> None:
    """Run only the SNR subgraph."""
    from model_test_agent.graphs.snr_subgraph import build_snr_subgraph
    from model_test_agent.tools.config_reader import ConfigReader

    models = ConfigReader.read_target_directory(target_dir, layout_path=target_layout_path) if target_dir else []
    if not models:
        console.print(f"[bold red]{t('error_no_target')}[/bold red]")
        return

    console.print("\n[bold blue]运行 layerwise SNR 分析...[/bold blue]")
    graph = build_snr_subgraph().compile()
    result = graph.invoke({"models": models, "snr_results": {}})

    console.print("[bold green]SNR 分析完成[/bold green]")
    snr_results = result.get("snr_results", {})
    for model_name, data in snr_results.items():
        console.print(f"  [bold]{model_name}[/bold]: {data}")


def _generate_charts(
    errors: list,
    debug_results: list,
    report_rows: list,
    output_dir: str,
) -> list[str]:
    """Generate all charts to the output directory."""
    from model_test_agent.viz.charts import ChartGenerator

    charts = ChartGenerator(output_dir=output_dir)
    paths: list[str] = []
    if errors:
        pie_path = charts.error_distribution_pie(errors)
        bar_path = charts.model_error_bar(errors)
        paths.extend([str(pie_path), str(bar_path)])
    if debug_results:
        fix_path = charts.fix_status_summary(debug_results)
        paths.append(str(fix_path))
    if report_rows:
        hm_path = charts.quantization_heatmap(report_rows)
        paths.append(str(hm_path))
    return paths


def main() -> None:
    args = _parse_args()
    load_strings(locale=args.locale)

    # --check-api: health-check all LLM profiles and exit
    if args.check_api:
        from model_test_agent.llm.client import check_all_profiles
        ui.show_banner()
        llm_cfg = args.llm_config or None
        kwargs = {"config_path": llm_cfg} if llm_cfg else {}
        results = check_all_profiles(**kwargs)
        ui.show_api_status(results)
        return

    if not args.skip_health_check:
        _show_llm_health(args.llm_config or None)

    # --show-graph / --export-graph: display graph structure and exit
    if args.show_graph or args.export_graph:
        from model_test_agent.graphs.main_graph import build_main_graph
        ui.show_banner()
        graph = build_main_graph(compile=True)
        ui.show_graph_structure(graph)
        if args.export_graph:
            from model_test_agent.viz.graph_viz import export_mermaid, export_png
            out = args.export_graph
            if out.endswith(".png"):
                result = export_png(graph, out)
                if result:
                    console.print(f"  图结构已导出: [underline]{result}[/underline]")
                else:
                    console.print("  [yellow]PNG 导出失败（需要 pyppeteer），已回退到 Mermaid[/yellow]")
                    export_mermaid(graph, out.replace(".png", ".md"))
            else:
                export_mermaid(graph, out)
                console.print(f"  图结构已导出: [underline]{out}[/underline]")
        return

    # If no target-dir is provided, enter interactive mode
    if not args.target_dir and not args.log_dir:
        settings = _interactive_setup()
    else:
        settings = {
            "target_dir": args.target_dir or "",
            "log_dir": args.log_dir or "",
            "output_dir": args.output,
            "llm_config_path": args.llm_config or "",
            "target_layout_path": args.target_layout_config or "",
            "codebase_root": args.codebase_root or "",
            "mode": args.mode,
            "auto_fix": args.auto_fix,
        }

    target_dir = settings.get("target_dir", "")
    log_dir = settings.get("log_dir", "")
    output_dir = settings["output_dir"]
    llm_config_path = settings.get("llm_config_path", "")
    target_layout_path = settings.get("target_layout_path", "")
    codebase_root = settings.get("codebase_root", "")
    mode = settings["mode"]

    input_dir = target_dir or log_dir
    if not input_dir or not Path(input_dir).is_dir():
        console.print(f"[bold red]{t('error_no_target')}: {input_dir or '-'}[/bold red]")
        sys.exit(1)
    if mode == "snr" and not target_dir:
        console.print("[bold red]SNR 模式需要 --target-dir[/bold red]")
        sys.exit(1)

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if mode == "full":
        _run_full_pipeline(
            target_dir,
            output_dir,
            llm_config_path,
            target_layout_path,
            codebase_root,
            args.max_retries,
            settings["auto_fix"],
            log_dir,
        )
    elif mode == "classify":
        _run_classify_only(target_dir, output_dir, llm_config_path, target_layout_path, codebase_root, log_dir)
    elif mode == "debug":
        _run_debug_only(
            target_dir,
            output_dir,
            llm_config_path,
            target_layout_path,
            codebase_root,
            args.max_retries,
            settings["auto_fix"],
            log_dir,
        )
    elif mode == "snr":
        _run_snr_only(target_dir, target_layout_path)


if __name__ == "__main__":
    main()
