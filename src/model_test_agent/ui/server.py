"""Remote-friendly local HTTP UI for running the pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit

from model_test_agent.llm.client import check_all_profiles
from model_test_agent.tools.report_paths import report_artifacts
from model_test_agent.tools.report_server import load_review_state, review_state_path, save_review_state
from model_test_agent.ui.job_runner import PipelineJobRunner
from model_test_agent.ui.templates import render_app


@dataclass(frozen=True)
class UIServerInfo:
    """Runtime information for the browser UI server."""

    server: ThreadingHTTPServer
    host: str
    port: int

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


def create_ui_server(
    host: str = "127.0.0.1",
    port: int = 7860,
    defaults: dict[str, str] | None = None,
) -> UIServerInfo:
    """Create the remote-friendly launch UI server."""
    app = _UIServerApp(defaults=defaults or {})

    class _Handler(_UIServerRequestHandler):
        _app = app

    server = ThreadingHTTPServer((host, port), _Handler)
    actual_port = server.server_address[1]
    return UIServerInfo(server=server, host=host, port=actual_port)


class _UIServerApp:
    def __init__(self, defaults: dict[str, str]) -> None:
        self.defaults = defaults
        self.runner = PipelineJobRunner(report_url_builder=self.report_url)

    @staticmethod
    def report_url(job_id: str, report_path: str) -> str:
        filename = Path(report_path).name
        return f"/reports/{quote(job_id)}/{quote(filename)}"

    def report_path_from_route(self, route_path: str) -> Path:
        clean_path = unquote(route_path).lstrip("/")
        parts = Path(clean_path).parts
        if len(parts) != 3 or parts[0] != "reports":
            raise FileNotFoundError(route_path)
        job_id = parts[1]
        filename = parts[2]
        report_path = self.runner.report_path_for(job_id)
        if not report_path:
            raise FileNotFoundError(route_path)
        resolved = Path(report_path).resolve()
        if resolved.name != filename:
            raise FileNotFoundError(route_path)
        return resolved


class _UIServerRequestHandler(BaseHTTPRequestHandler):
    """Serve the launch UI, directory browser, job status, and reports."""

    _app: _UIServerApp

    def do_GET(self) -> None:  # noqa: N802
        request = urlsplit(self.path)
        if request.path == "/":
            self._write_html(HTTPStatus.OK, render_app(self._app.defaults))
            return
        if request.path == "/api/fs":
            self._handle_fs(request.query)
            return
        if request.path == "/api/file":
            self._handle_get_file(request.query)
            return
        if request.path == "/api/job":
            self._write_json(HTTPStatus.OK, self._app.runner.latest().to_dict())
            return
        if request.path == "/api/llm-health":
            self._handle_llm_health(request.query)
            return
        if request.path == "/api/report-lookup":
            self._handle_report_lookup(request.query)
            return
        if request.path == "/api/review-state":
            self._handle_get_review_state(request.query)
            return
        if request.path.startswith("/reports/"):
            self._handle_report(request.path)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        request = urlsplit(self.path)
        if request.path == "/api/job/skip":
            self._handle_skip_job()
            return
        if request.path != "/api/run":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        payload = self._read_json_body()
        if payload is None:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON payload"})
            return
        target_dir = str(payload.get("target_dir", "") or "").strip()
        if not target_dir:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "target_dir is required"})
            return
        config = {
            "target_dir": target_dir,
            "output_dir": str(payload.get("output_dir", "") or "./output"),
            "llm_config_path": str(payload.get("llm_config_path", "") or ""),
            "target_layout_path": str(payload.get("target_layout_path", "") or ""),
            "codebase_root": str(payload.get("codebase_root", "") or ""),
            "docker_script_path": str(payload.get("docker_script_path", "") or ""),
            "rag_dir": str(payload.get("rag_dir", "") or ""),
            "auto_fix": bool(payload.get("auto_fix", False)),
            "max_retries": int(payload.get("max_retries", 2) or 2),
            "retry_count": 0,
        }
        force_rerun = bool(payload.get("force_rerun", False))
        if not force_rerun:
            existing = self._existing_report_snapshot(config)
            if existing is not None:
                self._write_json(HTTPStatus.OK, existing.to_dict())
                return
        try:
            snapshot = self._app.runner.start(config)
        except RuntimeError as exc:
            self._write_json(
                HTTPStatus.CONFLICT,
                {
                    "error": str(exc),
                    "snapshot": self._app.runner.latest().to_dict(),
                },
            )
            return
        self._write_json(HTTPStatus.ACCEPTED, snapshot.to_dict())

    def _handle_skip_job(self) -> None:
        payload = self._read_json_body() or {}
        step_key = str(payload.get("step_key", "") or "").strip()
        try:
            snapshot = self._app.runner.request_skip(step_key=step_key)
        except RuntimeError as exc:
            self._write_json(HTTPStatus.CONFLICT, {"error": str(exc), "snapshot": self._app.runner.latest().to_dict()})
            return
        self._write_json(HTTPStatus.OK, snapshot.to_dict())

    def do_PUT(self) -> None:  # noqa: N802
        request = urlsplit(self.path)
        if request.path == "/api/review-state":
            self._handle_put_review_state(request.query)
            return
        if request.path == "/api/file":
            self._handle_put_file(request.query)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def _handle_fs(self, query: str) -> None:
        params = parse_qs(query)
        requested = str(params.get("path", [""])[0] or "")
        mode = str(params.get("mode", ["dir"])[0] or "dir")
        current = Path(requested).expanduser() if requested else Path.cwd()
        if current.is_file():
            current = current.parent
        current = current.resolve()
        if not current.exists():
            self._write_json(HTTPStatus.NOT_FOUND, {"error": f"Path not found: {current}"})
            return
        entries = []
        for item in sorted(current.iterdir(), key=lambda entry: (not entry.is_dir(), entry.name.lower())):
            if item.is_dir():
                entries.append({"name": item.name or str(item), "path": str(item.resolve()), "kind": "dir"})
            elif mode == "file":
                entries.append({"name": item.name or str(item), "path": str(item.resolve()), "kind": "file"})
        self._write_json(
            HTTPStatus.OK,
            {
                "path": str(current),
                "parent": str(current.parent if current.parent != current else current),
                "entries": entries,
            },
        )

    def _handle_report_lookup(self, query: str) -> None:
        params = parse_qs(query)
        target_dir = str(params.get("target_dir", [""])[0] or "").strip()
        output_dir = str(params.get("output_dir", ["./output"])[0] or "./output").strip()
        if not target_dir:
            self._write_json(HTTPStatus.OK, {"exists": False})
            return
        artifacts = report_artifacts(output_dir, target_dir)
        exists = artifacts["html"].is_file()
        payload = {
            "exists": exists,
            "report_html_path": str(artifacts["html"]),
            "report_path": str(artifacts["xlsx"]),
            "review_path": str(artifacts["review"]),
        }
        if exists:
            snapshot = self._app.runner.load_existing(target_dir, str(artifacts["html"]), str(artifacts["xlsx"]))
            payload.update(snapshot.to_dict())
        self._write_json(HTTPStatus.OK, payload)

    def _handle_llm_health(self, query: str) -> None:
        params = parse_qs(query)
        config_path = str(params.get("config_path", [""])[0] or "").strip()
        try:
            if config_path:
                results = check_all_profiles(config_path=config_path, timeout=6)
            else:
                results = check_all_profiles(timeout=6)
        except Exception as exc:
            self._write_json(HTTPStatus.OK, {"ok": False, "error": str(exc), "profiles": []})
            return
        healthy = sum(1 for item in results if item.get("ok"))
        payload = {
            "ok": True,
            "profiles": results,
            "healthy": healthy,
            "total": len(results),
        }
        self._write_json(HTTPStatus.OK, payload)

    def _handle_get_file(self, query: str) -> None:
        try:
            path = self._resolve_any_path(query)
        except FileNotFoundError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "File not found"})
            return
        if not path.is_file():
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Path is not a file"})
            return
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        self._write_json(
            HTTPStatus.OK,
            {
                "path": str(path),
                "name": path.name,
                "size": path.stat().st_size,
                "kind": path.suffix or "file",
                "editable": True,
                "hint": self._file_hint(path, content),
                "content": content,
            },
        )

    def _handle_put_file(self, query: str) -> None:
        try:
            path = self._resolve_any_path(query)
        except FileNotFoundError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "File not found"})
            return
        payload = self._read_json_body()
        if payload is None:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON payload"})
            return
        if not path.is_file():
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Path is not a file"})
            return
        content = str(payload.get("content", ""))
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        self._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "path": str(path),
                "name": path.name,
                "size": path.stat().st_size,
                "kind": path.suffix or "file",
            },
        )

    def _handle_report(self, route_path: str) -> None:
        try:
            report_path = self._app.report_path_from_route(route_path)
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND, "Report not found")
            return
        try:
            body = report_path.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Unable to read report")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_get_review_state(self, query: str) -> None:
        try:
            report_path = self._report_path_from_query(query)
        except FileNotFoundError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Report not found"})
            return
        payload = {
            "rows": load_review_state(review_state_path(report_path)),
            "review_path": str(review_state_path(report_path)),
        }
        self._write_json(HTTPStatus.OK, payload)

    def _handle_put_review_state(self, query: str) -> None:
        try:
            report_path = self._report_path_from_query(query)
        except FileNotFoundError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Report not found"})
            return
        payload = self._read_json_body()
        if payload is None:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON payload"})
            return
        save_review_state(review_state_path(report_path), payload)
        self._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "rows": load_review_state(review_state_path(report_path)),
                "review_path": str(review_state_path(report_path)),
            },
        )

    def _existing_report_snapshot(self, config: dict[str, Any]):
        target_dir = str(config.get("target_dir", "") or "").strip()
        if not target_dir:
            return None
        artifacts = report_artifacts(str(config.get("output_dir", "./output") or "./output"), target_dir)
        if not artifacts["html"].is_file():
            return None
        return self._app.runner.load_existing(target_dir, str(artifacts["html"]), str(artifacts["xlsx"]))

    def _report_path_from_query(self, query: str) -> Path:
        params = parse_qs(query)
        route_path = str(params.get("report", [""])[0] or "")
        if not route_path:
            raise FileNotFoundError("Missing report path")
        return self._app.report_path_from_route(route_path)

    def _resolve_any_path(self, query: str) -> Path:
        params = parse_qs(query)
        raw_path = str(params.get("path", [""])[0] or "")
        if not raw_path:
            raise FileNotFoundError("Missing path")
        resolved = Path(raw_path).expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(resolved)
        return resolved

    @staticmethod
    def _file_hint(path: Path, content: str) -> str:
        if path.suffix in {".yaml", ".yml"}:
            lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]
            return lines[0][:120] if lines else "YAML 配置文件"
        if path.suffix == ".json":
            return "JSON 配置文件"
        if path.suffix == ".sh":
            commands = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]
            return commands[0][:120] if commands else "Shell 脚本"
        return "可直接编辑的文本文件"

    def _read_json_body(self) -> dict[str, Any] | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        raw_body = self.rfile.read(content_length)
        try:
            return json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except json.JSONDecodeError:
            return None

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, status: HTTPStatus, html_body: str) -> None:
        body = html_body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return
