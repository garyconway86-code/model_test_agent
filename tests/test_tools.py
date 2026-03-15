"""Tests for the tools layer — no LLM dependency, fully deterministic."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from model_test_agent.state import ErrorEntry, ModelInfo, ReportRow
from model_test_agent.tools.config_reader import ConfigReader
from model_test_agent.tools.docker_executor import DockerExecutor
from model_test_agent.tools.history_store import HistoryStore
from model_test_agent.tools.log_extractor import LogExtractor
from model_test_agent.tools.report_generator import ReportGenerator
from model_test_agent.tools.semantic_retriever import SemanticRetriever
from model_test_agent.viz import charts


# ------------------------------------------------------------------
# LogExtractor
# ------------------------------------------------------------------

class TestLogExtractor:
    def test_extract_from_file(self, tmp_path: Path) -> None:
        log = tmp_path / "test_model.log"
        log.write_text(
            "[INFO] Starting conversion\n"
            "[ERROR] Shape mismatch at layer conv1: expected [64,3,7,7] but got [64,3,3,3]\n"
            "[INFO] Attempting fallback\n"
            "[ERROR] Fallback failed: shape mismatch persists\n"
        )
        extractor = LogExtractor(context_lines=1)
        entries = extractor.extract_from_file(log, model_name="test_model")

        assert len(entries) >= 1
        assert entries[0].model_name == "test_model"
        assert entries[0].category == "shape_mismatch"

    def test_extract_from_directory(self, tmp_path: Path) -> None:
        for name in ["model_a", "model_b"]:
            (tmp_path / f"{name}.log").write_text(
                f"[ERROR] unsupported dtype: bfloat16 in {name}\n"
            )
        extractor = LogExtractor(context_lines=0)
        entries = extractor.extract_from_directory(tmp_path)

        assert len(entries) == 2
        model_names = {e.model_name for e in entries}
        assert model_names == {"model_a", "model_b"}

    def test_extract_from_nested_directory_uses_model_folder_name(self, tmp_path: Path) -> None:
        log_path = tmp_path / "Models_35" / "01-1_yolo" / "run_001" / "convert.log"
        log_path.parent.mkdir(parents=True)
        log_path.write_text("[ERROR] Shape mismatch at output\n", encoding="utf-8")

        extractor = LogExtractor(context_lines=0)
        entries = extractor.extract_from_directory(tmp_path / "Models_35")

        assert len(entries) == 1
        assert entries[0].model_name == "01-1_yolo"

    def test_extract_from_target_directory_uses_first_level_model_dirs(self, tmp_path: Path) -> None:
        model_log = tmp_path / "Models_35" / "02-1_qwen2" / "runs" / "20260312" / "convert.log"
        model_log.parent.mkdir(parents=True)
        model_log.write_text("[ERROR] missing operator: demo\n", encoding="utf-8")

        extractor = LogExtractor(context_lines=0)
        entries = extractor.extract_from_target_directory(tmp_path / "Models_35")

        assert len(entries) == 1
        assert entries[0].model_name == "02-1_qwen2"

    def test_no_errors_returns_empty(self, tmp_path: Path) -> None:
        log = tmp_path / "clean.log"
        log.write_text("[INFO] All good\n[INFO] Conversion successful\n")
        extractor = LogExtractor(context_lines=0)
        assert extractor.extract_from_file(log) == []

    def test_nonexistent_file_returns_empty(self) -> None:
        extractor = LogExtractor()
        assert extractor.extract_from_file("/nonexistent/path.log") == []

    def test_multiple_categories(self, tmp_path: Path) -> None:
        log = tmp_path / "multi.log"
        log.write_text(
            "[ERROR] Shape mismatch at layer 1\n"
            "[INFO] some info\n"
            "[ERROR] CUDA out of memory. Tried to allocate 2 GiB\n"
            "[INFO] more info\n"
            "[ERROR] FileNotFoundError: No such file or directory: '/missing'\n"
        )
        extractor = LogExtractor(context_lines=0)
        entries = extractor.extract_from_file(log)

        categories = {e.category for e in entries}
        assert "shape_mismatch" in categories
        assert "memory_error" in categories
        assert "io_error" in categories


# ------------------------------------------------------------------
# ConfigReader
# ------------------------------------------------------------------

class TestConfigReader:
    def test_read_models_list(self, tmp_path: Path) -> None:
        cfg = tmp_path / "models.yaml"
        cfg.write_text(
            "models:\n"
            "  - name: resnet50\n"
            "    quantization: int8\n"
            "    has_test_data: true\n"
            "  - name: bert\n"
            "    quantization: fp16\n"
        )
        models = ConfigReader.read_file(cfg)
        assert len(models) == 2
        assert models[0].name == "resnet50"
        assert models[0].quantization == "int8"
        assert models[0].has_test_data is True
        assert models[1].has_test_data is False

    def test_read_single_model(self, tmp_path: Path) -> None:
        cfg = tmp_path / "single.yaml"
        cfg.write_text("name: mobilenet\nquantization: fp32\n")
        models = ConfigReader.read_file(cfg)
        assert len(models) == 1
        assert models[0].name == "mobilenet"

    def test_nonexistent_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            ConfigReader.read_file("/nonexistent/config.yaml")

    def test_read_directory_recursively(self, tmp_path: Path) -> None:
        model_a = tmp_path / "Models_35" / "01-1_yolo" / "config.yaml"
        model_b = tmp_path / "Models_35" / "02-1_bert" / "meta.yml"
        model_a.parent.mkdir(parents=True)
        model_b.parent.mkdir(parents=True)
        model_a.write_text("name: 01-1_yolo\nquantization: int8\n", encoding="utf-8")
        model_b.write_text("name: 02-1_bert\nhas_test_data: true\n", encoding="utf-8")

        models = ConfigReader.read_file(tmp_path / "Models_35")

        assert [model.name for model in models] == ["01-1_yolo", "02-1_bert"]
        assert str(model_a) in {model.config_path for model in models}

    def test_read_target_directory_uses_first_level_model_dirs(self, tmp_path: Path) -> None:
        model_dir = tmp_path / "Models_35" / "01-1_yolo"
        model_dir.mkdir(parents=True)
        (model_dir / "model_config.yaml").write_text("quantization: int8\n", encoding="utf-8")
        (model_dir / "package_info.json").write_text('{"version": "1.0.0"}', encoding="utf-8")

        models = ConfigReader.read_target_directory(tmp_path / "Models_35")

        assert len(models) == 1
        assert models[0].name == "01-1_yolo"
        assert models[0].package_info_path.endswith("package_info.json")

    def test_read_file_resolves_relative_model_paths(self, tmp_path: Path) -> None:
        cfg = tmp_path / "models.yaml"
        cfg.write_text(
            "models:\n"
            "  - name: 01-1_yolo\n"
            "    config_path: Models_35/01-1_yolo/model.yaml\n"
            "    log_path: Models_35/01-1_yolo/run_001/convert.log\n"
            "    package_info_path: Models_35/01-1_yolo/package_info.json\n",
            encoding="utf-8",
        )

        models = ConfigReader.read_file(cfg)

        assert models[0].config_path == str((tmp_path / "Models_35/01-1_yolo/model.yaml").resolve())
        assert models[0].log_path == str((tmp_path / "Models_35/01-1_yolo/run_001/convert.log").resolve())
        assert models[0].package_info_path == str((tmp_path / "Models_35/01-1_yolo/package_info.json").resolve())


# ------------------------------------------------------------------
# HistoryStore
# ------------------------------------------------------------------

class TestHistoryStore:
    def test_add_and_find(self, tmp_path: Path) -> None:
        store_path = tmp_path / "cases.json"
        store_path.write_text("[]")
        store = HistoryStore(store_path)

        case_id = store.add_case(
            error_category="shape_mismatch",
            model_name="resnet50",
            quantization="int8",
            key_log="expected shape [64,3,7,7] but got [64,3,3,3]",
            root_cause="kernel size mismatch",
            solution="update config",
            effective=True,
        )
        assert case_id.startswith("case-")

        matches = store.find_similar("shape_mismatch", "expected shape mismatch")
        assert len(matches) == 1
        assert matches[0]["model_name"] == "resnet50"

    def test_find_no_match(self, tmp_path: Path) -> None:
        store_path = tmp_path / "cases.json"
        store_path.write_text("[]")
        store = HistoryStore(store_path)
        assert store.find_similar("nonexistent_category") == []

    def test_persistence(self, tmp_path: Path) -> None:
        store_path = tmp_path / "cases.json"
        store_path.write_text("[]")

        store1 = HistoryStore(store_path)
        store1.add_case("dtype_error", "bert", "fp16", "bfloat16", "cast", "use fp16", True)

        # New instance should see the persisted case
        store2 = HistoryStore(store_path)
        assert len(store2.get_all()) == 1


class TestSemanticRetriever:
    def test_empty_history_does_not_call_embedding_api(self, monkeypatch, tmp_path: Path) -> None:
        store_path = tmp_path / "cases.json"
        store_path.write_text("[]")
        store = HistoryStore(store_path)

        monkeypatch.setattr(
            "model_test_agent.tools.semantic_retriever._load_profiles",
            lambda config_path=None: {
                "embedding": {"base_url": "https://example.invalid/v1", "api_key": "x", "model": "embed"},
                "reranker": {"base_url": "https://example.invalid", "api_key": "x", "model": "rerank", "top_n": 3},
            },
        )

        class UnexpectedClient:
            def __init__(self, *args, **kwargs):
                raise AssertionError("Embedding client should not be created when history is empty")

        monkeypatch.setattr("model_test_agent.tools.semantic_retriever.OpenAI", UnexpectedClient)

        retriever = SemanticRetriever(store=store)

        assert retriever.find_similar("shape_mismatch", "shape mismatch", top_k=3) == []


# ------------------------------------------------------------------
# DockerExecutor
# ------------------------------------------------------------------

class TestDockerExecutor:
    def test_run_simple_command(self) -> None:
        executor = DockerExecutor(docker_image=None)
        result = executor.run("echo hello")
        assert result.success
        assert "hello" in result.stdout

    def test_failing_command(self) -> None:
        executor = DockerExecutor(docker_image=None)
        result = executor.run("exit 1")
        assert not result.success
        assert result.return_code == 1

    def test_timeout(self) -> None:
        executor = DockerExecutor(docker_image=None, timeout=1)
        result = executor.run("sleep 10")
        assert not result.success
        assert "timed out" in result.stderr.lower()


# ------------------------------------------------------------------
# ReportGenerator
# ------------------------------------------------------------------

class TestReportGenerator:
    @pytest.fixture()
    def sample_rows(self) -> list[ReportRow]:
        return [
            ReportRow(
                model_name="resnet50",
                log_path="/tmp/resnet50.log",
                log_line=3,
                package_summary="demo-kit | v1.2.3",
                quantization="int8",
                has_test_data="是",
                error_category="shape_mismatch",
                error_count=3,
                key_log_snippet="expected shape [64,3,7,7] but got [64,3,3,3]",
                history_match="是",
                suggested_fix="update conversion config",
                fix_executed="否",
                fix_result="pending",
                status="pending",
            ),
            ReportRow(
                model_name="bert-base",
                log_path="/tmp/bert-base.log",
                log_line=7,
                package_summary="demo-kit | v1.2.4",
                quantization="fp16",
                has_test_data="是",
                error_category="dtype_error",
                error_count=2,
                key_log_snippet="unsupported dtype: bfloat16",
                history_match="是",
                suggested_fix="use --force-dtype fp16",
                fix_executed="是",
                fix_result="success",
                status="success",
            ),
        ]

    def test_generate_xlsx(self, tmp_path: Path, sample_rows: list[ReportRow]) -> None:
        gen = ReportGenerator(output_dir=tmp_path)
        path = gen.generate_xlsx(sample_rows, filename="test.xlsx")
        assert path.exists()
        assert path.suffix == ".xlsx"

    def test_generate_html(self, tmp_path: Path, sample_rows: list[ReportRow]) -> None:
        (tmp_path / "resnet50.log").write_text("line1\nline2\nshape mismatch\n", encoding="utf-8")
        (tmp_path / "bert-base.log").write_text("a\nb\nc\nd\ne\nf\nunsupported dtype\n", encoding="utf-8")
        sample_rows[0].log_path = str((tmp_path / "resnet50.log").resolve())
        sample_rows[1].log_path = str((tmp_path / "bert-base.log").resolve())

        gen = ReportGenerator(output_dir=tmp_path)
        path = gen.generate_html(
            sample_rows,
            filename="test.html",
            summary={"total_models": 4, "passed_models": 2, "failed_models": 2},
            agent_info={
                "classifier_model": "deepseek-chat",
                "debugger_model": "deepseek-chat",
                "assisted_fields": "error_category, suggested_fix, root_cause",
            },
            source_info={
                "target_dir": "/demo/Models_35",
                "discovery_rule": "1st-level subdirs => models",
            },
        )
        assert path.exists()
        content = path.read_text()
        assert "resnet50" in content
        assert "bert-base" in content
        assert "shape_mismatch" in content
        assert "View Source" in content
        assert "Open File" in content
        assert "shape mismatch" in content
        assert "Passed Models" in content
        assert ">2</div>" in content
        assert "Agent Assist" in content
        assert "Target Layout" in content
        assert "/demo/Models_35" in content
        assert "deepseek-chat" in content
        assert "demo-kit | v1.2.3" in content


class TestCharts:
    def test_label_falls_back_to_english_without_cjk_font(self, monkeypatch) -> None:
        monkeypatch.setattr(charts, "_CJK_FONT", None)
        assert charts._label("错误数量", "Error Count") == "Error Count"
