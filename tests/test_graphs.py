"""Tests for graph construction (no LLM calls — structure only)."""

from pathlib import Path

from model_test_agent.graphs.classification_subgraph import build_classification_subgraph
from model_test_agent.graphs.debug_subgraph import build_debug_subgraph
from model_test_agent.graphs.main_graph import (
    _enrich_source_context,
    _extract,
    _report,
    _summarize_suggested_fixes,
    build_main_graph,
)
from model_test_agent.graphs.snr_subgraph import build_snr_subgraph
from model_test_agent.state import DebugResult, ErrorEntry, FixStatus, ModelInfo
from model_test_agent.tools.report_paths import report_output_dir


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
            "rag_dir": "/tmp/rag",
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
            def __init__(self, config_path=None, knowledge_dir=None):
                self.config_path = config_path
                self.knowledge_dir = knowledge_dir

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
            "rag_dir": "/tmp/rag",
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
        captured = {}

        class DummyGenerator:
            def __init__(self, output_dir="."):
                captured["output_dir"] = str(output_dir)

            def generate_xlsx(self, rows, filename=None):
                captured["xlsx_filename"] = filename
                return tmp_path / "report.xlsx"

            def generate_html(self, rows, filename=None, summary=None, agent_info=None, source_info=None):
                self.summary = summary
                self.agent_info = agent_info
                self.source_info = source_info
                self.rows = rows
                captured["html_filename"] = filename
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
                    extra={
                        "model_dir": str(tmp_path),
                        "config_context_files": [
                            str(tmp_path / "model.yaml"),
                            str(tmp_path / "Config" / "legacy.yaml"),
                        ],
                    },
                ),
                ModelInfo(
                    name="m2",
                    config_path=str(tmp_path / "m2.yaml"),
                ),
            ],
            "debug_results": [],
            "target_dir": str(tmp_path / "Models_35"),
            "output_dir": str(tmp_path / "output"),
        })

        assert result["report_path"].endswith("report.xlsx")
        assert result["report_html_path"].endswith("report.html")
        assert "report_rows" in result
        assert result["report_rows"][0].log_path == "/tmp/m1.log"
        assert result["report_rows"][0].config_hints == "model.yaml | Config/legacy.yaml"
        assert any(row.model_name == "m2" and row.error_category == "no_error" for row in result["report_rows"])
        assert captured["xlsx_filename"] == "report.xlsx"
        assert captured["html_filename"] == "report.html"
        assert captured["output_dir"].startswith(str((tmp_path / "output").resolve()))

    def test_report_output_dir_is_stable_per_target_dir(self, tmp_path) -> None:
        output_a = report_output_dir(str(tmp_path / "output"), str(tmp_path / "Models_35"))
        output_b = report_output_dir(str(tmp_path / "output"), str(tmp_path / "Models_35"))
        output_c = report_output_dir(str(tmp_path / "output"), str(tmp_path / "OtherModels"))

        assert output_a == output_b
        assert output_a.name.startswith("Models_35-")
        assert output_a != output_c

    def test_suggested_fix_summary_keeps_full_text(self) -> None:
        long_fix = "use calibration cache and disable per-channel quantization for the failing Conv2D branch"

        summary = _summarize_suggested_fixes([
            DebugResult(error_category="quantization_error", suggested_fix=long_fix),
        ])

        assert long_fix in summary

    def test_extract_uses_configured_log_paths_before_directory_scan(self, monkeypatch, tmp_path) -> None:
        explicit_log = tmp_path / "Models_35" / "01-1_yolo" / "run_001" / "convert.log"
        explicit_log.parent.mkdir(parents=True)
        explicit_log.write_text("[ERROR] unsupported dtype\n", encoding="utf-8")

        monkeypatch.setattr(
            "model_test_agent.graphs.main_graph.ConfigReader.read_target_directory",
            lambda self, path, layout_path="": [
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

    def test_extract_returns_layout_source_info(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "model_test_agent.graphs.main_graph.ConfigReader.read_target_directory",
            lambda self, path, layout_path="": [],
        )
        monkeypatch.setattr(
            "model_test_agent.graphs.main_graph.ConfigReader.describe_target_layout",
            lambda self, target_dir, layout_path="": {
                "target_dir": str(tmp_path),
                "layout_config": str(tmp_path / "target_layout.yaml"),
                "discovery_rule": "demo rule",
                "source_tree": "target-dir/\n  model/",
            },
        )

        result = _extract({"target_dir": str(tmp_path), "target_layout_path": str(tmp_path / "target_layout.yaml")})

        assert result["source_info"]["layout_config"].endswith("target_layout.yaml")

    def test_enrich_source_context_populates_code_location_and_context(self, monkeypatch) -> None:
        class DummyResolver:
            def __init__(self, codebase_root="", context_lines=15, docker_script_path=""):
                self.codebase_root = codebase_root
                self.docker_script_path = docker_script_path

            def extract_error_location(self, text):
                assert "shape mismatch" in text
                return ("src/demo.cpp", 42)

            def retrieve_code_context(self, file_path, line_num):
                assert file_path == "src/demo.cpp"
                assert line_num == 42
                return ">>    42 | return fail;"

            def describe_codebase_root(self):
                return "/repo"

        monkeypatch.setattr("model_test_agent.graphs.main_graph.SourceContextResolver", DummyResolver)

        result = _enrich_source_context({
            "errors": [ErrorEntry(model_name="m1", line_number=5, message="shape mismatch", raw_context="shape mismatch")],
            "source_info": {"target_dir": "/tmp/models"},
            "codebase_root": "/repo",
            "docker_script_path": "/tmp/enter_container.sh",
        })

        assert result["errors"][0].error_file_path == "src/demo.cpp"
        assert result["errors"][0].error_line_num == 42
        assert "return fail" in result["errors"][0].source_code_context
        assert result["source_info"]["codebase_root"] == "/repo"

    def test_enrich_source_context_can_skip_remaining_errors(self, monkeypatch) -> None:
        class DummyResolver:
            def __init__(self, codebase_root="", context_lines=15, docker_script_path=""):
                pass

            def extract_error_location(self, text):
                return ("src/demo.cpp", 42)

            def retrieve_code_context(self, file_path, line_num):
                return ">>    42 | return fail;"

            def describe_codebase_root(self):
                return "/repo"

        monkeypatch.setattr("model_test_agent.graphs.main_graph.SourceContextResolver", DummyResolver)

        seen = {"count": 0}

        def _should_skip(step_key: str) -> bool:
            return step_key == "source_context" and seen["count"] > 0

        def _progress(step_key: str, detail: str) -> None:
            if step_key == "source_context" and "正在定位源码" in detail:
                seen["count"] += 1

        errors = [
            ErrorEntry(model_name="m1", line_number=5, message="shape mismatch", raw_context="shape mismatch"),
            ErrorEntry(model_name="m2", line_number=6, message="other mismatch", raw_context="other mismatch"),
        ]

        result = _enrich_source_context({
            "errors": errors,
            "source_info": {"target_dir": "/tmp/models"},
            "ui_should_skip": _should_skip,
            "ui_progress_callback": _progress,
        })

        assert result["errors"][0].source_code_context == ">>    42 | return fail;"
        assert result["errors"][1].source_code_context == "源码定位已跳过，请仅根据日志与 RAG 推理"
        assert result["source_info"]["source_context_status"] == "skipped"

    def test_debug_subgraph_can_skip_remaining_categories(self, monkeypatch) -> None:
        analyzed = []

        class DummyRetriever:
            def __init__(self, config_path=None, knowledge_dir=None):
                pass

            def find_similar(self, category, key_log="", top_k=3):
                return []

        class DummySkill:
            def __init__(self, llm_config_path=None):
                pass

            def run(self, error_groups, models=None, history_per_category=None):
                category = next(iter(error_groups))
                analyzed.append(category)
                return [DebugResult(error_category=category, root_cause=f"done:{category}")]

        monkeypatch.setattr("model_test_agent.graphs.debug_subgraph.SemanticRetriever", DummyRetriever)
        monkeypatch.setattr("model_test_agent.graphs.debug_subgraph.DebugAnalyzerSkill", DummySkill)

        counter = {"seen": 0}

        def _progress(step_key: str, detail: str) -> None:
            if step_key == "debug" and "正在分析" in detail:
                counter["seen"] += 1

        def _should_skip(step_key: str) -> bool:
            return step_key == "debug" and counter["seen"] >= 1

        graph = build_debug_subgraph().compile()
        result = graph.invoke({
            "error_groups": {
                "cat_a": [ErrorEntry(model_name="m1", line_number=1, message="a")],
                "cat_b": [ErrorEntry(model_name="m2", line_number=2, message="b")],
            },
            "models": [],
            "debug_results": [],
            "auto_fix": False,
            "ui_progress_callback": _progress,
            "ui_should_skip": _should_skip,
        })

        result_map = {item.error_category: item for item in result["debug_results"]}
        assert analyzed == ["cat_a"]
        assert result_map["cat_a"].root_cause == "done:cat_a"
        assert result_map["cat_b"].fix_status == FixStatus.SKIPPED
        assert result_map["cat_b"].root_cause == "调试分析已跳过"
