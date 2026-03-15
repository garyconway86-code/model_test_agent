"""Background pipeline execution for the browser UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import os
from pathlib import Path
from threading import Lock, Thread
import time
from typing import Any, Callable
from uuid import uuid4

from model_test_agent.pipeline import PipelineEvent, PipelineExecutionError, run_main_pipeline


@dataclass
class JobSnapshot:
    """Serializable state for one UI-triggered pipeline run."""

    job_id: str = ""
    status: str = "idle"
    step_key: str = ""
    step_index: int = 0
    total_steps: int = 0
    detail: str = ""
    error: str = ""
    report_path: str = ""
    report_html_path: str = ""
    report_url: str = ""
    target_dir: str = ""
    pid: int = 0
    messages: list[str] = field(default_factory=list)
    started_at: float = 0.0
    step_started_at: float = 0.0
    step_elapsed_seconds: int = 0
    skip_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.step_started_at:
            data["step_elapsed_seconds"] = max(0, int(time.time() - self.step_started_at))
        return data


class PipelineJobRunner:
    """Run at most one pipeline job at a time for the local UI."""

    def __init__(self, report_url_builder: Callable[[str, str], str] | None = None) -> None:
        self._lock = Lock()
        self._jobs: dict[str, JobSnapshot] = {}
        self._latest_job_id = ""
        self._active_job_id = ""
        self._report_url_builder = report_url_builder or (lambda _job_id, _report_path: "")
        self._skip_requests: dict[str, set[str]] = {}

    def latest(self) -> JobSnapshot:
        with self._lock:
            if self._latest_job_id:
                return JobSnapshot(**self._jobs[self._latest_job_id].to_dict())
            return JobSnapshot()

    def get(self, job_id: str) -> JobSnapshot:
        with self._lock:
            snapshot = self._jobs.get(job_id)
            return JobSnapshot(**snapshot.to_dict()) if snapshot else JobSnapshot()

    def report_path_for(self, job_id: str) -> str:
        with self._lock:
            snapshot = self._jobs.get(job_id)
            return snapshot.report_html_path if snapshot else ""

    def start(self, config: dict[str, Any]) -> JobSnapshot:
        with self._lock:
            if self._active_job_id and self._jobs[self._active_job_id].status == "running":
                raise RuntimeError("A pipeline job is already running")
            job_id = uuid4().hex[:8]
            snapshot = JobSnapshot(
                job_id=job_id,
                status="running",
                detail="Queued",
                target_dir=str(config.get("target_dir", "") or ""),
                pid=os.getpid(),
                messages=["Queued pipeline run"],
                started_at=time.time(),
            )
            self._jobs[job_id] = snapshot
            self._latest_job_id = job_id
            self._active_job_id = job_id
            self._skip_requests[job_id] = set()

        thread = Thread(target=self._run_job, args=(job_id, dict(config)), daemon=True)
        thread.start()
        return self.get(job_id)

    def load_existing(self, target_dir: str, report_html_path: str, report_path: str = "") -> JobSnapshot:
        with self._lock:
            job_id = uuid4().hex[:8]
            report_html = str(Path(report_html_path).resolve())
            snapshot = JobSnapshot(
                job_id=job_id,
                status="completed",
                step_key="report",
                step_index=6,
                total_steps=6,
                detail="Loaded existing report",
                report_path=str(report_path),
                report_html_path=report_html,
                report_url=self._report_url_builder(job_id, report_html),
                target_dir=target_dir,
                pid=os.getpid(),
                messages=["Loaded existing report"],
                started_at=time.time(),
            )
            self._jobs[job_id] = snapshot
            self._latest_job_id = job_id
            return JobSnapshot(**snapshot.to_dict())

    def request_skip(self, step_key: str = "") -> JobSnapshot:
        with self._lock:
            if not self._active_job_id:
                raise RuntimeError("No pipeline job is running")
            snapshot = self._jobs[self._active_job_id]
            if snapshot.status != "running":
                raise RuntimeError("No pipeline job is running")
            current_step = snapshot.step_key or ""
            target_step = step_key or current_step
            if target_step not in {"source_context", "debug"}:
                raise RuntimeError("Current step does not support skip")
            if current_step and target_step != current_step:
                raise RuntimeError(f"Current step is {current_step}, cannot skip {target_step}")
            self._skip_requests.setdefault(self._active_job_id, set()).add(target_step)
            snapshot.skip_requested = True
            self._append_message(snapshot, f"SKIP {target_step}: 用户请求跳过，当前项完成后生效")
            return JobSnapshot(**snapshot.to_dict())

    def _run_job(self, job_id: str, config: dict[str, Any]) -> None:
        config["ui_progress_callback"] = lambda step_key, detail: self._update_progress(job_id, step_key, detail)
        config["ui_should_skip"] = lambda step_key: self._should_skip(job_id, step_key)

        def _on_event(event: PipelineEvent) -> None:
            with self._lock:
                snapshot = self._jobs[job_id]
                snapshot.status = "running"
                snapshot.step_key = event.step_key
                snapshot.step_index = event.step_index
                snapshot.total_steps = event.total_steps
                snapshot.detail = self._event_detail(event)
                if event.phase == "start":
                    snapshot.step_started_at = time.time()
                    snapshot.skip_requested = False
                self._append_message(snapshot, self._event_message(event))
                if event.phase == "error":
                    snapshot.error = event.error

        try:
            result = run_main_pipeline(config, on_event=_on_event)
        except PipelineExecutionError as exc:
            with self._lock:
                snapshot = self._jobs[job_id]
                snapshot.status = "failed"
                snapshot.error = str(exc.original_error)
                snapshot.detail = f"{exc.step_key} failed"
                self._append_message(snapshot, f"ERROR {exc.step_key}: {exc.original_error}")
                self._active_job_id = ""
                self._skip_requests.pop(job_id, None)
            return
        except Exception as exc:  # pragma: no cover - defensive fallback for UI threads
            with self._lock:
                snapshot = self._jobs[job_id]
                snapshot.status = "failed"
                snapshot.error = str(exc)
                snapshot.detail = "pipeline failed"
                self._append_message(snapshot, f"ERROR pipeline: {exc}")
                self._active_job_id = ""
                self._skip_requests.pop(job_id, None)
            return

        report_html_path = str(result.get("report_html_path", "") or "")
        report_path = str(result.get("report_path", "") or "")
        with self._lock:
            snapshot = self._jobs[job_id]
            snapshot.status = "completed"
            snapshot.step_key = "report"
            snapshot.step_index = snapshot.total_steps
            snapshot.detail = f"Completed · {len(result.get('report_rows', []))} report rows"
            snapshot.report_path = report_path
            snapshot.report_html_path = report_html_path
            snapshot.report_url = (
                self._report_url_builder(job_id, report_html_path) if report_html_path else ""
            )
            self._append_message(snapshot, snapshot.detail)
            self._active_job_id = ""
            self._skip_requests.pop(job_id, None)

    def _update_progress(self, job_id: str, step_key: str, detail: str) -> None:
        with self._lock:
            snapshot = self._jobs.get(job_id)
            if not snapshot or snapshot.status != "running":
                return
            snapshot.step_key = step_key
            snapshot.detail = detail
            self._append_message(snapshot, f"INFO {step_key}: {detail}")

    def _should_skip(self, job_id: str, step_key: str) -> bool:
        with self._lock:
            return step_key in self._skip_requests.get(job_id, set())

    @staticmethod
    def _append_message(snapshot: JobSnapshot, message: str) -> None:
        text = (message or "").strip()
        if not text:
            return
        if snapshot.messages and snapshot.messages[-1] == text:
            return
        snapshot.messages.append(text)
        if len(snapshot.messages) > 120:
            snapshot.messages = snapshot.messages[-120:]

    @staticmethod
    def _event_detail(event: PipelineEvent) -> str:
        if event.phase == "start":
            return f"Running {event.step_key}"
        state = event.state
        if event.step_key == "extract":
            return f"{len(state.get('errors', []))} errors · {len(state.get('models', []))} models"
        if event.step_key == "source_context":
            errors = state.get("errors", [])
            resolved = sum(1 for item in errors if getattr(item, "error_file_path", "Unknown") != "Unknown")
            return f"{resolved}/{len(errors)} source paths resolved"
        if event.step_key == "classification":
            return f"{len(state.get('error_groups', {}))} categories"
        if event.step_key == "debug":
            return f"{len(state.get('debug_results', []))} debug results"
        if event.step_key == "save_history":
            return "History updated"
        if event.step_key == "report":
            return f"{len(state.get('report_rows', []))} report rows"
        return event.step_key

    @staticmethod
    def _event_message(event: PipelineEvent) -> str:
        detail = PipelineJobRunner._event_detail(event)
        if event.phase == "start":
            return f"START {event.step_key}: {detail}"
        if event.phase == "error":
            return f"ERROR {event.step_key}: {event.error}"
        return f"DONE {event.step_key}: {detail}"
