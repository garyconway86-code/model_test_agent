"""CLI entry point — ``python -m model_test_agent`` or ``model-test-agent``.

Provides both interactive (prompt-based) and non-interactive (argument-based)
modes, with full Chinese UI support.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, Prompt

from model_test_agent.i18n import load_strings, t
from model_test_agent.viz.console import ConsoleUI

console = Console()
ui = ConsoleUI()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="model-test-agent",
        description="模型转换测试分析 Agent — 自动化错误分析与修复建议",
    )
    parser.add_argument("--log-dir", type=str, help="日志目录路径")
    parser.add_argument("--config", type=str, help="模型配置文件路径")
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
    parser.add_argument("--show-graph", action="store_true", help="显示工作流图结构后退出")
    parser.add_argument("--export-graph", type=str, default=None, help="导出工作流图到文件（.md 或 .png）")
    return parser.parse_args()


def _interactive_setup() -> dict:
    """Prompt user for inputs interactively (Chinese UI)."""
    ui.show_banner()
    console.print()

    log_dir = Prompt.ask(f"[bold]{t('prompt_log_dir')}[/bold]")
    config_path = Prompt.ask(f"[bold]{t('prompt_config')}[/bold]", default="")
    output_dir = Prompt.ask(f"[bold]{t('prompt_output')}[/bold]", default="./output")

    # Mode selection
    console.print(f"\n[bold]{t('prompt_subgraph')}:[/bold]")
    console.print(f"  1. {t('mode_full')}")
    console.print(f"  2. {t('mode_classify_only')}")
    console.print(f"  3. {t('mode_debug_only')}")
    console.print(f"  4. {t('mode_snr_only')}")
    mode_choice = Prompt.ask("选择", choices=["1", "2", "3", "4"], default="1")
    mode_map = {"1": "full", "2": "classify", "3": "debug", "4": "snr"}
    mode = mode_map[mode_choice]

    auto_fix = False
    if mode in ("full", "debug"):
        auto_fix = Confirm.ask(f"[bold]{t('prompt_run_fix')}[/bold]", default=False)

    return {
        "log_dir": log_dir,
        "config_path": config_path,
        "output_dir": output_dir,
        "mode": mode,
        "auto_fix": auto_fix,
    }


def _run_full_pipeline(log_dir: str, config_path: str, output_dir: str, max_retries: int) -> None:
    """Execute the complete LangGraph pipeline with live progress."""
    from model_test_agent.graphs.main_graph import build_main_graph

    progress = ui.create_progress()
    with progress:
        task = progress.add_task(t("step_extract"), total=6)

        graph = build_main_graph(compile=True)
        initial_state = {
            "log_dir": log_dir,
            "config_path": config_path,
            "errors": [],
            "models": [],
            "error_groups": {},
            "debug_results": [],
            "report_rows": [],
            "max_retries": max_retries,
            "retry_count": 0,
        }

        progress.update(task, description=t("step_extract"))
        result = graph.invoke(initial_state)
        progress.update(task, advance=6)

    # Display results
    errors = result.get("errors", [])
    models = result.get("models", [])
    error_groups = result.get("error_groups", {})
    debug_results = result.get("debug_results", [])
    report_rows = result.get("report_rows", [])
    report_path = result.get("report_path", "")

    ui.show_extraction_summary(errors, models)
    if error_groups:
        ui.show_classification_tree(error_groups)
    if debug_results:
        ui.show_debug_results(debug_results)
    if report_rows:
        ui.show_report_table(report_rows)

    # Generate charts
    _generate_charts(errors, debug_results, report_rows, output_dir)

    if report_path:
        ui.show_completion(report_path)


def _run_classify_only(log_dir: str, config_path: str, output_dir: str) -> None:
    """Run only the classification subgraph."""
    from model_test_agent.graphs.classification_subgraph import build_classification_subgraph
    from model_test_agent.tools.config_reader import ConfigReader
    from model_test_agent.tools.log_extractor import LogExtractor

    console.print(f"\n[bold blue]{t('step_extract')}...[/bold blue]")
    extractor = LogExtractor()
    errors = extractor.extract_from_directory(log_dir)

    models = []
    if config_path:
        models = ConfigReader.read_file(config_path)

    console.print(f"[bold blue]{t('step_classify')}...[/bold blue]")
    graph = build_classification_subgraph().compile()
    result = graph.invoke({"errors": errors, "models": models, "error_groups": {}})

    ui.show_extraction_summary(errors, models)
    ui.show_classification_tree(result.get("error_groups", {}))
    _generate_charts(errors, [], [], output_dir)


def _run_debug_only(log_dir: str, config_path: str, output_dir: str, max_retries: int) -> None:
    """Run classification + debug subgraph (skip reporting)."""
    from model_test_agent.graphs.classification_subgraph import build_classification_subgraph
    from model_test_agent.graphs.debug_subgraph import build_debug_subgraph
    from model_test_agent.tools.config_reader import ConfigReader
    from model_test_agent.tools.log_extractor import LogExtractor

    console.print(f"\n[bold blue]{t('step_extract')}...[/bold blue]")
    extractor = LogExtractor()
    errors = extractor.extract_from_directory(log_dir)
    models = ConfigReader.read_file(config_path) if config_path else []

    console.print(f"[bold blue]{t('step_classify')}...[/bold blue]")
    cls_graph = build_classification_subgraph().compile()
    cls_result = cls_graph.invoke({"errors": errors, "models": models, "error_groups": {}})

    console.print(f"[bold blue]{t('step_debug')}...[/bold blue]")
    dbg_graph = build_debug_subgraph().compile()
    dbg_result = dbg_graph.invoke({
        "error_groups": cls_result.get("error_groups", {}),
        "models": models,
        "debug_results": [],
        "retry_count": 0,
        "max_retries": max_retries,
    })

    ui.show_extraction_summary(errors, models)
    ui.show_classification_tree(cls_result.get("error_groups", {}))
    ui.show_debug_results(dbg_result.get("debug_results", []))


def _run_snr_only(config_path: str) -> None:
    """Run only the SNR subgraph."""
    from model_test_agent.graphs.snr_subgraph import build_snr_subgraph
    from model_test_agent.tools.config_reader import ConfigReader

    models = ConfigReader.read_file(config_path) if config_path else []
    if not models:
        console.print(f"[bold red]{t('error_no_config')}[/bold red]")
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
) -> None:
    """Generate all charts to the output directory."""
    from model_test_agent.viz.charts import ChartGenerator

    charts = ChartGenerator(output_dir=output_dir)
    if errors:
        pie_path = charts.error_distribution_pie(errors)
        bar_path = charts.model_error_bar(errors)
        console.print(f"  [dim]图表: {pie_path}, {bar_path}[/dim]")
    if debug_results:
        fix_path = charts.fix_status_summary(debug_results)
        console.print(f"  [dim]图表: {fix_path}[/dim]")
    if report_rows:
        hm_path = charts.quantization_heatmap(report_rows)
        console.print(f"  [dim]图表: {hm_path}[/dim]")


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

    # If no log_dir provided, enter interactive mode
    if not args.log_dir:
        settings = _interactive_setup()
    else:
        settings = {
            "log_dir": args.log_dir,
            "config_path": args.config or "",
            "output_dir": args.output,
            "mode": args.mode,
            "auto_fix": args.auto_fix,
        }

    log_dir = settings["log_dir"]
    config_path = settings["config_path"]
    output_dir = settings["output_dir"]
    mode = settings["mode"]

    # Validate log directory
    if mode != "snr" and not Path(log_dir).is_dir():
        console.print(f"[bold red]{t('error_no_logs')}: {log_dir}[/bold red]")
        sys.exit(1)

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if mode == "full":
        _run_full_pipeline(log_dir, config_path, output_dir, args.max_retries)
    elif mode == "classify":
        _run_classify_only(log_dir, config_path, output_dir)
    elif mode == "debug":
        _run_debug_only(log_dir, config_path, output_dir, args.max_retries)
    elif mode == "snr":
        _run_snr_only(config_path)


if __name__ == "__main__":
    main()
