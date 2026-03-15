"""Background pipeline execution for the browser UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import Lock, Thread
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PipelineJobRunner:
    """Run at most one pipeline job at a time for the local UI."""

    def __init__(self, report_url_builder: Callable[[str, str], str] | None = None) -> None:
        self._lock = Lock()
        self._jobs: dict[str, JobSnapshot] = {}
        self._latest_job_id = ""
        self._active_job_id = ""
        self._report_url_builder = report_url_builder or (lambda _job_id, _report_path: "")

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
            )
            self._jobs[job_id] = snapshot
            self._latest_job_id = job_id
            self._active_job_id = job_id

        thread = Thread(target=self._run_job, args=(job_id, dict(config)), daemon=True)
        thread.start()
        return self.get(job_id)

    def _run_job(self, job_id: str, config: dict[str, Any]) -> None:
        def _on_event(event: PipelineEvent) -> None:
            with self._lock:
                snapshot = self._jobs[job_id]
                snapshot.status = "running"
                snapshot.step_key = event.step_key
                snapshot.step_index = event.step_index
                snapshot.total_steps = event.total_steps
                snapshot.detail = self._event_detail(event)
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
                self._active_job_id = ""
            return
        except Exception as exc:  # pragma: no cover - defensive fallback for UI threads
            with self._lock:
                snapshot = self._jobs[job_id]
                snapshot.status = "failed"
                snapshot.error = str(exc)
                snapshot.detail = "pipeline failed"
                self._active_job_id = ""
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
            self._active_job_id = ""

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
