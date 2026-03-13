"""Tests for the imperative CLI pipeline runner."""

from model_test_agent.pipeline import PipelineExecutionError, PipelineStep, run_main_pipeline


class TestPipelineRunner:
    def test_run_main_pipeline_updates_state_in_order(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "model_test_agent.pipeline._build_steps",
            lambda: [
                PipelineStep("extract", lambda state: {"errors": ["e1"]}),
                PipelineStep("report", lambda state: {"report_path": f"{len(state['errors'])}.xlsx"}),
            ],
        )

        events = []
        result = run_main_pipeline({"errors": []}, on_event=events.append)

        assert result["errors"] == ["e1"]
        assert result["report_path"] == "1.xlsx"
        assert [event.phase for event in events] == ["start", "finish", "start", "finish"]

    def test_run_main_pipeline_wraps_step_failures(self, monkeypatch) -> None:
        def _fail(state):
            raise ValueError("broken")

        monkeypatch.setattr(
            "model_test_agent.pipeline._build_steps",
            lambda: [PipelineStep("debug", _fail)],
        )

        try:
            run_main_pipeline({})
        except PipelineExecutionError as exc:
            assert exc.step_key == "debug"
            assert str(exc.original_error) == "broken"
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("PipelineExecutionError was not raised")
