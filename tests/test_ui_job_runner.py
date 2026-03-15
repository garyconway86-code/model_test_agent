"""Tests for the browser UI job runner."""

from __future__ import annotations

import time

from model_test_agent.pipeline import PipelineEvent, PipelineExecutionError
from model_test_agent.ui.job_runner import PipelineJobRunner


class TestPipelineJobRunner:
    def test_start_runs_pipeline_and_builds_report_url(self, monkeypatch) -> None:
        def _fake_run(initial_state, on_event=None):
            if on_event:
                on_event(PipelineEvent("start", "extract", 1, 6, dict(initial_state)))
                on_event(PipelineEvent("finish", "extract", 1, 6, {"errors": [], "models": []}))
                on_event(PipelineEvent("finish", "report", 6, 6, {"report_rows": [1, 2]}))
            return {
                "report_path": "/tmp/report.xlsx",
                "report_html_path": "/tmp/report.html",
                "report_rows": [1, 2],
            }

        monkeypatch.setattr("model_test_agent.ui.job_runner.run_main_pipeline", _fake_run)
        runner = PipelineJobRunner(report_url_builder=lambda job_id, _path: f"/reports/{job_id}/report.html")

        snapshot = runner.start({"target_dir": "/tmp/models"})
        for _ in range(20):
            current = runner.get(snapshot.job_id)
            if current.status == "completed":
                break
            time.sleep(0.01)

        assert current.status == "completed"
        assert current.report_url.endswith("/report.html")
        assert current.target_dir == "/tmp/models"

    def test_start_rejects_parallel_run(self, monkeypatch) -> None:
        def _slow_run(initial_state, on_event=None):
            if on_event:
                on_event(PipelineEvent("start", "extract", 1, 6, dict(initial_state)))
            time.sleep(0.2)
            return {}

        monkeypatch.setattr("model_test_agent.ui.job_runner.run_main_pipeline", _slow_run)
        runner = PipelineJobRunner()
        runner.start({"target_dir": "/tmp/models"})

        try:
            runner.start({"target_dir": "/tmp/models-2"})
        except RuntimeError as exc:
            assert "already running" in str(exc)
        else:
            raise AssertionError("Expected the second run to be rejected")

    def test_start_records_pipeline_failure(self, monkeypatch) -> None:
        def _broken_run(_initial_state, on_event=None):
            raise PipelineExecutionError("extract", RuntimeError("boom"))

        monkeypatch.setattr("model_test_agent.ui.job_runner.run_main_pipeline", _broken_run)
        runner = PipelineJobRunner()

        snapshot = runner.start({"target_dir": "/tmp/models"})
        for _ in range(20):
            current = runner.get(snapshot.job_id)
            if current.status == "failed":
                break
            time.sleep(0.01)

        assert current.status == "failed"
        assert current.error == "boom"

    def test_request_skip_marks_running_job(self, monkeypatch) -> None:
        def _slow_run(initial_state, on_event=None):
            if on_event:
                on_event(PipelineEvent("start", "source_context", 2, 6, dict(initial_state)))
            time.sleep(0.2)
            return {}

        monkeypatch.setattr("model_test_agent.ui.job_runner.run_main_pipeline", _slow_run)
        runner = PipelineJobRunner()
        snapshot = runner.start({"target_dir": "/tmp/models"})
        time.sleep(0.05)

        updated = runner.request_skip("source_context")

        assert updated.skip_requested is True
        assert any("SKIP source_context" in message for message in updated.messages)

    def test_start_uses_selected_subgraph_mode(self, monkeypatch) -> None:
        def _unexpected_full(*args, **kwargs):
            raise AssertionError("full pipeline should not run for classify mode")

        def _fake_subset(initial_state, step_keys, on_event=None):
            assert initial_state["mode"] == "classify"
            assert step_keys == ["extract", "source_context", "classification"]
            if on_event:
                on_event(PipelineEvent("start", "classification", 3, 3, dict(initial_state)))
                on_event(PipelineEvent("finish", "classification", 3, 3, {"error_groups": {"shape_mismatch": []}}))
            return {"error_groups": {"shape_mismatch": []}}

        monkeypatch.setattr("model_test_agent.ui.job_runner.run_main_pipeline", _unexpected_full)
        monkeypatch.setattr("model_test_agent.ui.job_runner.run_pipeline_steps", _fake_subset)
        runner = PipelineJobRunner()

        snapshot = runner.start({"target_dir": "/tmp/models", "mode": "classify"})
        for _ in range(20):
            current = runner.get(snapshot.job_id)
            if current.status == "completed":
                break
            time.sleep(0.01)

        assert current.status == "completed"
        assert current.mode == "classify"
        assert current.detail == "Completed · 1 categories"
