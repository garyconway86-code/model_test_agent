"""Lightweight local server for interactive report review state.

The server keeps the deployment simple:
  - serves the generated HTML report from its output directory
  - stores shared review state in ``<report>.review.json`` beside the report
  - requires only the Python standard library
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlsplit


@dataclass(frozen=True)
class ReportServerInfo:
    """Runtime information for a report review server."""

    server: ThreadingHTTPServer
    host: str
    port: int
    report_path: Path

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def report_url(self) -> str:
        return f"{self.base_url}/{quote(self.report_path.name)}"

    @property
    def review_state_path(self) -> Path:
        return review_state_path(self.report_path)


def review_state_path(report_path: str | Path) -> Path:
    """Return the shared review-state JSON path for one HTML report."""
    path = Path(report_path).resolve()
    return path.with_suffix(".review.json")


def create_report_server(
    report_path: str | Path,
    host: str = "127.0.0.1",
    port: int = 7860,
) -> ReportServerInfo:
    """Create a local HTTP server for one generated report."""
    resolved_report = Path(report_path).resolve()
    if not resolved_report.is_file():
        raise FileNotFoundError(f"Report file not found: {resolved_report}")

    handler = partial(_ReportRequestHandler, directory=str(resolved_report.parent), report_path=resolved_report)
    server = ThreadingHTTPServer((host, port), handler)
    actual_port = server.server_address[1]
    return ReportServerInfo(server=server, host=host, port=actual_port, report_path=resolved_report)


def load_review_state(review_path: str | Path) -> dict[str, Any]:
    """Load persisted review state from disk."""
    path = Path(review_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_review_state(review_path: str | Path, state: dict[str, Any]) -> None:
    """Persist normalized review state to disk."""
    path = Path(review_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_review_state(path)
    normalized = _normalize_review_state(state)
    merged = _merge_review_state(existing, normalized)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _normalize_review_state(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = state.get("rows") if "rows" in state else state
    if not isinstance(rows, dict):
        return {}

    normalized: dict[str, dict[str, Any]] = {}
    for row_key, value in rows.items():
        if not isinstance(row_key, str):
            continue
        normalized_entry = _normalize_review_entry(value)
        if normalized_entry:
            normalized[row_key] = normalized_entry
    return normalized


def _normalize_review_entry(value: Any) -> dict[str, Any]:
    checked_by = ""
    comment = ""
    updated_at = ""
    history: list[dict[str, str]] = []
    if isinstance(value, str):
        checked_by = value.strip()
    elif isinstance(value, dict):
        checked_by = str(value.get("checkedBy", "") or "").strip()
        comment = str(value.get("comment", "") or "")
        updated_at = str(value.get("updatedAt", "") or "")
        raw_history = value.get("history", [])
        if isinstance(raw_history, list):
            for item in raw_history:
                if not isinstance(item, dict):
                    continue
                history.append({
                    "updatedAt": str(item.get("updatedAt", "") or ""),
                    "checkedBy": str(item.get("checkedBy", "") or "").strip(),
                    "comment": str(item.get("comment", "") or ""),
                })
    if not checked_by and not comment.strip() and not history:
        return {}
    entry: dict[str, Any] = {"checkedBy": checked_by, "comment": comment}
    if updated_at:
        entry["updatedAt"] = updated_at
    if history:
        entry["history"] = history
    return entry


def _merge_review_state(
    existing: dict[str, Any],
    incoming: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged = dict(existing) if isinstance(existing, dict) else {}
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for row_key, next_entry in incoming.items():
        previous = _normalize_review_entry(merged.get(row_key, {}))
        history = list(previous.get("history", []))
        changed = (
            previous.get("checkedBy", "") != next_entry.get("checkedBy", "")
            or previous.get("comment", "") != next_entry.get("comment", "")
        )
        if changed:
            history.append({
                "updatedAt": now,
                "checkedBy": str(next_entry.get("checkedBy", "") or ""),
                "comment": str(next_entry.get("comment", "") or ""),
            })
            next_entry["updatedAt"] = now
        elif previous.get("updatedAt"):
            next_entry["updatedAt"] = previous["updatedAt"]
        if history:
            next_entry["history"] = history[-20:]
        merged[row_key] = next_entry
    return merged


class _ReportRequestHandler(SimpleHTTPRequestHandler):
    """Serve a generated report and accept review-state updates."""

    def __init__(self, *args: Any, directory: str, report_path: Path, **kwargs: Any) -> None:
        self._report_path = report_path
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        request = urlsplit(self.path)
        if request.path == "/":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", f"/{quote(self._report_path.name)}")
            self.end_headers()
            return
        if request.path == "/api/review-state":
            self._handle_get_review_state(request.query)
            return
        super().do_GET()

    def do_PUT(self) -> None:  # noqa: N802
        request = urlsplit(self.path)
        if request.path != "/api/review-state":
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")
            return
        self._handle_put_review_state(request.query)

    def _handle_get_review_state(self, query: str) -> None:
        try:
            report_path = self._resolve_report_from_query(query)
        except FileNotFoundError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Report not found"})
            return
        except PermissionError:
            self._write_json(HTTPStatus.FORBIDDEN, {"error": "Report path is outside the served directory"})
            return
        payload = {
            "rows": load_review_state(review_state_path(report_path)),
            "review_path": str(review_state_path(report_path)),
        }
        self._write_json(HTTPStatus.OK, payload)

    def _handle_put_review_state(self, query: str) -> None:
        try:
            report_path = self._resolve_report_from_query(query)
        except FileNotFoundError:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "Report not found"})
            return
        except PermissionError:
            self._write_json(HTTPStatus.FORBIDDEN, {"error": "Report path is outside the served directory"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except json.JSONDecodeError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid JSON payload"})
            return

        normalized = _normalize_review_state(payload if isinstance(payload, dict) else {})
        save_review_state(review_state_path(report_path), {"rows": normalized})
        self._write_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "rows": normalized,
                "review_path": str(review_state_path(report_path)),
            },
        )

    def _resolve_report_from_query(self, query: str) -> Path:
        params = parse_qs(query)
        raw_report = params.get("report", [f"/{self._report_path.name}"])[0]
        relative_path = unquote(raw_report).lstrip("/") or self._report_path.name
        candidate = (self._report_path.parent / relative_path).resolve()
        base_dir = self._report_path.parent.resolve()
        try:
            candidate.relative_to(base_dir)
        except ValueError as exc:
            raise PermissionError(f"Report path escapes server root: {candidate}") from exc
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        return candidate

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the CLI output clean unless the user explicitly debugs the server.
        return
