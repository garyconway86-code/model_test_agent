"""Export a standalone offline demo HTML from an existing report."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

from model_test_agent.tools.report_server import review_state_path


def export_demo_html(
    report_path: str | Path,
    output_path: str | Path | None = None,
    preview_paths: Iterable[str | Path] | None = None,
) -> Path:
    """Export a single-file offline demo HTML from an existing report."""
    report = Path(report_path).resolve()
    if not report.is_file():
        raise FileNotFoundError(f"Report file not found: {report}")

    report_html = report.read_text(encoding="utf-8")
    review_path = review_state_path(report)
    preview_files = [report]
    if review_path.is_file():
        preview_files.append(review_path)
    for item in preview_paths or []:
        candidate = Path(item).expanduser().resolve()
        if candidate.is_file() and candidate not in preview_files:
            preview_files.append(candidate)

    generated_at, target_dir = _extract_report_meta(report_html)
    previews = [_build_preview_payload(path) for path in preview_files]
    output = Path(output_path).resolve() if output_path else report.with_name(f"{report.stem}.demo.html")
    output.write_text(
        _DEMO_TEMPLATE.format(
            title="Model Debug Agent | 智能体辅助日志分析",
            exported_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            generated_at=html.escape(generated_at or "-"),
            target_dir=html.escape(target_dir or "-"),
            report_path=html.escape(str(report)),
            review_path=html.escape(str(review_path if review_path.is_file() else "-")),
            report_name=html.escape(report.name),
            preview_tabs=_build_preview_tabs(previews),
            preview_panes=_build_preview_panes(previews),
            report_srcdoc=json.dumps(report_html, ensure_ascii=False),
        ),
        encoding="utf-8",
    )
    return output


def _extract_report_meta(report_html: str) -> tuple[str, str]:
    meta_match = re.search(r'<div class="meta">Generated:\s*(.*?)<br>Target Dir:\s*(.*?)</div>', report_html, re.DOTALL)
    if not meta_match:
        return "", ""
    generated = re.sub(r"\s+", " ", meta_match.group(1)).strip()
    target_dir = re.sub(r"\s+", " ", meta_match.group(2)).strip()
    return generated, target_dir


def _build_preview_payload(path: Path) -> dict[str, str]:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        content = f"[Unable to read file]\n{exc}"
    return {
        "name": path.name,
        "path": str(path),
        "content": content,
    }


def _build_preview_tabs(previews: list[dict[str, str]]) -> str:
    tabs = []
    for index, item in enumerate(previews):
        active = " active" if index == 0 else ""
        tabs.append(
            f'<button type="button" class="preview-tab{active}" data-preview-tab="{index}">{html.escape(item["name"])}</button>'
        )
    return "".join(tabs)


def _build_preview_panes(previews: list[dict[str, str]]) -> str:
    panes = []
    for index, item in enumerate(previews):
        active = "" if index == 0 else " hidden"
        panes.append(
            f'<section class="preview-pane{active}" data-preview-pane="{index}">'
            f'<div class="preview-meta">{html.escape(item["path"])}</div>'
            f'<pre><code>{html.escape(item["content"])}</code></pre>'
            "</section>"
        )
    return "".join(panes)


_DEMO_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    :root {{
      --ink: #18344a;
      --muted: #64748b;
      --line: rgba(24, 52, 74, 0.12);
      --panel: #ffffff;
      --bg: linear-gradient(180deg, #f4f7fb 0%, #eef3f8 100%);
      --accent: #0f6cbd;
      --accent-soft: #eaf4ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }}
    .shell {{
      display: grid;
      grid-template-columns: 360px minmax(0, 1fr);
      gap: 18px;
      padding: 24px;
      min-height: 100vh;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 18px 40px rgba(15, 23, 42, 0.06);
      overflow: hidden;
    }}
    .side {{
      display: grid;
      gap: 18px;
      align-content: start;
    }}
    .hero {{
      padding: 22px 22px 18px;
      background: radial-gradient(circle at top right, rgba(15, 108, 189, 0.12), transparent 35%), #fff;
    }}
    .hero h1 {{
      margin: 0 0 6px;
      font-size: 1.28rem;
    }}
    .hero p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
    }}
    .meta-list {{
      padding: 18px 22px 22px;
      display: grid;
      gap: 14px;
    }}
    .meta-item strong {{
      display: block;
      font-size: 0.83rem;
      color: var(--muted);
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .meta-item div {{
      word-break: break-word;
      line-height: 1.5;
    }}
    .preview-card header,
    .viewer-card header {{
      padding: 18px 22px 14px;
      border-bottom: 1px solid var(--line);
    }}
    .preview-card h2,
    .viewer-card h2 {{
      margin: 0 0 4px;
      font-size: 1rem;
    }}
    .preview-card p,
    .viewer-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }}
    .preview-tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      padding: 14px 18px 0;
    }}
    .preview-tab {{
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: 999px;
      padding: 8px 12px;
      cursor: pointer;
      font-size: 0.88rem;
    }}
    .preview-tab.active {{
      background: var(--accent-soft);
      color: var(--accent);
      border-color: rgba(15, 108, 189, 0.18);
    }}
    .preview-body {{
      padding: 14px 18px 18px;
    }}
    .preview-pane.hidden {{
      display: none;
    }}
    .preview-meta {{
      color: var(--muted);
      margin-bottom: 10px;
      font-size: 0.86rem;
      word-break: break-word;
    }}
    pre {{
      margin: 0;
      padding: 14px;
      border-radius: 14px;
      background: #0f172a;
      color: #e2e8f0;
      overflow: auto;
      max-height: 420px;
      font-size: 0.82rem;
      line-height: 1.55;
    }}
    .viewer-card {{
      display: grid;
      grid-template-rows: auto 1fr;
      min-height: calc(100vh - 48px);
    }}
    .viewer-meta {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      color: var(--muted);
      font-size: 0.88rem;
      margin-top: 8px;
    }}
    iframe {{
      width: 100%;
      min-height: 0;
      border: 0;
      background: #fff;
    }}
    @media (max-width: 1100px) {{
      .shell {{
        grid-template-columns: 1fr;
      }}
      .viewer-card {{
        min-height: 900px;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="side">
      <section class="panel">
        <div class="hero">
          <h1>{title}</h1>
          <p>离线演示包。保留当前报告与轻量交互，不依赖本地环境、服务器接口或原始数据目录。</p>
        </div>
        <div class="meta-list">
          <div class="meta-item"><strong>导出时间</strong><div>{exported_at}</div></div>
          <div class="meta-item"><strong>报告生成时间</strong><div>{generated_at}</div></div>
          <div class="meta-item"><strong>Target Dir</strong><div>{target_dir}</div></div>
          <div class="meta-item"><strong>Report HTML</strong><div>{report_path}</div></div>
          <div class="meta-item"><strong>Review State</strong><div>{review_path}</div></div>
        </div>
      </section>

      <section class="panel preview-card">
        <header>
          <h2>文件预览</h2>
          <p>这里打包了演示用的关键文件，方便在别人的电脑上直接查看原始 HTML 和评注记录。</p>
        </header>
        <div class="preview-tabs">{preview_tabs}</div>
        <div class="preview-body">{preview_panes}</div>
      </section>
    </div>

    <section class="panel viewer-card">
      <header>
        <h2>报告预览</h2>
        <p>右侧直接嵌入现有 report.html。表格筛选、列显隐、日志展开等前端交互仍可使用。</p>
        <div class="viewer-meta">
          <span>报告文件：{report_name}</span>
          <span>评注：离线模式下走浏览器本地保存</span>
        </div>
      </header>
      <iframe id="report-frame" title="offline-demo-report"></iframe>
    </section>
  </div>

  <script>
    const reportHtml = {report_srcdoc};
    document.getElementById("report-frame").srcdoc = reportHtml;
    const tabs = Array.from(document.querySelectorAll("[data-preview-tab]"));
    const panes = Array.from(document.querySelectorAll("[data-preview-pane]"));
    tabs.forEach((tab) => {{
      tab.addEventListener("click", () => {{
        const index = tab.dataset.previewTab;
        tabs.forEach((node) => node.classList.toggle("active", node === tab));
        panes.forEach((pane) => pane.classList.toggle("hidden", pane.dataset.previewPane !== index));
      }});
    }});
  </script>
</body>
</html>
"""
