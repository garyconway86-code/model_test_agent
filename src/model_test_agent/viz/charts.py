"""Generate matplotlib charts for visual reporting.

All charts are saved as PNG images, suitable for embedding in HTML reports
or viewing directly.  No external CDN or network access required.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend — works on headless servers
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from model_test_agent.state import ErrorEntry, DebugResult, FixStatus, ReportRow

# Try to use a CJK font for Chinese labels
_CJK_FONTS = [
    "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei",
    "Microsoft YaHei", "SimHei", "PingFang SC", "Heiti SC",
]

def _find_cjk_font() -> str | None:
    available = {f.name for f in fm.fontManager.ttflist}
    for name in _CJK_FONTS:
        if name in available:
            return name
    return None

_CJK_FONT = _find_cjk_font()
if _CJK_FONT:
    plt.rcParams["font.sans-serif"] = [_CJK_FONT] + plt.rcParams.get("font.sans-serif", [])
    plt.rcParams["axes.unicode_minus"] = False


# Color palette
_COLORS = ["#1F4E79", "#2E75B6", "#4BACC6", "#F79646", "#E74C3C", "#27AE60", "#8E44AD", "#95A5A6"]


class ChartGenerator:
    """Generate analysis charts and save to disk.

    Parameters
    ----------
    output_dir : Path | str
        Directory to write PNG files.
    """

    def __init__(self, output_dir: str | Path = ".") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def error_distribution_pie(
        self,
        errors: list[ErrorEntry],
        filename: str = "error_distribution.png",
    ) -> Path:
        """Pie chart of errors by category."""
        counts = Counter(e.category for e in errors)
        labels = list(counts.keys())
        sizes = list(counts.values())
        colors = _COLORS[: len(labels)]

        fig, ax = plt.subplots(figsize=(8, 6))
        wedges, texts, autotexts = ax.pie(
            sizes, labels=labels, colors=colors, autopct="%1.1f%%",
            startangle=140, pctdistance=0.85,
        )
        for text in autotexts:
            text.set_fontsize(9)
        ax.set_title("错误类型分布", fontsize=14, fontweight="bold")
        fig.tight_layout()

        path = self.output_dir / filename
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path

    def model_error_bar(
        self,
        errors: list[ErrorEntry],
        top_n: int = 20,
        filename: str = "model_errors.png",
    ) -> Path:
        """Horizontal bar chart: top N models by error count."""
        counts = Counter(e.model_name for e in errors)
        most_common = counts.most_common(top_n)
        names = [m for m, _ in reversed(most_common)]
        values = [c for _, c in reversed(most_common)]

        fig, ax = plt.subplots(figsize=(10, max(4, len(names) * 0.4)))
        bars = ax.barh(names, values, color=_COLORS[0], edgecolor="white", height=0.6)
        ax.set_xlabel("错误数量")
        ax.set_title(f"错误最多的 {top_n} 个模型", fontsize=14, fontweight="bold")
        ax.bar_label(bars, padding=3, fontsize=9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        fig.tight_layout()

        path = self.output_dir / filename
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path

    def fix_status_summary(
        self,
        results: list[DebugResult],
        filename: str = "fix_status.png",
    ) -> Path:
        """Bar chart showing fix status per error category."""
        categories = [dr.error_category for dr in results]
        statuses = [dr.fix_status.value for dr in results]

        status_colors = {
            "success": "#27AE60",
            "failed": "#E74C3C",
            "pending": "#F39C12",
            "skipped": "#95A5A6",
            "running": "#4BACC6",
        }
        colors = [status_colors.get(s, "#95A5A6") for s in statuses]

        fig, ax = plt.subplots(figsize=(max(6, len(categories) * 1.2), 5))
        bars = ax.bar(categories, [1] * len(categories), color=colors, edgecolor="white")
        ax.set_ylabel("错误类别")
        ax.set_title("修复状态总览", fontsize=14, fontweight="bold")
        ax.set_yticks([])

        # Legend
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor=c, label=s) for s, c in status_colors.items()
        ]
        ax.legend(handles=legend_elements, loc="upper right", fontsize=9)

        for bar, status in zip(bars, statuses):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() / 2,
                status,
                ha="center", va="center", fontsize=9, fontweight="bold", color="white",
            )

        plt.xticks(rotation=30, ha="right")
        fig.tight_layout()

        path = self.output_dir / filename
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path

    def quantization_heatmap(
        self,
        rows: list[ReportRow],
        filename: str = "quantization_heatmap.png",
    ) -> Path:
        """Heatmap: error count by quantization type × error category."""
        # Build the matrix
        quant_types: list[str] = sorted({r.quantization for r in rows if r.quantization})
        categories: list[str] = sorted({r.error_category for r in rows if r.error_category})
        if not quant_types or not categories:
            # Nothing to plot
            fig, ax = plt.subplots(figsize=(4, 3))
            ax.text(0.5, 0.5, "数据不足", ha="center", va="center", fontsize=14)
            ax.set_axis_off()
            path = self.output_dir / filename
            fig.savefig(path, dpi=150)
            plt.close(fig)
            return path

        matrix = []
        for qt in quant_types:
            row_data = []
            for cat in categories:
                count = sum(
                    r.error_count for r in rows
                    if r.quantization == qt and r.error_category == cat
                )
                row_data.append(count)
            matrix.append(row_data)

        fig, ax = plt.subplots(figsize=(max(6, len(categories) * 1.5), max(4, len(quant_types) * 0.8)))
        im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto")
        ax.set_xticks(range(len(categories)))
        ax.set_xticklabels(categories, rotation=30, ha="right", fontsize=9)
        ax.set_yticks(range(len(quant_types)))
        ax.set_yticklabels(quant_types, fontsize=9)
        ax.set_title("量化类型 × 错误类别 热力图", fontsize=14, fontweight="bold")

        # Annotate cells
        for i in range(len(quant_types)):
            for j in range(len(categories)):
                val = matrix[i][j]
                if val > 0:
                    ax.text(j, i, str(val), ha="center", va="center", fontsize=10, fontweight="bold")

        fig.colorbar(im, ax=ax, shrink=0.8, label="错误数量")
        fig.tight_layout()

        path = self.output_dir / filename
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return path
