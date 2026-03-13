"""Tests for graph construction (no LLM calls — structure only)."""

from model_test_agent.graphs.classification_subgraph import build_classification_subgraph
from model_test_agent.graphs.debug_subgraph import build_debug_subgraph
from model_test_agent.graphs.main_graph import _report, build_main_graph
from model_test_agent.graphs.snr_subgraph import build_snr_subgraph
from model_test_agent.state import DebugResult, ErrorEntry, FixStatus


class TestGraphConstruction:
    """Verify that all graphs compile without errors."""

    def test_classification_subgraph_compiles(self) -> None:
        graph = build_classification_subgraph()
        compiled = graph.compile()
        assert compiled is not None

    def test_debug_subgraph_compiles(self) -> None:
        graph = build_debug_subgraph()
        compiled = graph.compile()
        assert compiled is not None

    def test_snr_subgraph_compiles(self) -> None:
        graph = build_snr_subgraph()
        compiled = graph.compile()
        assert compiled is not None

    def test_main_graph_compiles(self) -> None:
        graph = build_main_graph(compile=True)
        assert graph is not None

    def test_main_graph_uncompiled(self) -> None:
        graph = build_main_graph(compile=False)
        # Should be a StateGraph, not compiled
        assert hasattr(graph, "compile")

    def test_classification_subgraph_does_not_duplicate_errors(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "model_test_agent.skills.error_classifier.ErrorClassifierSkill.run",
            lambda self, errors, models=None: errors,
        )
        graph = build_classification_subgraph().compile()
        errors = [ErrorEntry(model_name="resnet50", line_number=1, message="shape mismatch")]

        result = graph.invoke({"errors": errors, "models": [], "error_groups": {}})

        assert len(result["errors"]) == 1
        assert result["errors"][0].model_name == "resnet50"

    def test_debug_subgraph_skips_fix_execution_when_disabled(self, monkeypatch) -> None:
        def _fake_run(self, error_groups, models=None, history_per_category=None):
            return [DebugResult(error_category="shape_mismatch", fix_command="echo repair")]

        def _unexpected_run(self, command):
            raise AssertionError("DockerExecutor.run should not be called when auto_fix=False")

        monkeypatch.setattr(
            "model_test_agent.skills.debug_analyzer.DebugAnalyzerSkill.run",
            _fake_run,
        )
        monkeypatch.setattr(
            "model_test_agent.tools.docker_executor.DockerExecutor.run",
            _unexpected_run,
        )

        graph = build_debug_subgraph().compile()
        result = graph.invoke({
            "error_groups": {"shape_mismatch": [ErrorEntry(model_name="m1", line_number=1, message="oops")]},
            "models": [],
            "debug_results": [],
            "retry_count": 0,
            "max_retries": 2,
            "auto_fix": False,
        })

        assert len(result["debug_results"]) == 1
        assert result["debug_results"][0].fix_status == FixStatus.SKIPPED

    def test_report_node_returns_html_path(self, monkeypatch, tmp_path) -> None:
        class DummyGenerator:
            def __init__(self, output_dir="."):
                self.output_dir = output_dir

            def generate_xlsx(self, rows):
                return tmp_path / "report.xlsx"

            def generate_html(self, rows):
                return tmp_path / "report.html"

        monkeypatch.setattr("model_test_agent.graphs.main_graph.ReportGenerator", DummyGenerator)

        result = _report({
            "errors": [ErrorEntry(model_name="m1", line_number=1, message="shape mismatch", category="shape_mismatch")],
            "models": [],
            "debug_results": [],
        })

        assert result["report_path"].endswith("report.xlsx")
        assert result["report_html_path"].endswith("report.html")
        assert "report_rows" in result
