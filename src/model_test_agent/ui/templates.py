"""HTML templates for the thin local browser UI."""

from __future__ import annotations

import json


def render_app(defaults: dict[str, str]) -> str:
    """Return the single-page UI used to launch and monitor runs."""
    defaults_json = json.dumps(defaults, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Model Test Agent UI</title>
<style>
  :root {{
    --ink: #17324d;
    --accent: #0f766e;
    --accent-soft: #dff5f1;
    --danger: #b33a3a;
    --paper: #f5f7fb;
    --card: #ffffff;
    --line: #d7dee8;
    --muted: #607081;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    background:
      radial-gradient(circle at top left, rgba(15, 118, 110, 0.08), transparent 30%),
      linear-gradient(180deg, #f7fafc 0%, #eef3f8 100%);
    color: var(--ink);
  }}
  .page {{
    max-width: 1280px;
    margin: 0 auto;
    padding: 28px 24px 40px;
  }}
  .hero {{
    display: flex;
    justify-content: space-between;
    gap: 24px;
    align-items: flex-start;
    margin-bottom: 24px;
  }}
  .hero-copy h1 {{
    margin: 0 0 8px;
    font-size: 2rem;
    letter-spacing: -0.02em;
  }}
  .hero-copy p {{
    margin: 0;
    color: var(--muted);
    max-width: 720px;
    line-height: 1.6;
  }}
  .hero-note {{
    min-width: 280px;
    background: rgba(255, 255, 255, 0.82);
    border: 1px solid rgba(15, 50, 77, 0.08);
    border-radius: 18px;
    padding: 16px 18px;
    backdrop-filter: blur(10px);
    box-shadow: 0 18px 40px rgba(23, 50, 77, 0.08);
  }}
  .hero-note strong {{ display: block; margin-bottom: 6px; }}
  .layout {{
    display: grid;
    grid-template-columns: 420px minmax(0, 1fr);
    gap: 20px;
    align-items: start;
  }}
  .panel {{
    background: var(--card);
    border: 1px solid rgba(23, 50, 77, 0.08);
    border-radius: 20px;
    box-shadow: 0 18px 50px rgba(23, 50, 77, 0.08);
    overflow: hidden;
  }}
  .panel-header {{
    padding: 18px 20px 14px;
    border-bottom: 1px solid var(--line);
  }}
  .panel-header h2 {{
    margin: 0 0 6px;
    font-size: 1rem;
  }}
  .panel-header p {{
    margin: 0;
    color: var(--muted);
    line-height: 1.5;
    font-size: 0.92rem;
  }}
  .panel-body {{
    padding: 18px 20px 20px;
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
    color: var(--muted);
    margin-top: 6px;
    line-height: 1.5;
  }}
  .input-row {{
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px;
  }}
  input[type="text"],
  input[type="number"],
  select {{
    width: 100%;
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 11px 12px;
    font: inherit;
    background: #fcfdff;
    color: var(--ink);
  }}
  input:focus,
  select:focus {{
    outline: none;
    border-color: rgba(15, 118, 110, 0.55);
    box-shadow: 0 0 0 4px rgba(15, 118, 110, 0.12);
  }}
  .stack-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
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
    padding: 11px 16px;
    font: inherit;
    cursor: pointer;
  }}
  .btn-primary {{
    background: linear-gradient(135deg, var(--accent) 0%, #0b5f67 100%);
    color: #fff;
    font-weight: 700;
    box-shadow: 0 12px 24px rgba(15, 118, 110, 0.2);
  }}
  .btn-secondary {{
    background: #eff5f9;
    color: var(--ink);
  }}
  .status-grid {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin-bottom: 18px;
  }}
  .mini-card {{
    border-radius: 16px;
    padding: 14px 16px;
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
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 18px;
  }}
  .step-pill {{
    border-radius: 999px;
    padding: 8px 12px;
    background: #eef4f8;
    color: var(--muted);
    font-size: 0.85rem;
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
    border-radius: 16px;
    padding: 16px;
    background: #fbfdff;
    min-height: 130px;
    line-height: 1.6;
  }}
  .log-box.error {{
    border-color: rgba(179, 58, 58, 0.2);
    background: #fff7f7;
    color: var(--danger);
  }}
  .viewer-shell {{
    margin-top: 18px;
    border: 1px solid var(--line);
    border-radius: 18px;
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
    width: min(880px, 100%);
    max-height: 80vh;
    overflow: hidden;
    background: #fff;
    border-radius: 20px;
    box-shadow: 0 20px 50px rgba(0,0,0,0.18);
    display: flex;
    flex-direction: column;
  }}
  .browser-card header,
  .browser-card footer {{
    padding: 16px 18px;
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
  .muted {{
    color: var(--muted);
  }}
  @media (max-width: 980px) {{
    .layout {{ grid-template-columns: 1fr; }}
    .hero {{ flex-direction: column; }}
    .stack-2, .status-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="hero-copy">
        <h1>Model Test Agent UI</h1>
        <p>Use a remote-friendly launch page to pick server-side directories, run the full analysis pipeline, and open the interactive report with shared review comments.</p>
      </div>
      <aside class="hero-note">
        <strong>SSH-friendly</strong>
        <div class="muted">Open this UI through an SSH tunnel. The directory browser operates on the server filesystem, not your local browser filesystem.</div>
      </aside>
    </section>

    <section class="layout">
      <div class="panel">
        <div class="panel-header">
          <h2>Run Setup</h2>
          <p>Pick the target model directory first. Other paths are optional and can stay empty for a simple demo run.</p>
        </div>
        <div class="panel-body">
          <form id="run-form">
            <div class="field">
              <label for="target_dir">Target Dir</label>
              <div class="input-row">
                <input id="target_dir" name="target_dir" type="text" required>
                <button type="button" class="btn-secondary" data-browse-for="target_dir">Browse</button>
              </div>
              <small>Each first-level subdirectory is treated as one model directory.</small>
            </div>
            <div class="field">
              <label for="output_dir">Output Dir</label>
              <div class="input-row">
                <input id="output_dir" name="output_dir" type="text">
                <button type="button" class="btn-secondary" data-browse-for="output_dir">Browse</button>
              </div>
            </div>
            <div class="field">
              <label for="codebase_root">Codebase Root</label>
              <div class="input-row">
                <input id="codebase_root" name="codebase_root" type="text">
                <button type="button" class="btn-secondary" data-browse-for="codebase_root">Browse</button>
              </div>
            </div>
            <div class="field">
              <label for="rag_dir">RAG Dir</label>
              <div class="input-row">
                <input id="rag_dir" name="rag_dir" type="text">
                <button type="button" class="btn-secondary" data-browse-for="rag_dir">Browse</button>
              </div>
            </div>
            <div class="field">
              <label for="target_layout_path">Target Layout Config</label>
              <input id="target_layout_path" name="target_layout_path" type="text">
            </div>
            <div class="field">
              <label for="llm_config_path">LLM Config</label>
              <input id="llm_config_path" name="llm_config_path" type="text">
            </div>
            <div class="field">
              <label for="docker_script_path">Docker Script</label>
              <input id="docker_script_path" name="docker_script_path" type="text">
            </div>
            <div class="stack-2">
              <div class="field">
                <label for="max_retries">Max Retries</label>
                <input id="max_retries" name="max_retries" type="number" min="0" max="10">
              </div>
              <div class="field">
                <label>&nbsp;</label>
                <label class="checkbox">
                  <input id="auto_fix" name="auto_fix" type="checkbox">
                  <span>Enable Auto Fix</span>
                </label>
              </div>
            </div>
            <button id="run-button" class="btn-primary" type="submit">Run Full Pipeline</button>
          </form>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <h2>Run Status</h2>
          <p>The UI keeps polling the current job. When the report is ready, it opens in-place and still supports shared comments.</p>
        </div>
        <div class="panel-body">
          <div class="status-grid">
            <div class="mini-card">
              <div class="label">Job</div>
              <div class="value" id="job-id">-</div>
            </div>
            <div class="mini-card">
              <div class="label">Status</div>
              <div class="value" id="job-status">Idle</div>
            </div>
            <div class="mini-card">
              <div class="label">Current Detail</div>
              <div class="value" id="job-detail">Waiting for input</div>
            </div>
          </div>

          <div class="step-strip" id="step-strip"></div>

          <div id="job-log" class="log-box">Pick a target directory and run the pipeline.</div>

          <div id="viewer-shell" class="viewer-shell" hidden>
            <div class="viewer-bar">
              <div>
                <strong>Interactive Report</strong>
                <div class="muted" id="report-meta"></div>
              </div>
              <a id="report-link" href="#" target="_blank" rel="noopener noreferrer">Open in new tab</a>
            </div>
            <iframe id="report-frame" title="Interactive report"></iframe>
          </div>
        </div>
      </div>
    </section>
  </div>

  <div class="browser" id="browser">
    <div class="browser-card">
      <header>
        <strong>Browse server directories</strong>
        <div class="muted">The selected path is resolved on the machine where the UI server is running.</div>
      </header>
      <div class="browser-body">
        <div class="field">
          <label for="browser-path">Current Path</label>
          <div class="input-row">
            <input id="browser-path" type="text">
            <button type="button" class="btn-secondary" id="browser-refresh">Open</button>
          </div>
        </div>
        <div class="browser-list" id="browser-list"></div>
      </div>
      <footer>
        <button type="button" class="btn-secondary" id="browser-cancel">Cancel</button>
        <button type="button" class="btn-primary" id="browser-choose">Use This Directory</button>
      </footer>
    </div>
  </div>

<script>
  const defaults = {defaults_json};
  const steps = ["extract", "source_context", "classification", "debug", "save_history", "report"];
  const form = document.getElementById("run-form");
  const runButton = document.getElementById("run-button");
  const jobIdNode = document.getElementById("job-id");
  const jobStatusNode = document.getElementById("job-status");
  const jobDetailNode = document.getElementById("job-detail");
  const jobLogNode = document.getElementById("job-log");
  const stepStrip = document.getElementById("step-strip");
  const viewerShell = document.getElementById("viewer-shell");
  const reportLink = document.getElementById("report-link");
  const reportFrame = document.getElementById("report-frame");
  const reportMeta = document.getElementById("report-meta");
  const browser = document.getElementById("browser");
  const browserPath = document.getElementById("browser-path");
  const browserList = document.getElementById("browser-list");
  let browserTarget = "";
  let selectedBrowserPath = "";
  let pollTimer = null;

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
    stepStrip.innerHTML = steps.map((step, index) => {{
      let className = "step-pill";
      if (snapshot.status === "completed" || snapshot.status === "failed") {{
        if (index + 1 < snapshot.step_index || (snapshot.status === "completed" && index + 1 <= snapshot.step_index)) {{
          className += " done";
        }}
      }}
      if (snapshot.status === "running" && step === snapshot.step_key) {{
        className += " active";
      }}
      return `<div class="${{className}}">${{step}}</div>`;
    }}).join("");
  }}

  function renderSnapshot(snapshot) {{
    jobIdNode.textContent = snapshot.job_id || "-";
    jobStatusNode.textContent = snapshot.status || "idle";
    jobDetailNode.textContent = snapshot.detail || "Waiting for input";
    jobLogNode.classList.toggle("error", snapshot.status === "failed");
    jobLogNode.textContent = snapshot.error || snapshot.detail || "Waiting for input";
    renderSteps(snapshot);

    if (snapshot.report_url) {{
      viewerShell.hidden = false;
      reportLink.href = snapshot.report_url;
      reportFrame.src = snapshot.report_url;
      reportMeta.textContent = snapshot.report_html_path || "";
    }}
    if (snapshot.status === "running") {{
      runButton.disabled = true;
      runButton.textContent = "Pipeline Running...";
    }} else {{
      runButton.disabled = false;
      runButton.textContent = "Run Full Pipeline";
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

  async function startRun(event) {{
    event.preventDefault();
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
    }};
    const response = await fetch("/api/run", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload),
    }});
    const result = await response.json();
    if (!response.ok) {{
      renderSnapshot({{ status: "failed", detail: "Unable to start", error: result.error || "Unknown error" }});
      return;
    }}
    viewerShell.hidden = true;
    renderSnapshot(result);
    schedulePoll();
  }}

  async function loadDirectory(pathValue) {{
    const response = await fetch(`/api/fs?path=${{encodeURIComponent(pathValue || "")}}`);
    const payload = await response.json();
    browserPath.value = payload.path || "";
    selectedBrowserPath = payload.path || "";
    browserList.innerHTML = "";

    if (payload.parent && payload.parent !== payload.path) {{
      const up = document.createElement("button");
      up.type = "button";
      up.className = "browser-item";
      up.innerHTML = `<strong>..</strong><span class="muted">${{payload.parent}}</span>`;
      up.addEventListener("click", () => void loadDirectory(payload.parent));
      browserList.appendChild(up);
    }}

    payload.directories.forEach((item) => {{
      const button = document.createElement("button");
      button.type = "button";
      button.className = "browser-item";
      button.innerHTML = `<strong>${{item.name}}</strong><span class="muted">${{item.path}}</span>`;
      button.addEventListener("click", () => void loadDirectory(item.path));
      browserList.appendChild(button);
    }});
  }}

  function openBrowser(targetField) {{
    browserTarget = targetField;
    browser.classList.add("open");
    const initialPath = document.getElementById(targetField).value.trim() || defaults[targetField] || "";
    void loadDirectory(initialPath);
  }}

  document.querySelectorAll("[data-browse-for]").forEach((button) => {{
    button.addEventListener("click", () => openBrowser(button.dataset.browseFor));
  }});
  document.getElementById("browser-refresh").addEventListener("click", () => void loadDirectory(browserPath.value.trim()));
  document.getElementById("browser-cancel").addEventListener("click", () => browser.classList.remove("open"));
  document.getElementById("browser-choose").addEventListener("click", () => {{
    if (browserTarget) {{
      document.getElementById(browserTarget).value = selectedBrowserPath;
    }}
    browser.classList.remove("open");
  }});
  form.addEventListener("submit", startRun);

  setDefaults();
  renderSnapshot({{ status: "idle", detail: "Waiting for input", error: "" }});
  void fetchSnapshot();
</script>
</body>
</html>"""
