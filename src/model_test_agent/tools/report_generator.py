"""Generate summary reports in XLSX and HTML formats.

Reads column definitions from ``config/report.yaml`` so the layout is
customisable without touching code.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from model_test_agent.state import ReportRow

_DEFAULT_REPORT_CFG = Path(__file__).resolve().parents[3] / "config" / "report.yaml"


class ReportGenerator:
    """Build XLSX and HTML reports from a list of :class:`ReportRow`.

    Parameters
    ----------
    config_path : Path | str
        Path to ``config/report.yaml``.
    output_dir : Path | str
        Directory where generated files are written.
    """

    def __init__(
        self,
        config_path: str | Path = _DEFAULT_REPORT_CFG,
        output_dir: str | Path = ".",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cfg_path = Path(config_path)
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as fh:
                self._cfg = yaml.safe_load(fh) or {}
        else:
            self._cfg = {}

    # ------------------------------------------------------------------
    # XLSX
    # ------------------------------------------------------------------

    def generate_xlsx(self, rows: list[ReportRow], filename: str | None = None) -> Path:
        """Write an XLSX report and return the file path."""
        xlsx_cfg = self._cfg.get("xlsx", {})
        columns: list[dict[str, Any]] = xlsx_cfg.get("columns", self._default_columns())

        if filename is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            template = xlsx_cfg.get("filename_template", "test_report_{timestamp}.xlsx")
            filename = template.replace("{timestamp}", ts)

        wb = Workbook()
        ws = wb.active
        ws.title = xlsx_cfg.get("sheet_name", "Report")

        # --- Header row ---
        header_fill = PatternFill(
            start_color=xlsx_cfg.get("header_fill_color", "1F4E79"),
            end_color=xlsx_cfg.get("header_fill_color", "1F4E79"),
            fill_type="solid",
        )
        header_font = Font(
            bold=True,
            color=xlsx_cfg.get("header_font_color", "FFFFFF"),
            size=11,
        )
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        for col_idx, col_def in enumerate(columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col_def["header"])
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = thin_border
            ws.column_dimensions[get_column_letter(col_idx)].width = col_def.get("width", 18)

        # --- Data rows ---
        alt_fill_color = xlsx_cfg.get("alternating_row_color", "D6E4F0")
        alt_fill = PatternFill(start_color=alt_fill_color, end_color=alt_fill_color, fill_type="solid")

        for row_idx, report_row in enumerate(rows, start=2):
            row_dict = self._row_to_dict(report_row)
            for col_idx, col_def in enumerate(columns, start=1):
                value = row_dict.get(col_def["key"], "")
                cell = ws.cell(row=row_idx, column=col_idx, value=value)
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                cell.border = thin_border
                if row_idx % 2 == 0:
                    cell.fill = alt_fill

        # Freeze header
        ws.freeze_panes = "A2"

        out_path = self.output_dir / filename
        wb.save(str(out_path))
        return out_path

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    def generate_html(self, rows: list[ReportRow], filename: str | None = None) -> Path:
        """Write a self-contained HTML report and return the file path."""
        html_cfg = self._cfg.get("html", {})
        xlsx_cfg = self._cfg.get("xlsx", {})
        columns: list[dict[str, Any]] = xlsx_cfg.get("columns", self._default_columns())

        if filename is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            template = html_cfg.get("filename_template", "test_report_{timestamp}.html")
            filename = template.replace("{timestamp}", ts)

        title = html_cfg.get("title", "Model Conversion Test Report")

        # Build table rows
        header_cells = "".join(f'<th>{c["header"]}</th>' for c in columns)
        body_rows = []
        for i, report_row in enumerate(rows):
            rd = self._row_to_dict(report_row)
            cls = ' class="alt"' if i % 2 == 1 else ""
            cells = "".join(f"<td>{rd.get(c['key'], '')}</td>" for c in columns)
            body_rows.append(f"  <tr{cls}>{cells}</tr>")
        body_html = "\n".join(body_rows)

        # Statistics for the summary section
        total = len(rows)
        by_category: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for r in rows:
            by_category[r.error_category] = by_category.get(r.error_category, 0) + 1
            by_status[r.status] = by_status.get(r.status, 0) + 1

        stats_rows = "".join(
            f"<tr><td>{cat}</td><td>{cnt}</td></tr>" for cat, cnt in sorted(by_category.items())
        )
        status_rows = "".join(
            f"<tr><td>{st}</td><td>{cnt}</td></tr>" for st, cnt in sorted(by_status.items())
        )

        html = _HTML_TEMPLATE.format(
            title=title,
            header_cells=header_cells,
            body_rows=body_html,
            total=total,
            stats_rows=stats_rows,
            status_rows=status_rows,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        out_path = self.output_dir / filename
        out_path.write_text(html, encoding="utf-8")
        return out_path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: ReportRow) -> dict[str, Any]:
        return {
            "model_name": row.model_name,
            "quantization": row.quantization,
            "has_test_data": row.has_test_data,
            "error_category": row.error_category,
            "error_count": row.error_count,
            "key_log_snippet": row.key_log_snippet,
            "history_match": row.history_match,
            "suggested_fix": row.suggested_fix,
            "fix_executed": row.fix_executed,
            "fix_result": row.fix_result,
            "status": row.status,
        }

    @staticmethod
    def _default_columns() -> list[dict[str, Any]]:
        return [
            {"key": "model_name", "header": "Model Name", "width": 28},
            {"key": "quantization", "header": "Quantization", "width": 14},
            {"key": "has_test_data", "header": "Has Test Data", "width": 13},
            {"key": "error_category", "header": "Error Category", "width": 18},
            {"key": "error_count", "header": "Error Count", "width": 12},
            {"key": "key_log_snippet", "header": "Key Log (truncated)", "width": 50},
            {"key": "history_match", "header": "Seen Before", "width": 12},
            {"key": "suggested_fix", "header": "Suggested Fix", "width": 55},
            {"key": "fix_executed", "header": "Fix Executed", "width": 12},
            {"key": "fix_result", "header": "Fix Result", "width": 18},
            {"key": "status", "header": "Status", "width": 12},
        ]


# ------------------------------------------------------------------
# HTML template (no external dependencies)
# ------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --primary: #1F4E79;
    --primary-light: #D6E4F0;
    --success: #27ae60;
    --danger: #e74c3c;
    --warning: #f39c12;
    --bg: #f5f6fa;
    --text: #2c3e50;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 24px;
  }}
  h1 {{
    color: var(--primary);
    margin-bottom: 8px;
    font-size: 1.6em;
  }}
  .meta {{ color: #7f8c8d; margin-bottom: 24px; font-size: 0.9em; }}
  .summary {{
    display: flex;
    gap: 24px;
    margin-bottom: 24px;
    flex-wrap: wrap;
  }}
  .summary-card {{
    background: #fff;
    border-radius: 8px;
    padding: 16px 24px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    min-width: 200px;
  }}
  .summary-card h3 {{
    font-size: 0.85em;
    color: #7f8c8d;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
  }}
  .summary-card .big {{ font-size: 2em; font-weight: 700; color: var(--primary); }}
  .summary-card table {{ width: 100%; font-size: 0.9em; }}
  .summary-card td {{ padding: 2px 8px; }}
  .summary-card td:last-child {{ text-align: right; font-weight: 600; }}
  .table-wrapper {{
    overflow-x: auto;
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  }}
  table.report {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85em;
  }}
  table.report th {{
    background: var(--primary);
    color: #fff;
    padding: 10px 12px;
    text-align: left;
    position: sticky;
    top: 0;
    white-space: nowrap;
  }}
  table.report td {{
    padding: 8px 12px;
    border-bottom: 1px solid #ecf0f1;
    max-width: 400px;
    word-wrap: break-word;
  }}
  table.report tr.alt {{ background: var(--primary-light); }}
  table.report tr:hover {{ background: #eaf2f8; }}
  footer {{
    margin-top: 24px;
    text-align: center;
    color: #95a5a6;
    font-size: 0.8em;
  }}
</style>
</head>
<body>
  <h1>{title}</h1>
  <div class="meta">Generated: {timestamp}</div>

  <div class="summary">
    <div class="summary-card">
      <h3>Total Models</h3>
      <div class="big">{total}</div>
    </div>
    <div class="summary-card">
      <h3>Errors by Category</h3>
      <table>{stats_rows}</table>
    </div>
    <div class="summary-card">
      <h3>Status</h3>
      <table>{status_rows}</table>
    </div>
  </div>

  <div class="table-wrapper">
    <table class="report">
      <thead><tr>{header_cells}</tr></thead>
      <tbody>
{body_rows}
      </tbody>
    </table>
  </div>

  <footer>model-test-agent v0.1.0</footer>
</body>
</html>
"""
