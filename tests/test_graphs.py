"""Tests for graph construction (no LLM calls — structure only)."""

from pathlib import Path

from model_test_agent.graphs.classification_subgraph import build_classification_subgraph
from model_test_agent.graphs.debug_subgraph import build_debug_subgraph
from model_test_agent.graphs.main_graph import _extract, _report, build_main_graph
from model_test_agent.graphs.snr_subgraph import build_snr_subgraph
from model_test_agent.state import DebugResult, ErrorEntry, FixStatus, ModelInfo


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

    def test_classification_subgraph_forwards_llm_config_path(self, monkeypatch) -> None:
        captured = {}

        class DummySkill:
            def __init__(self, llm_config_path=None):
                captured["llm_config_path"] = llm_config_path

            def run(self, errors, models=None):
                return errors

        monkeypatch.setattr(
            "model_test_agent.graphs.classification_subgraph.ErrorClassifierSkill",
            DummySkill,
        )

        graph = build_classification_subgraph().compile()
        graph.invoke({
            "errors": [ErrorEntry(model_name="m1", line_number=1, message="oops")],
            "models": [],
            "error_groups": {},
            "llm_config_path": "/tmp/llm-alt.yaml",
        })

        assert captured["llm_config_path"] == "/tmp/llm-alt.yaml"

    def test_debug_subgraph_preserves_successful_results_across_retries(self, monkeypatch) -> None:
        analyzed_categories = []
        executed_commands = []

        class DummyRetriever:
            def __init__(self, config_path=None):
                self.config_path = config_path

            def find_similar(self, category, key_log="", top_k=3):
                return []

        class DummySkill:
            def __init__(self, llm_config_path=None):
                assert llm_config_path == "/tmp/llm-alt.yaml"

            def run(self, error_groups, models=None, history_per_category=None):
                analyzed_categories.append(sorted(error_groups))
                results = []
                for category in error_groups:
                    command = "fix-success" if category == "ok" else "fix-fail"
                    results.append(DebugResult(error_category=category, fix_command=command))
                return results

        class DummyOutcome:
            def __init__(self, success):
                self.success = success
                self.output = "done" if success else "failed"

        def _run_fix(self, command):
            executed_commands.append(command)
            return DummyOutcome(success=command == "fix-success")

        monkeypatch.setattr("model_test_agent.graphs.debug_subgraph.SemanticRetriever", DummyRetriever)
        monkeypatch.setattr("model_test_agent.graphs.debug_subgraph.DebugAnalyzerSkill", DummySkill)
        monkeypatch.setattr("model_test_agent.tools.docker_executor.DockerExecutor.run", _run_fix)

        graph = build_debug_subgraph().compile()
        result = graph.invoke({
            "error_groups": {
                "ok": [ErrorEntry(model_name="m1", line_number=1, message="ok")],
                "bad": [ErrorEntry(model_name="m2", line_number=2, message="bad")],
            },
            "models": [],
            "debug_results": [],
            "retry_count": 0,
            "max_retries": 1,
            "auto_fix": True,
            "llm_config_path": "/tmp/llm-alt.yaml",
        })

        assert analyzed_categories == [["bad", "ok"], ["bad"]]
        assert executed_commands == ["fix-success", "fix-fail", "fix-fail"]
        assert result["retry_count"] == 1
        assert {item.error_category: item.fix_status for item in result["debug_results"]} == {
            "ok": FixStatus.SUCCESS,
            "bad": FixStatus.FAILED,
        }

    def test_report_node_returns_html_path(self, monkeypatch, tmp_path) -> None:
        package_info = tmp_path / "package_info.json"
        package_info.write_text('{"package_name": "demo-kit", "version": "1.2.3"}', encoding="utf-8")

        class DummyGenerator:
            def __init__(self, output_dir="."):
                self.output_dir = output_dir

            def generate_xlsx(self, rows):
                return tmp_path / "report.xlsx"

            def generate_html(self, rows, summary=None, agent_info=None):
                self.summary = summary
                self.agent_info = agent_info
                self.rows = rows
                return tmp_path / "report.html"

        monkeypatch.setattr("model_test_agent.graphs.main_graph.ReportGenerator", DummyGenerator)

        result = _report({
            "errors": [
                ErrorEntry(
                    model_name="m1",
                    line_number=1,
                    message="shape mismatch",
                    log_path="/tmp/m1.log",
                    category="shape_mismatch",
                )
            ],
            "models": [
                ModelInfo(
                    name="m1",
                    config_path=str(tmp_path / "model.yaml"),
                    package_info_path=str(package_info),
                ),
                ModelInfo(
                    name="m2",
                    config_path=str(tmp_path / "m2.yaml"),
                ),
            ],
            "debug_results": [],
        })

        assert result["report_path"].endswith("report.xlsx")
        assert result["report_html_path"].endswith("report.html")
        assert "report_rows" in result
        assert result["report_rows"][0].log_path == "/tmp/m1.log"
        assert any(row.model_name == "m2" and row.error_category == "no_error" for row in result["report_rows"])

    def test_extract_uses_configured_log_paths_before_directory_scan(self, monkeypatch, tmp_path) -> None:
        explicit_log = tmp_path / "Models_35" / "01-1_yolo" / "run_001" / "convert.log"
        explicit_log.parent.mkdir(parents=True)
        explicit_log.write_text("[ERROR] unsupported dtype\n", encoding="utf-8")

        monkeypatch.setattr(
            "model_test_agent.graphs.main_graph.ConfigReader.read_target_directory",
            lambda self, path: [
                ModelInfo(
                    name="01-1_yolo",
                    log_path=str(explicit_log),
                    config_path=str(tmp_path / "Models_35" / "01-1_yolo" / "config.yaml"),
                )
            ],
        )
        monkeypatch.setattr(
            "model_test_agent.graphs.main_graph.LogExtractor.extract_from_target_directory",
            lambda self, path: (_ for _ in ()).throw(AssertionError("directory scan should not be used")),
        )

        result = _extract({"target_dir": str(tmp_path / "Models_35")})

        assert len(result["errors"]) == 1
        assert result["errors"][0].model_name == "01-1_yolo"
