"""HTML templates for the thin local browser UI."""

from __future__ import annotations

import json
import os
from pathlib import Path


_DEFAULT_HISTORY_PATH = Path(__file__).resolve().parents[3] / "history" / "cases.json"


def render_app(defaults: dict[str, str]) -> str:
    """Return the single-page UI used to launch and monitor runs."""
    defaults_json = json.dumps(defaults, ensure_ascii=False)
    history_path = str(_DEFAULT_HISTORY_PATH)
    process_pid = os.getpid()
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Model Debug Agent</title>
<style>
  :root {{
    --ink: #17324d;
    --accent: #0f766e;
    --accent-soft: #dff5f1;
    --danger: #b33a3a;
    --paper: #f4f7fb;
    --card: #ffffff;
    --line: #d6dee8;
    --muted: #617284;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: "IBM Plex Sans", "PingFang SC", "Segoe UI", sans-serif;
    background:
      radial-gradient(circle at top left, rgba(15, 118, 110, 0.07), transparent 32%),
      linear-gradient(180deg, #f8fafc 0%, #eef3f8 100%);
    color: var(--ink);
  }}
  .page {{
    max-width: 1360px;
    margin: 0 auto;
    padding: 24px;
  }}
  .topbar {{
    display: block;
    margin-bottom: 20px;
  }}
  .topbar h1 {{
    margin: 0 0 6px;
    font-size: 1.7rem;
    letter-spacing: -0.02em;
  }}
  .topbar p {{
    margin: 0;
    color: var(--muted);
    max-width: 760px;
    line-height: 1.55;
  }}
  .layout {{
    display: grid;
    grid-template-columns: 440px minmax(0, 1fr);
    gap: 18px;
    align-items: start;
  }}
  .stack {{
    display: grid;
    gap: 18px;
  }}
  .panel {{
    background: var(--card);
    border: 1px solid rgba(23, 50, 77, 0.08);
    border-radius: 18px;
    box-shadow: 0 18px 46px rgba(23, 50, 77, 0.08);
    overflow: hidden;
  }}
  .panel-header {{
    padding: 16px 18px 12px;
    border-bottom: 1px solid var(--line);
  }}
  .panel-header h2 {{
    margin: 0 0 6px;
    font-size: 1rem;
  }}
  .panel-header p {{
    margin: 0;
    color: var(--muted);
    font-size: 0.92rem;
    line-height: 1.5;
  }}
  .panel-body {{
    padding: 16px 18px 18px;
  }}
  .field {{
    margin-bottom: 14px;
  }}
  .field label {{
    display: block;
    margin-bottom: 6px;
    font-weight: 600;
  }}
  .field small {{
    display: block;
    margin-top: 6px;
    color: var(--muted);
    line-height: 1.5;
  }}
  .layout-note {{
    margin-bottom: 14px;
    padding: 12px 14px;
    border-radius: 14px;
    background: #f8fbfd;
    border: 1px solid rgba(23, 50, 77, 0.08);
  }}
  .layout-note strong {{
    display: block;
    margin-bottom: 8px;
  }}
  .layout-tree {{
    margin-top: 8px;
    padding: 10px 12px;
    border-radius: 10px;
    background: #f2f6fb;
    color: #304050;
    font-size: 0.85rem;
    line-height: 1.55;
    white-space: pre-wrap;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }}
  .input-row {{
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    gap: 8px;
  }}
  .stack-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }}
  input[type="text"],
  input[type="number"],
  textarea {{
    width: 100%;
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 11px 12px;
    font: inherit;
    background: #fcfdff;
    color: var(--ink);
  }}
  textarea {{
    min-height: 320px;
    resize: vertical;
    line-height: 1.5;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.9rem;
  }}
  input:focus,
  textarea:focus {{
    outline: none;
    border-color: rgba(15, 118, 110, 0.55);
    box-shadow: 0 0 0 4px rgba(15, 118, 110, 0.12);
  }}
  .checkbox {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding-top: 4px;
    color: var(--ink);
  }}
  button {{
    border: 0;
    border-radius: 999px;
    padding: 10px 15px;
    font: inherit;
    cursor: pointer;
  }}
  .btn-primary {{
    background: linear-gradient(135deg, var(--accent) 0%, #0c6660 100%);
    color: #fff;
    font-weight: 700;
    box-shadow: 0 10px 22px rgba(15, 118, 110, 0.18);
  }}
  .btn-secondary {{
    background: #eef4f8;
    color: var(--ink);
  }}
  .btn-link {{
    background: transparent;
    color: var(--accent);
    padding: 0;
    border-radius: 0;
    font-weight: 700;
  }}
  .status-grid {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-bottom: 16px;
  }}
  .mini-card {{
    border-radius: 14px;
    padding: 14px 15px;
    background: #f8fbfd;
    border: 1px solid rgba(23, 50, 77, 0.06);
  }}
  .mini-card .label {{
    color: var(--muted);
    font-size: 0.84rem;
    margin-bottom: 8px;
  }}
  .mini-card .value {{
    font-weight: 700;
    word-break: break-word;
  }}
  .step-strip {{
    display: flex;
    gap: 8px;
    flex-wrap: nowrap;
    margin-bottom: 16px;
    align-items: center;
  }}
  .step-legend {{
    display: flex;
    flex-wrap: nowrap;
    margin-bottom: 10px;
    gap: 8px;
  }}
  .legend-chip {{
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 10px 12px;
    border-radius: 12px;
    font-size: 0.84rem;
    background: #f6f9fc;
    border: 1px solid rgba(23, 50, 77, 0.08);
    color: var(--muted);
    flex: 0 0 auto;
  }}
  .legend-copy {{
    display: grid;
    gap: 2px;
    min-width: 0;
  }}
  .legend-copy strong {{
    color: var(--ink);
    font-size: 0.86rem;
  }}
  .legend-copy span {{
    overflow-wrap: anywhere;
    word-break: break-word;
  }}
  .legend-mark {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 18px;
    height: 18px;
    padding: 0 6px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    background: rgba(23, 50, 77, 0.08);
    color: var(--ink);
  }}
  .legend-mark.llm {{
    background: rgba(15, 118, 110, 0.12);
    color: var(--accent);
  }}
  .step-arrow {{
    color: var(--muted);
    font-size: 0.92rem;
    align-self: center;
  }}
  .step-pill {{
    border-radius: 999px;
    padding: 7px 11px;
    background: #eef4f8;
    color: var(--muted);
    font-size: 0.84rem;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    flex: 0 0 auto;
  }}
  .step-pill .step-label {{
    font-weight: 600;
  }}
  .step-pill[data-tooltip] {{
    position: relative;
    cursor: help;
  }}
  .step-pill[data-tooltip]::after {{
    content: attr(data-tooltip);
    position: absolute;
    left: 0;
    bottom: calc(100% + 10px);
    width: min(320px, 72vw);
    padding: 10px 12px;
    border-radius: 12px;
    background: rgba(15, 23, 32, 0.96);
    color: #f4f8fb;
    white-space: pre-wrap;
    line-height: 1.55;
    font-size: 0.82rem;
    font-weight: 400;
    box-shadow: 0 12px 26px rgba(0, 0, 0, 0.2);
    opacity: 0;
    transform: translateY(6px);
    pointer-events: none;
    transition: opacity 0.18s ease, transform 0.18s ease;
    z-index: 10;
  }}
  .step-pill[data-tooltip]::before {{
    content: "";
    position: absolute;
    left: 16px;
    bottom: calc(100% + 4px);
    border-width: 6px;
    border-style: solid;
    border-color: rgba(15, 23, 32, 0.96) transparent transparent transparent;
    opacity: 0;
    transform: translateY(6px);
    transition: opacity 0.18s ease, transform 0.18s ease;
    pointer-events: none;
    z-index: 10;
  }}
  .step-pill[data-tooltip]:hover::after,
  .step-pill[data-tooltip]:hover::before {{
    opacity: 1;
    transform: translateY(0);
  }}
  .pill-mark {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 20px;
    height: 20px;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    background: rgba(23, 50, 77, 0.08);
    color: var(--ink);
  }}
  .pill-mark.llm {{
    background: rgba(15, 118, 110, 0.14);
    color: var(--accent);
  }}
  .step-pill.active {{
    background: var(--accent-soft);
    color: var(--accent);
    font-weight: 700;
  }}
  .step-pill.done {{
    background: #ebf7ee;
    color: #23754b;
  }}
  .log-box {{
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 14px;
    background: #fbfdff;
    min-height: 160px;
    max-height: 280px;
    line-height: 1.6;
    overflow: auto;
    white-space: pre-wrap;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.88rem;
  }}
  .log-box.error {{
    border-color: rgba(179, 58, 58, 0.2);
    background: #fff7f7;
    color: var(--danger);
  }}
  .health-panel {{
    margin-bottom: 14px;
    border: 1px solid rgba(23, 50, 77, 0.08);
    border-radius: 14px;
    background: #fbfdff;
    padding: 12px 14px;
  }}
  .health-toolbar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
  }}
  .health-summary {{
    font-size: 0.92rem;
    color: var(--muted);
  }}
  .health-list {{
    display: grid;
    gap: 8px;
  }}
  .health-item {{
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 10px;
    align-items: start;
    padding: 10px 12px;
    border-radius: 12px;
    background: #f6f9fc;
  }}
  .health-item.ok {{
    border: 1px solid rgba(35, 117, 75, 0.14);
  }}
  .health-item.bad {{
    border: 1px solid rgba(179, 58, 58, 0.14);
  }}
  .health-badge {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 48px;
    padding: 4px 8px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 700;
  }}
  .health-badge.ok {{
    background: #ebf7ee;
    color: #23754b;
  }}
  .health-badge.bad {{
    background: #fff1f1;
    color: var(--danger);
  }}
  .health-copy {{
    min-width: 0;
  }}
  .health-copy strong {{
    display: block;
    margin-bottom: 2px;
  }}
  .health-copy .muted {{
    overflow-wrap: anywhere;
    word-break: break-word;
  }}
  .health-impact {{
    margin-top: 6px;
    font-size: 0.84rem;
    line-height: 1.45;
    color: #51606f;
    overflow-wrap: anywhere;
    word-break: break-word;
  }}
  .health-meta {{
    font-size: 0.82rem;
    color: var(--muted);
    white-space: nowrap;
  }}
  .viewer-shell {{
    margin-top: 16px;
    border: 1px solid var(--line);
    border-radius: 16px;
    overflow: hidden;
    background: #fff;
  }}
  .viewer-bar {{
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: center;
    padding: 12px 14px;
    border-bottom: 1px solid var(--line);
    background: #f8fbfd;
  }}
  .viewer-bar a {{
    color: var(--accent);
    font-weight: 700;
    text-decoration: none;
  }}
  iframe {{
    width: 100%;
    min-height: 860px;
    border: 0;
    background: #fff;
  }}
  .meta-list {{
    display: grid;
    gap: 8px;
    margin-bottom: 12px;
  }}
  .meta-item {{
    padding: 10px 12px;
    border-radius: 12px;
    background: #f8fbfd;
    border: 1px solid rgba(23, 50, 77, 0.06);
    overflow-wrap: anywhere;
    word-break: break-word;
  }}
  .meta-item strong {{
    display: block;
    margin-bottom: 4px;
  }}
  #preview-path,
  .meta-item .muted {{
    overflow-wrap: anywhere;
    word-break: break-word;
  }}
  .editor-toolbar {{
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: center;
    margin-bottom: 12px;
  }}
  .editor-actions {{
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
  }}
  .browser {{
    position: fixed;
    inset: 0;
    display: none;
    align-items: center;
    justify-content: center;
    background: rgba(14, 26, 39, 0.32);
    padding: 24px;
  }}
  .browser.open {{ display: flex; }}
  .browser-card {{
    width: min(920px, 100%);
    max-height: 82vh;
    overflow: hidden;
    background: #fff;
    border-radius: 18px;
    box-shadow: 0 20px 50px rgba(0,0,0,0.18);
    display: flex;
    flex-direction: column;
  }}
  .browser-card header,
  .browser-card footer {{
    padding: 15px 18px;
    border-bottom: 1px solid var(--line);
  }}
  .browser-card footer {{
    border-bottom: 0;
    border-top: 1px solid var(--line);
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }}
  .browser-body {{
    padding: 16px 18px;
    overflow: auto;
  }}
  .browser-list {{
    display: grid;
    gap: 8px;
  }}
  .browser-item {{
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: center;
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 10px 12px;
    background: #fcfdff;
  }}
  .browser-item strong {{ word-break: break-all; }}
  .browser-item .type {{
    color: var(--muted);
    font-size: 0.85rem;
  }}
  .muted {{ color: var(--muted); }}
  @media (max-width: 1100px) {{
    .layout {{ grid-template-columns: 1fr; }}
    .stack-2, .status-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
  <div class="page">
    <section class="topbar">
      <div>
        <h1>Model Debug Agent | 智能体辅助日志分析</h1>
        <p>选择服务器上的模型目录，启动分析流程，查看报告并共享评注。</p>
      </div>
    </section>

    <section class="layout">
      <div class="stack">
        <div class="panel">
          <div class="panel-header">
            <h2>运行参数</h2>
            <p>必填的是模型目录。其余路径按需填写，字段都支持浏览服务器文件。</p>
          </div>
          <div class="panel-body">
            <form id="run-form">
              <input id="target_layout_path" name="target_layout_path" type="hidden">
              <input id="llm_config_path" name="llm_config_path" type="hidden">
              <div class="field">
                <label for="target_dir">模型目录</label>
                <div class="input-row">
                  <input id="target_dir" name="target_dir" type="text" required>
                  <button type="button" class="btn-secondary" data-browse-for="target_dir" data-browse-mode="dir">浏览</button>
                  <button type="button" class="btn-link" data-preview-for="target_dir" data-preview-mode="dir">查看</button>
                </div>
                <small>每个一级子目录视为一个模型目录。</small>
              </div>

              <div class="layout-note">
                <strong>目录约定</strong>
                <div class="muted">程序会按下面这类结构理解模型目录，主要用于说明输入格式。</div>
                <div class="layout-tree">target-dir/
  01-1_model/
    01-1_model.yaml
    package_info.json
    Converter_result/convert/.log/
      latest log file</div>
              </div>

              <div class="field">
                <label for="output_dir">输出目录</label>
                <div class="input-row">
                  <input id="output_dir" name="output_dir" type="text">
                  <button type="button" class="btn-secondary" data-browse-for="output_dir" data-browse-mode="dir">浏览</button>
                  <button type="button" class="btn-link" data-preview-for="output_dir" data-preview-mode="dir">查看</button>
                </div>
              </div>

              <div class="field">
                <label for="docker_script_path">Docker 进入脚本</label>
                <div class="input-row">
                  <input id="docker_script_path" name="docker_script_path" type="text">
                  <button type="button" class="btn-secondary" data-browse-for="docker_script_path" data-browse-mode="file">浏览</button>
                  <button type="button" class="btn-link" data-preview-for="docker_script_path" data-preview-mode="file">打开</button>
                </div>
                <small>如果日志和源码都在容器里，就用这个脚本进入 Docker 读源码、执行修复命令。直接在容器里跑时可以留空。</small>
              </div>

              <div class="field">
                <label for="codebase_root">源码目录</label>
                <div class="input-row">
                  <input id="codebase_root" name="codebase_root" type="text">
                  <button type="button" class="btn-secondary" data-browse-for="codebase_root" data-browse-mode="dir">浏览</button>
                  <button type="button" class="btn-link" data-preview-for="codebase_root" data-preview-mode="dir">查看</button>
                </div>
              </div>

              <div class="field">
                <label for="rag_dir">RAG 目录</label>
                <div class="input-row">
                  <input id="rag_dir" name="rag_dir" type="text">
                  <button type="button" class="btn-secondary" data-browse-for="rag_dir" data-browse-mode="dir">浏览</button>
                  <button type="button" class="btn-link" data-preview-for="rag_dir" data-preview-mode="dir">查看</button>
                </div>
              </div>

              <div class="stack-2">
                <div class="field">
                  <label for="max_retries">重试次数</label>
                  <input id="max_retries" name="max_retries" type="number" min="0" max="10">
                </div>
                <div class="field">
                  <label>&nbsp;</label>
                  <label class="checkbox">
                    <input id="auto_fix" name="auto_fix" type="checkbox">
                    <span>启用自动修复</span>
                  </label>
                </div>
              </div>

              <div class="editor-actions">
                <button id="run-button" class="btn-primary" type="submit">运行完整流程</button>
                <button id="force-run-button" class="btn-secondary" type="button">强制重跑</button>
              </div>
              <small>强制重跑会重新生成稳定报告，但会保留已有 Checked By 和 Comment。</small>
            </form>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <h2>文件预览</h2>
            <p>可以查看目录摘要，或打开并修改文本文件。这里也会说明所选路径在流程里的作用。</p>
          </div>
          <div class="panel-body">
            <div class="editor-toolbar">
              <div>
                <strong id="preview-title">未选择文件</strong>
                <div class="muted" id="preview-path">-</div>
              </div>
              <div class="editor-actions">
                <button type="button" class="btn-secondary" id="preview-refresh">刷新</button>
                <button type="button" class="btn-primary" id="preview-save">保存</button>
              </div>
            </div>
            <div class="meta-list" id="preview-meta">
              <div class="meta-item">
                <strong>说明</strong>
                <div class="muted">点开右侧字段旁的“打开”或“查看”后，这里会显示文件内容、目录摘要，以及这个路径在流程里的作用。</div>
              </div>
            </div>
            <textarea id="preview-content" placeholder="文件内容会显示在这里"></textarea>
          </div>
        </div>
      </div>

      <div class="stack">
        <div class="panel">
          <div class="panel-header">
            <h2>运行状态</h2>
            <p>运行过程中会持续刷新当前步骤。完成后会直接展示交互报告。</p>
          </div>
          <div class="panel-body">
            <div class="status-grid">
              <div class="mini-card">
                <div class="label">PID</div>
                <div class="value" id="job-id">-</div>
              </div>
              <div class="mini-card">
                <div class="label">状态</div>
                <div class="value" id="job-status">Idle</div>
              </div>
              <div class="mini-card">
                <div class="label">当前信息</div>
                <div class="value" id="job-detail">等待输入</div>
              </div>
              <div class="mini-card">
                <div class="label">本步耗时</div>
                <div class="value" id="job-elapsed">-</div>
              </div>
            </div>

            <div class="editor-actions" style="margin-bottom: 14px;">
              <button type="button" class="btn-secondary" id="skip-step-button" hidden>跳过当前步骤</button>
              <small id="skip-step-hint">源码定位和根因分析耗时较长时，可请求跳过当前步骤。</small>
            </div>

            <div class="health-panel">
              <div class="health-toolbar">
                <div>
                  <strong>LLM 健康度</strong>
                  <div class="health-summary" id="health-summary">正在检查...</div>
                </div>
                <button type="button" class="btn-secondary" id="health-refresh">刷新</button>
              </div>
              <div class="health-list" id="health-list">
                <div class="meta-item">
                  <strong>说明</strong>
                  <div class="muted">这里会显示当前 LLM / Embedding / Reranker 接口的可用性、模型名和延迟。Embedding / Reranker 不可用时会自动降级，不会阻断主流程。</div>
                </div>
              </div>
            </div>

            <div class="step-legend">
              <div class="legend-chip">
                <span class="legend-mark llm">LLM</span>
                <div class="legend-copy">
                  <strong>大模型节点</strong>
                  <span>错误分类、根因分析、自动修复</span>
                </div>
              </div>
              <div class="legend-chip">
                <span class="legend-mark">Tool</span>
                <div class="legend-copy">
                  <strong>工具节点</strong>
                  <span>日志提取、源码定位、历史写回、报告生成</span>
                </div>
              </div>
            </div>
            <div class="step-strip" id="step-strip"></div>
            <div id="job-log" class="log-box">选择模型目录后开始运行。</div>

            <div id="viewer-shell" class="viewer-shell" hidden>
              <div class="viewer-bar">
                <div>
                  <strong>交互报告</strong>
                  <div class="muted" id="report-meta"></div>
                </div>
                <a id="report-link" href="#" target="_blank" rel="noopener noreferrer">新窗口打开</a>
              </div>
              <iframe id="report-frame" title="交互报告"></iframe>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>

  <div class="browser" id="browser">
    <div class="browser-card">
      <header>
        <strong id="browser-title">浏览服务器文件</strong>
        <div class="muted" id="browser-desc">当前浏览的是服务器上的真实路径。</div>
      </header>
      <div class="browser-body">
        <div class="field">
          <label for="browser-path">当前路径</label>
          <div class="input-row">
            <input id="browser-path" type="text">
            <button type="button" class="btn-secondary" id="browser-refresh">打开</button>
            <span></span>
          </div>
        </div>
        <div class="browser-list" id="browser-list"></div>
      </div>
      <footer>
        <button type="button" class="btn-secondary" id="browser-cancel">取消</button>
        <button type="button" class="btn-primary" id="browser-choose">使用当前选中项</button>
      </footer>
    </div>
  </div>

<script>
  const defaults = {defaults_json};
  const appPid = {process_pid};
  const steps = ["extract", "source_context", "classification", "debug", "save_history", "report"];
  const form = document.getElementById("run-form");
  const runButton = document.getElementById("run-button");
  const forceRunButton = document.getElementById("force-run-button");
  const jobIdNode = document.getElementById("job-id");
  const jobStatusNode = document.getElementById("job-status");
  const jobDetailNode = document.getElementById("job-detail");
  const jobElapsedNode = document.getElementById("job-elapsed");
  const jobLogNode = document.getElementById("job-log");
  const skipStepButton = document.getElementById("skip-step-button");
  const skipStepHint = document.getElementById("skip-step-hint");
  const healthSummary = document.getElementById("health-summary");
  const healthList = document.getElementById("health-list");
  const healthRefreshButton = document.getElementById("health-refresh");
  const stepStrip = document.getElementById("step-strip");
  const viewerShell = document.getElementById("viewer-shell");
  const reportLink = document.getElementById("report-link");
  const reportFrame = document.getElementById("report-frame");
  const reportMeta = document.getElementById("report-meta");
  const browser = document.getElementById("browser");
  const browserTitle = document.getElementById("browser-title");
  const browserDesc = document.getElementById("browser-desc");
  const browserPath = document.getElementById("browser-path");
  const browserList = document.getElementById("browser-list");
  const previewTitle = document.getElementById("preview-title");
  const previewPath = document.getElementById("preview-path");
  const previewMeta = document.getElementById("preview-meta");
  const previewContent = document.getElementById("preview-content");
  const historyStorePath = {json.dumps(history_path, ensure_ascii=False)};
  const stepLabels = {{
    extract: "日志提取",
    source_context: "源码定位",
    classification: "错误分类",
    debug: "根因分析",
    save_history: "经验入库",
    report: "报告生成",
  }};
  const stepKinds = {{
    extract: "tool",
    source_context: "tool",
    classification: "llm",
    debug: "llm",
    save_history: "tool",
    report: "tool",
  }};
  let browserTarget = "";
  let browserMode = "dir";
  let selectedBrowserPath = "";
  let selectedBrowserType = "dir";
  let previewFilePath = "";
  let previewFileEditable = false;
  let pollTimer = null;
  let lookupTimer = null;
  let currentSnapshot = {{ status: "idle" }};

  function supportsSkip(stepKey) {{
    return stepKey === "source_context" || stepKey === "debug";
  }}

  function formatElapsed(seconds) {{
    const total = Math.max(0, Number(seconds || 0));
    if (!total) return "-";
    const mins = Math.floor(total / 60);
    const secs = total % 60;
    return mins ? `${{mins}}m ${{secs}}s` : `${{secs}}s`;
  }}

  function setDefaults() {{
    Object.entries(defaults).forEach(([key, value]) => {{
      const node = document.getElementById(key);
      if (!node) return;
      if (node.type === "checkbox") {{
        node.checked = Boolean(value);
      }} else {{
        node.value = value || "";
      }}
    }});
  }}

  function renderSteps(snapshot) {{
    const items = [];
    steps.forEach((step, index) => {{
      let className = "step-pill";
      const kind = stepKinds[step] || "tool";
      const label = kind === "llm" ? "LLM" : "Tool";
      const tooltip = stepTooltip(step);
      if (snapshot.status === "completed" || snapshot.status === "failed") {{
        if (index + 1 < snapshot.step_index || (snapshot.status === "completed" && index + 1 <= snapshot.step_index)) {{
          className += " done";
        }}
      }}
      if (snapshot.status === "running" && step === snapshot.step_key) {{
        className += " active";
      }}
      items.push(
        `<div class="${{className}}" data-tooltip="${{escapeHtml(tooltip)}}"><span class="pill-mark ${{kind}}">${{label}}</span><span class="step-label">${{stepLabels[step] || step}}</span></div>`
      );
      if (index < steps.length - 1) {{
        items.push('<div class="step-arrow">→</div>');
      }}
    }});
    stepStrip.innerHTML = items.join("");
  }}

  function escapeHtml(value) {{
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }}

  function stepTooltip(step) {{
    const targetDir = document.getElementById("target_dir").value.trim() || "(未选择模型目录)";
    const outputDir = document.getElementById("output_dir").value.trim() || "./output";
    const codebaseRoot = document.getElementById("codebase_root").value.trim() || "(未指定)";
    const dockerScript = document.getElementById("docker_script_path").value.trim() || "(未指定)";
    const ragDir = document.getElementById("rag_dir").value.trim() || "(未指定)";
    if (step === "extract") {{
      return `读取模型目录中的日志、配置和 package_info。\\n来源：${{targetDir}}\\n保存位置：仅内存，不单独落盘`;
    }}
    if (step === "source_context") {{
      return `从日志中提取报错路径，并尝试补源码上下文。\\n源码目录：${{codebaseRoot}}\\nDocker 脚本：${{dockerScript}}\\n保存位置：仅内存，不单独落盘`;
    }}
    if (step === "classification") {{
      return "调用大模型做错误分类。\\n输入：日志摘录、源码上下文\\n保存位置：仅内存，不单独落盘";
    }}
    if (step === "debug") {{
      return `调用大模型做根因分析和修复建议。\\n输入：分类结果、历史案例、RAG 资料\\nRAG 目录：${{ragDir}}\\n保存位置：仅内存，不单独落盘`;
    }}
    if (step === "save_history") {{
      return `把确认有效的经验案例写入本地经验库，供后续检索复用。\\n保存位置：${{historyStorePath}}`;
    }}
    if (step === "report") {{
      return `生成 HTML / XLSX 报告。\\n保存位置：${{outputDir}} 下当前模型目录对应的稳定报告目录`;
    }}
    return "";
  }}

  function renderSnapshot(snapshot) {{
    currentSnapshot = snapshot || {{ status: "idle" }};
    jobIdNode.textContent = String(snapshot.pid || appPid || "-");
    jobStatusNode.textContent = snapshot.status || "idle";
    jobDetailNode.textContent = snapshot.detail || "等待输入";
    jobElapsedNode.textContent = formatElapsed(snapshot.step_elapsed_seconds || 0);
    jobLogNode.classList.toggle("error", snapshot.status === "failed");
    const lines = Array.isArray(snapshot.messages) && snapshot.messages.length
      ? snapshot.messages
      : [snapshot.error || snapshot.detail || "等待输入"];
    jobLogNode.textContent = lines.join("\\n");
    jobLogNode.scrollTop = jobLogNode.scrollHeight;
    renderSteps(snapshot);

    if (snapshot.report_url) {{
      viewerShell.hidden = false;
      reportLink.href = snapshot.report_url;
      reportFrame.src = snapshot.report_url;
      reportMeta.textContent = snapshot.report_html_path || "";
    }} else {{
      viewerShell.hidden = true;
    }}
    if (snapshot.status === "running") {{
      runButton.disabled = true;
      forceRunButton.disabled = true;
      runButton.textContent = "运行中...";
      const skipSupported = supportsSkip(snapshot.step_key);
      skipStepButton.hidden = !skipSupported;
      skipStepButton.disabled = Boolean(snapshot.skip_requested);
      skipStepButton.textContent = snapshot.skip_requested ? "已请求跳过" : "跳过当前步骤";
      skipStepHint.textContent = skipSupported
        ? (snapshot.step_key === "source_context"
            ? "源码定位支持逐条跳过；若当前正在读取 Docker 内源码，会在当前读取结束后生效。"
            : "根因分析会在当前类别分析结束后跳过剩余类别。")
        : "源码定位和根因分析耗时较长时，可请求跳过当前步骤。";
    }} else {{
      runButton.disabled = false;
      forceRunButton.disabled = false;
      runButton.textContent = "运行完整流程";
      skipStepButton.hidden = true;
      skipStepButton.disabled = false;
      skipStepButton.textContent = "跳过当前步骤";
      skipStepHint.textContent = "源码定位和根因分析耗时较长时，可请求跳过当前步骤。";
    }}
  }}

  function renderHealth(payload) {{
    if (!payload || payload.ok === false) {{
      healthSummary.textContent = payload && payload.error ? `检查失败：${{payload.error}}` : "健康检查失败";
      healthList.innerHTML = `
        <div class="meta-item">
          <strong>状态</strong>
          <div class="muted">${{payload && payload.error ? escapeHtml(payload.error) : "无法获取健康状态"}}</div>
        </div>
      `;
      return;
    }}
    const healthy = Number(payload.healthy || 0);
    const total = Number(payload.total || 0);
    healthSummary.textContent = total ? `${{healthy}} / ${{total}} 可用` : "未配置可检查的接口";
    const profiles = Array.isArray(payload.profiles) ? payload.profiles : [];
    if (!profiles.length) {{
      healthList.innerHTML = `
        <div class="meta-item">
          <strong>状态</strong>
          <div class="muted">当前没有已配置的 LLM / Embedding / Reranker profile。</div>
        </div>
      `;
      return;
    }}
    healthList.innerHTML = profiles.map((item) => {{
      const ok = Boolean(item.ok);
      const badgeClass = ok ? "ok" : "bad";
      const badgeText = ok ? "OK" : "FAIL";
      const detail = item.error ? escapeHtml(item.error) : escapeHtml(item.model || "-");
      const latency = item.latency_ms ? `${{item.latency_ms}} ms` : "-";
      const impact = explainHealthImpact(item);
      return `
        <div class="health-item ${{badgeClass}}">
          <span class="health-badge ${{badgeClass}}">${{badgeText}}</span>
          <div class="health-copy">
            <strong>${{escapeHtml(item.profile || "-")}} · ${{escapeHtml(item.kind || "chat")}}</strong>
            <div class="muted">${{detail}}</div>
            <div class="health-impact">${{escapeHtml(impact)}}</div>
          </div>
          <div class="health-meta">${{latency}}</div>
        </div>
      `;
    }}).join("");
  }}

  function explainHealthImpact(item) {{
    const kind = String(item && item.kind || "chat");
    const profile = String(item && item.profile || "default");
    const ok = Boolean(item && item.ok);
    if (ok) {{
      if (kind === "embedding") {{
        return "影响：语义检索增强可用。系统措施：RAG 会优先使用 embedding 提升相似文档召回。";
      }}
      if (kind === "reranker") {{
        return "影响：检索结果重排可用。系统措施：召回结果会进一步优化排序。";
      }}
      if (profile === "classifier") {{
        return "影响：错误分类可正常执行。系统措施：分类节点直接使用该模型。";
      }}
      if (profile === "debugger") {{
        return "影响：根因分析和自动修复可正常执行。系统措施：调试节点直接使用该模型。";
      }}
      return "影响：依赖该模型的节点可正常执行。系统措施：按当前配置直接调用。";
    }}

    if (kind === "embedding") {{
      return "影响：语义检索增强暂不可用。系统措施：RAG 会自动退回本地词法检索，主流程仍可继续。";
    }}
    if (kind === "reranker") {{
      return "影响：重排增强暂不可用。系统措施：跳过 reranker，保留原始检索结果顺序，主流程仍可继续。";
    }}
    if (profile === "classifier") {{
      return "影响：错误分类会受影响。系统措施：主流程可继续，但分类结果与后续分析质量会下降。";
    }}
    if (profile === "debugger") {{
      return "影响：根因分析和自动修复会受影响。系统措施：日志提取、源码定位和报告生成仍可执行，但调试结论会缺失。";
    }}
    return "影响：依赖该模型的节点会受影响。系统措施：未依赖该 profile 的部分仍可继续执行。";
  }}

  async function fetchHealthStatus() {{
    healthRefreshButton.disabled = true;
    const llmConfigPath = document.getElementById("llm_config_path").value.trim();
    const suffix = llmConfigPath ? `?config_path=${{encodeURIComponent(llmConfigPath)}}` : "";
    try {{
      const response = await fetch(`/api/llm-health${{suffix}}`);
      const payload = await response.json();
      renderHealth(payload);
    }} catch (_error) {{
      renderHealth({{ ok: false, error: "无法连接健康检查接口" }});
    }} finally {{
      healthRefreshButton.disabled = false;
    }}
  }}

  async function fetchSnapshot() {{
    const response = await fetch("/api/job");
    const payload = await response.json();
    renderSnapshot(payload);
    if (payload.status === "running") {{
      schedulePoll();
    }}
  }}

  function schedulePoll() {{
    if (pollTimer) {{
      window.clearTimeout(pollTimer);
    }}
    pollTimer = window.setTimeout(() => {{
      void fetchSnapshot();
    }}, 1000);
  }}

  async function requestSkipCurrentStep() {{
    if (!currentSnapshot || !supportsSkip(currentSnapshot.step_key) || currentSnapshot.status !== "running") {{
      return;
    }}
    skipStepButton.disabled = true;
    const response = await fetch("/api/job/skip", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ step_key: currentSnapshot.step_key }}),
    }});
    const result = await response.json();
    if (result.snapshot) {{
      renderSnapshot(result.snapshot);
    }} else {{
      renderSnapshot(result);
    }}
    if (currentSnapshot.status === "running") {{
      schedulePoll();
    }}
  }}

  async function lookupExistingReport() {{
    if (currentSnapshot.status === "running") {{
      return;
    }}
    const targetDir = document.getElementById("target_dir").value.trim();
    const outputDir = document.getElementById("output_dir").value.trim() || "./output";
    if (!targetDir) {{
      return;
    }}
    const response = await fetch(
      `/api/report-lookup?target_dir=${{encodeURIComponent(targetDir)}}&output_dir=${{encodeURIComponent(outputDir)}}`
    );
    if (!response.ok) {{
      return;
    }}
    const payload = await response.json();
    if (payload.exists) {{
      renderSnapshot(payload);
    }}
  }}

  function scheduleExistingReportLookup() {{
    if (lookupTimer) {{
      window.clearTimeout(lookupTimer);
    }}
    lookupTimer = window.setTimeout(() => {{
      void lookupExistingReport();
    }}, 250);
  }}

  async function startRun(event, forceRerun = false) {{
    if (event) {{
      event.preventDefault();
    }}
    const payload = {{
      target_dir: document.getElementById("target_dir").value.trim(),
      output_dir: document.getElementById("output_dir").value.trim(),
      target_layout_path: document.getElementById("target_layout_path").value.trim(),
      codebase_root: document.getElementById("codebase_root").value.trim(),
      docker_script_path: document.getElementById("docker_script_path").value.trim(),
      rag_dir: document.getElementById("rag_dir").value.trim(),
      llm_config_path: document.getElementById("llm_config_path").value.trim(),
      auto_fix: document.getElementById("auto_fix").checked,
      max_retries: Number(document.getElementById("max_retries").value || "2"),
      force_rerun: forceRerun,
    }};
    const response = await fetch("/api/run", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload),
    }});
    const result = await response.json();
    if (!response.ok) {{
      if (result.snapshot) {{
        renderSnapshot(result.snapshot);
        if ((result.snapshot.status || "") === "running") {{
          schedulePoll();
        }}
        return;
      }}
      renderSnapshot({{ status: "failed", detail: "启动失败", error: result.error || "未知错误" }});
      return;
    }}
    viewerShell.hidden = true;
    renderSnapshot(result);
    schedulePoll();
  }}

  function openBrowser(targetField, mode) {{
    browserTarget = targetField;
    browserMode = mode;
    browserTitle.textContent = mode === "file" ? "选择文件" : "选择目录";
    browserDesc.textContent = mode === "file"
      ? "可选配置文件、Docker 脚本等服务器文件。"
      : "可选模型目录、输出目录、源码目录等服务器目录。";
    browser.classList.add("open");
    const initialPath = document.getElementById(targetField).value.trim() || defaults[targetField] || "";
    void loadBrowser(initialPath, mode);
  }}

  async function loadBrowser(pathValue, mode) {{
    const response = await fetch(`/api/fs?path=${{encodeURIComponent(pathValue || "")}}&mode=${{encodeURIComponent(mode)}}`);
    const payload = await response.json();
    browserPath.value = payload.path || "";
    selectedBrowserPath = payload.path || "";
    selectedBrowserType = "dir";
    browserList.innerHTML = "";

    if (payload.parent && payload.parent !== payload.path) {{
      const up = document.createElement("button");
      up.type = "button";
      up.className = "browser-item";
      up.innerHTML = `<strong>..</strong><span class="type">${{payload.parent}}</span>`;
      up.addEventListener("click", () => void loadBrowser(payload.parent, mode));
      browserList.appendChild(up);
    }}

    payload.entries.forEach((item) => {{
      const button = document.createElement("button");
      button.type = "button";
      button.className = "browser-item";
      button.innerHTML = `<strong>${{item.name}}</strong><span class="type">${{item.kind}} · ${{item.path}}</span>`;
      button.addEventListener("click", () => {{
        selectedBrowserPath = item.path;
        selectedBrowserType = item.kind;
        if (item.kind === "dir") {{
          void loadBrowser(item.path, mode);
        }}
      }});
      browserList.appendChild(button);
    }});
  }}

  async function openPreview(targetField, mode) {{
    const targetPath = document.getElementById(targetField).value.trim();
    if (!targetPath) {{
      previewTitle.textContent = "未选择文件";
      previewPath.textContent = "请先填写或浏览路径";
      previewMeta.innerHTML = `<div class="meta-item"><strong>提示</strong><div class="muted">当前字段还没有路径。</div></div>`;
      previewContent.value = "";
      previewFilePath = "";
      previewFileEditable = false;
      return;
    }}
    if (mode === "dir") {{
      const response = await fetch(`/api/fs?path=${{encodeURIComponent(targetPath)}}&mode=dir`);
      const payload = await response.json();
      previewTitle.textContent = "目录摘要";
      previewPath.textContent = payload.path || targetPath;
      previewMeta.innerHTML = `
        <div class="meta-item"><strong>目录</strong><div class="muted">${{payload.path || targetPath}}</div></div>
        <div class="meta-item"><strong>子目录数量</strong><div class="muted">${{payload.entries.filter(item => item.kind === "dir").length}}</div></div>
        <div class="meta-item"><strong>文件数量</strong><div class="muted">${{payload.entries.filter(item => item.kind === "file").length}}</div></div>
        <div class="meta-item"><strong>作用</strong><div class="muted">${{directoryHint(targetField)}}</div></div>
      `;
      previewContent.value = payload.entries.map(item => `${{item.kind}}  ${{item.path}}`).join("\\n");
      previewFilePath = "";
      previewFileEditable = false;
      previewContent.readOnly = true;
      return;
    }}

    const response = await fetch(`/api/file?path=${{encodeURIComponent(targetPath)}}`);
    const payload = await response.json();
    previewTitle.textContent = payload.name || "文件预览";
    previewPath.textContent = payload.path || targetPath;
    previewMeta.innerHTML = `
      <div class="meta-item"><strong>类型</strong><div class="muted">${{payload.kind || "file"}}</div></div>
      <div class="meta-item"><strong>大小</strong><div class="muted">${{payload.size || 0}} bytes</div></div>
      <div class="meta-item"><strong>作用</strong><div class="muted">${{fileHint(targetField)}}</div></div>
      <div class="meta-item"><strong>关键提示</strong><div class="muted">${{payload.hint || "无"}}</div></div>
    `;
    previewContent.value = payload.content || "";
    previewFilePath = payload.path || targetPath;
    previewFileEditable = Boolean(payload.editable);
    previewContent.readOnly = !previewFileEditable;
  }}

  async function savePreview() {{
    if (!previewFilePath || !previewFileEditable) {{
      return;
    }}
    const response = await fetch(`/api/file?path=${{encodeURIComponent(previewFilePath)}}`, {{
      method: "PUT",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ content: previewContent.value }}),
    }});
    const payload = await response.json();
    previewMeta.innerHTML = `
      <div class="meta-item"><strong>类型</strong><div class="muted">${{payload.kind || "file"}}</div></div>
      <div class="meta-item"><strong>大小</strong><div class="muted">${{payload.size || 0}} bytes</div></div>
      <div class="meta-item"><strong>状态</strong><div class="muted">保存成功</div></div>
    `;
  }}

  function directoryHint(targetField) {{
    if (targetField === "target_dir") return "主输入目录。程序会在这里按模型子目录发现日志和配置。";
    if (targetField === "output_dir") return "报告、图表和 HTML 页面都会输出到这里。";
    if (targetField === "codebase_root") return "用于按日志里的报错路径去匹配宿主机源码。";
    if (targetField === "rag_dir") return "放补充资料，例如 txt / md / xlsx，用于增强分析。";
    return "服务器目录。";
  }}

  function fileHint(targetField) {{
    if (targetField === "target_layout_path") return "定义目录规则：日志在哪，配置在哪，package_info 在哪。";
    if (targetField === "llm_config_path") return "定义分类、调试、embedding 调用哪个模型接口。";
    if (targetField === "docker_script_path") return "定义如何进入 Docker，例如 docker exec ... bash -lc。";
    return "服务器文件。";
  }}

  document.querySelectorAll("[data-browse-for]").forEach((button) => {{
    button.addEventListener("click", () => openBrowser(button.dataset.browseFor, button.dataset.browseMode));
  }});
  document.querySelectorAll("[data-preview-for]").forEach((button) => {{
    button.addEventListener("click", () => void openPreview(button.dataset.previewFor, button.dataset.previewMode));
  }});
  document.getElementById("browser-refresh").addEventListener("click", () => void loadBrowser(browserPath.value.trim(), browserMode));
  document.getElementById("browser-cancel").addEventListener("click", () => browser.classList.remove("open"));
  document.getElementById("browser-choose").addEventListener("click", () => {{
    if (browserMode === "file" && selectedBrowserType !== "file") {{
      return;
    }}
    if (browserTarget) {{
      document.getElementById(browserTarget).value = selectedBrowserPath;
      if (browserTarget === "target_dir" || browserTarget === "output_dir") {{
        scheduleExistingReportLookup();
      }}
    }}
    browser.classList.remove("open");
  }});
  document.getElementById("preview-refresh").addEventListener("click", () => {{
    const candidates = [
      ["target_layout_path", "file"],
      ["llm_config_path", "file"],
      ["docker_script_path", "file"],
      ["target_dir", "dir"],
      ["output_dir", "dir"],
      ["codebase_root", "dir"],
      ["rag_dir", "dir"],
    ];
    const active = candidates.find(([id]) => document.getElementById(id).value.trim() === previewFilePath)
      || candidates.find(([id]) => document.getElementById(id).value.trim() === previewPath.textContent.trim());
    if (active) {{
      void openPreview(active[0], active[1]);
    }}
  }});
  document.getElementById("preview-save").addEventListener("click", () => void savePreview());
  document.getElementById("target_dir").addEventListener("change", scheduleExistingReportLookup);
  document.getElementById("target_dir").addEventListener("blur", scheduleExistingReportLookup);
  document.getElementById("output_dir").addEventListener("change", scheduleExistingReportLookup);
  document.getElementById("output_dir").addEventListener("blur", scheduleExistingReportLookup);
  healthRefreshButton.addEventListener("click", () => void fetchHealthStatus());
  skipStepButton.addEventListener("click", () => void requestSkipCurrentStep());
  form.addEventListener("submit", (event) => void startRun(event, false));
  forceRunButton.addEventListener("click", () => void startRun(null, true));

  setDefaults();
  renderSnapshot({{ status: "idle", detail: "等待输入", error: "" }});
  void fetchHealthStatus();
  void lookupExistingReport();
  void fetchSnapshot();
</script>
</body>
</html>"""
