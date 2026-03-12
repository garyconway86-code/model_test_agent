"""Rich-based terminal UI for real-time pipeline progress and results.

Provides:
  - Live progress bars during pipeline execution
  - Colored tables for quick result inspection
  - Tree view of error classification
  - Panel-based summary cards
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.tree import Tree

from model_test_agent.state import DebugResult, ErrorEntry, FixStatus, ModelInfo, ReportRow

console = Console()


class ConsoleUI:
    """Terminal interface for the model test agent."""

    def __init__(self) -> None:
        self.console = console

    # ------------------------------------------------------------------
    # Pipeline progress
    # ------------------------------------------------------------------

    def create_progress(self) -> Progress:
        """Create a Rich progress bar for pipeline steps."""
        return Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
        )

    # ------------------------------------------------------------------
    # Result display
    # ------------------------------------------------------------------

    def show_banner(self) -> None:
        self.console.print(Panel(
            "[bold cyan]模型转换测试分析 Agent[/bold cyan]\n"
            "[dim]基于 LangGraph 的自动化错误分析与修复建议系统[/dim]",
            border_style="cyan",
            padding=(1, 2),
        ))

    def show_extraction_summary(self, errors: list[ErrorEntry], models: list[ModelInfo]) -> None:
        self.console.print()
        self.console.rule("[bold]📋 提取结果", style="blue")
        self.console.print(f"  模型数量: [bold]{len(models)}[/bold]")
        self.console.print(f"  错误总数: [bold red]{len(errors)}[/bold red]")
        self.console.print(f"  涉及模型: [bold]{len({e.model_name for e in errors})}[/bold]")

    def show_classification_tree(self, error_groups: dict[str, list[ErrorEntry]]) -> None:
        self.console.print()
        self.console.rule("[bold]🔍 错误分类结果", style="blue")
        tree = Tree("[bold]错误分类")
        for category, errors in sorted(error_groups.items(), key=lambda x: -len(x[1])):
            branch = tree.add(f"[bold yellow]{category}[/bold yellow] ({len(errors)} 个)")
            models = sorted({e.model_name for e in errors})
            for m in models[:10]:
                count = sum(1 for e in errors if e.model_name == m)
                branch.add(f"{m} [dim]×{count}[/dim]")
            if len(models) > 10:
                branch.add(f"[dim]... 及其他 {len(models) - 10} 个模型[/dim]")
        self.console.print(tree)

    def show_debug_results(self, results: list[DebugResult]) -> None:
        self.console.print()
        self.console.rule("[bold]🔧 调试分析结果", style="blue")
        for dr in results:
            status_color = {
                FixStatus.SUCCESS: "green",
                FixStatus.FAILED: "red",
                FixStatus.PENDING: "yellow",
                FixStatus.SKIPPED: "dim",
                FixStatus.RUNNING: "cyan",
            }.get(dr.fix_status, "white")

            panel_content = (
                f"[bold]影响模型:[/bold] {', '.join(dr.affected_models[:5])}"
                + (f" 等{len(dr.affected_models)}个" if len(dr.affected_models) > 5 else "")
                + f"\n[bold]根本原因:[/bold] {dr.root_cause[:200]}"
                + f"\n[bold]修复建议:[/bold] {dr.suggested_fix[:200]}"
                + f"\n[bold]修复状态:[/bold] [{status_color}]{dr.fix_status.value}[/{status_color}]"
            )
            if dr.history_match_id:
                panel_content += f"\n[bold]历史匹配:[/bold] {dr.history_match_id}"

            self.console.print(Panel(
                panel_content,
                title=f"[bold]{dr.error_category}[/bold]",
                border_style=status_color,
                padding=(0, 1),
            ))

    def show_report_table(self, rows: list[ReportRow]) -> None:
        self.console.print()
        self.console.rule("[bold]📊 汇总报告", style="blue")
        table = Table(
            show_header=True,
            header_style="bold white on #1F4E79",
            border_style="blue",
            row_styles=["", "on #D6E4F0"],
            pad_edge=True,
        )
        table.add_column("模型", style="bold", max_width=25)
        table.add_column("量化", max_width=10)
        table.add_column("测试数据", max_width=8)
        table.add_column("错误类型", style="yellow", max_width=18)
        table.add_column("数量", justify="right", max_width=6)
        table.add_column("日志摘要", max_width=40)
        table.add_column("历史", max_width=6)
        table.add_column("修复建议", max_width=40)
        table.add_column("状态", max_width=10)

        for row in rows:
            status_color = {
                "success": "[green]",
                "failed": "[red]",
                "pending": "[yellow]",
                "skipped": "[dim]",
            }.get(row.status, "")
            status_end = "[/]" if status_color else ""

            table.add_row(
                row.model_name,
                row.quantization,
                row.has_test_data,
                row.error_category,
                str(row.error_count),
                row.key_log_snippet[:40],
                row.history_match,
                row.suggested_fix[:40],
                f"{status_color}{row.status}{status_end}",
            )

        self.console.print(table)

    def show_api_status(self, status_list: list[dict]) -> None:
        """Display LLM API health check results as a table."""
        self.console.print()
        self.console.rule("[bold]🔌 LLM API 状态", style="blue")
        table = Table(
            show_header=True,
            header_style="bold white on #1F4E79",
            border_style="blue",
        )
        table.add_column("Profile", style="bold", min_width=12)
        table.add_column("Model", min_width=16)
        table.add_column("状态", min_width=6, justify="center")
        table.add_column("延迟", justify="right", min_width=8)
        table.add_column("错误", max_width=50)

        for s in status_list:
            status = "[bold green]OK[/bold green]" if s["ok"] else "[bold red]FAIL[/bold red]"
            latency = f"{s['latency_ms']}ms" if s["latency_ms"] else "-"
            error = s.get("error", "")[:50]
            table.add_row(s["profile"], s["model"], status, latency, error)

        self.console.print(table)

    def show_graph_structure(self, graph: Any) -> None:
        """Display graph structure in the terminal."""
        from model_test_agent.viz.graph_viz import print_graph_ascii

        self.console.print()
        self.console.rule("[bold]🔀 工作流结构", style="blue")
        ascii_repr = print_graph_ascii(graph)
        self.console.print(Panel(ascii_repr, border_style="cyan", padding=(0, 1)))

    def show_completion(self, report_path: str) -> None:
        self.console.print()
        self.console.print(Panel(
            f"[bold green]✅ 分析完成[/bold green]\n"
            f"报告已生成: [underline]{report_path}[/underline]",
            border_style="green",
        ))
