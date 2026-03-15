"""Tests for the tools layer — no LLM dependency, fully deterministic."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from model_test_agent.state import ErrorEntry, ModelInfo, ReportRow
from model_test_agent.debug_config import load_debug_settings
from model_test_agent.tools.config_reader import ConfigReader
from model_test_agent.tools.docker_executor import DockerExecutor
from model_test_agent.tools.history_store import HistoryStore
from model_test_agent.tools.knowledge_base import KnowledgeBase
from model_test_agent.tools.log_extractor import LogExtractor
from model_test_agent.tools.report_generator import ReportGenerator
from model_test_agent.tools.semantic_retriever import SemanticRetriever
from model_test_agent.tools.source_context import SourceContextResolver
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

        assert len(entries) == 1
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

    def test_multiple_error_lines_are_collapsed_into_one_entry(self, tmp_path: Path) -> None:
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

        assert len(entries) == 1
        assert entries[0].category in {"shape_mismatch", "memory_error", "io_error"}

    def test_chained_exceptions_are_split_into_multiple_entries(self, tmp_path: Path) -> None:
        log = tmp_path / "chain.log"
        log.write_text(
            "Traceback (most recent call last):\n"
            "  File \"/tmp/demo.py\", line 1, in <module>\n"
            "    raise ValueError('bad input')\n"
            "ValueError: bad input\n"
            "\n"
            "During handling of the above exception, another exception occurred:\n"
            "\n"
            "RuntimeError: fallback execution failed\n",
            encoding="utf-8",
        )

        extractor = LogExtractor(context_lines=1)
        entries = extractor.extract_from_file(log)

        assert len(entries) == 2
        assert "ValueError" in entries[0].message or "Traceback" in entries[0].message
        assert "RuntimeError" in entries[1].message


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
        (model_dir / "01-1_yolo.yaml").write_text("quantization: int8\n", encoding="utf-8")
        (model_dir / "package_info.json").write_text('{"version": "1.0.0"}', encoding="utf-8")
        config_dir = model_dir / "Config"
        config_dir.mkdir()
        (config_dir / "legacy.yaml").write_text("backend: legacy\nprecision: int8\n", encoding="utf-8")
        log_bundle = model_dir / "Converter_result" / "convert" / ".log"
        log_bundle.mkdir(parents=True)
        (log_bundle / "latest.txt").write_text("[ERROR] demo\n", encoding="utf-8")

        models = ConfigReader.read_target_directory(tmp_path / "Models_35")

        assert len(models) == 1
        assert models[0].name == "01-1_yolo"
        assert models[0].package_info_path.endswith("package_info.json")
        assert models[0].config_path.endswith("01-1_yolo.yaml")
        assert models[0].log_path.endswith("latest.txt")
        assert "Config/legacy.yaml" in models[0].extra["config_context"]
        assert any(path.endswith("legacy.yaml") for path in models[0].extra["config_context_files"])

    def test_read_target_directory_uses_layout_config_and_latest_log_in_dot_log_dir(self, tmp_path: Path) -> None:
        target_dir = tmp_path / "Models_35"
        model_dir = target_dir / "01-1_yolo"
        bundle_dir = model_dir / "convert.log"
        nested_cfg = model_dir / "meta" / "model.yaml"
        nested_pkg = model_dir / "meta" / "package_info.json"
        older_log = bundle_dir / "20260313_100000.txt"
        newer_log = bundle_dir / "20260314_100000.txt"

        nested_cfg.parent.mkdir(parents=True)
        bundle_dir.mkdir(parents=True)
        nested_cfg.write_text("name: 01-1_yolo\nquantization: int8\n", encoding="utf-8")
        nested_pkg.write_text('{"version": "1.0.0"}', encoding="utf-8")
        older_log.write_text("[ERROR] old error\n", encoding="utf-8")
        newer_log.write_text("[ERROR] new error\n", encoding="utf-8")
        older_log.touch()
        newer_log.touch()
        (target_dir / "target_layout.yaml").write_text(
            "config_patterns:\n"
            "  - meta/model.yaml\n"
            "package_info_patterns:\n"
            "  - meta/package_info.json\n"
            "log_dir_patterns:\n"
            "  - '*.log'\n"
            "log_file_patterns: []\n"
            "latest_log_file: true\n",
            encoding="utf-8",
        )

        models = ConfigReader.read_target_directory(target_dir)

        assert len(models) == 1
        assert models[0].config_path == str(nested_cfg.resolve())
        assert models[0].package_info_path == str(nested_pkg.resolve())
        assert models[0].log_path == str(newer_log.resolve())

    def test_layout_can_customize_config_context_patterns(self, tmp_path: Path) -> None:
        target_dir = tmp_path / "Models_35"
        model_dir = target_dir / "01-1_yolo"
        primary_cfg = model_dir / "01-1_yolo.yaml"
        legacy_cfg = model_dir / "Config" / "legacy.yaml"
        extra_cfg = model_dir / "Config" / "runtime.yaml"
        log_dir = model_dir / "Converter_result" / "convert" / ".log"

        extra_cfg.parent.mkdir(parents=True)
        log_dir.mkdir(parents=True)
        primary_cfg.write_text("quantization: int8\n", encoding="utf-8")
        legacy_cfg.write_text("backend: legacy\n", encoding="utf-8")
        extra_cfg.write_text("device: npu\n", encoding="utf-8")
        (log_dir / "latest.txt").write_text("[ERROR] demo\n", encoding="utf-8")
        (target_dir / "target_layout.yaml").write_text(
            "config_patterns:\n"
            "  - '{model_name}.yaml'\n"
            "config_context_patterns:\n"
            "  - Config/*.yaml\n"
            "config_context_max_files: 3\n"
            "log_dir_patterns:\n"
            "  - Converter_result/convert/.log\n"
            "log_file_patterns: []\n"
            "latest_log_file: true\n",
            encoding="utf-8",
        )

        models = ConfigReader.read_target_directory(target_dir)

        assert len(models) == 1
        context_files = models[0].extra["config_context_files"]
        assert len(context_files) == 3
        assert any(path.endswith("01-1_yolo.yaml") for path in context_files)
        assert any(path.endswith("legacy.yaml") for path in context_files)
        assert any(path.endswith("runtime.yaml") for path in context_files)

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


class TestDebugConfig:
    def test_load_debug_settings_from_yaml(self, tmp_path: Path) -> None:
        cfg = tmp_path / "debug.yaml"
        cfg.write_text(
            "source_context:\n"
            "  context_lines: 8\n"
            "prompt_budget:\n"
            "  max_error_samples: 7\n"
            "retrieval:\n"
            "  top_k: 5\n",
            encoding="utf-8",
        )

        settings = load_debug_settings(cfg)

        assert settings.source_context.context_lines == 8
        assert settings.prompt_budget.max_error_samples == 7
        assert settings.retrieval.top_k == 5
        assert settings.prompt_budget.max_log_chars_per_sample == 600


class TestSourceContextResolver:
    def test_extract_error_location_prefers_longer_source_path(self) -> None:
        resolver = SourceContextResolver()
        log = (
            "RuntimeError at helper.h:12\n"
            "Caused by /workspace/compiler/src/op_fallback.cpp:417: quantize failed\n"
        )

        path, line = resolver.extract_error_location(log)

        assert path == "/workspace/compiler/src/op_fallback.cpp"
        assert line == 417

    def test_retrieve_code_context_resolves_docker_style_path_via_codebase_root(self, tmp_path: Path) -> None:
        source = tmp_path / "src" / "compiler" / "op_fallback.cpp"
        source.parent.mkdir(parents=True)
        source.write_text("\n".join(f"line {index}" for index in range(1, 61)), encoding="utf-8")

        resolver = SourceContextResolver(codebase_root=tmp_path, context_lines=2)
        context = resolver.retrieve_code_context("/workspace/compiler/src/compiler/op_fallback.cpp", 30)

        assert ">>    30 | line 30" in context
        assert "      28 | line 28" in context

    def test_retrieve_code_context_returns_fallback_when_missing(self, tmp_path: Path) -> None:
        resolver = SourceContextResolver(codebase_root=tmp_path)
        assert resolver.retrieve_code_context("src/missing.cpp", 12) == "源码未找到，请仅根据日志推理"

    def test_retrieve_code_context_can_use_docker_script(self, tmp_path: Path) -> None:
        script = tmp_path / "docker_wrapper.sh"
        script.write_text(
            "#!/usr/bin/env bash\n"
            "bash -lc \"$1\"\n",
            encoding="utf-8",
        )
        source = tmp_path / "workspace" / "compiler" / "src" / "op_fallback.cpp"
        source.parent.mkdir(parents=True)
        source.write_text("\n".join(f"line {index}" for index in range(1, 21)), encoding="utf-8")

        resolver = SourceContextResolver(docker_script_path=script, context_lines=1)
        context = resolver.retrieve_code_context(str(source), 5)

        assert ">>     5 | line 5" in context
        assert "      4 | line 4" in context


class TestKnowledgeBase:
    def test_search_reads_txt_and_xlsx(self, tmp_path: Path) -> None:
        (tmp_path / "notes.txt").write_text("Conv2D quantization fallback requires int8 calibration", encoding="utf-8")
        workbook_path = tmp_path / "workaround.xlsx"
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "issues"
        sheet.append(["op", "workaround"])
        sheet.append(["Conv2D", "disable per-channel quantization"])
        workbook.save(workbook_path)

        kb = KnowledgeBase(tmp_path)
        results = kb.search("Conv2D quantization workaround", top_k=2)

        assert len(results) >= 1
        assert any(item["kind"] == "document" for item in results)
        assert any("Conv2D" in item["excerpt"] for item in results)


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

    def test_knowledge_dir_enables_local_rag_without_history(self, tmp_path: Path) -> None:
        store_path = tmp_path / "cases.json"
        store_path.write_text("[]")
        store = HistoryStore(store_path)
        knowledge_dir = tmp_path / "rag"
        knowledge_dir.mkdir()
        (knowledge_dir / "compiler_notes.md").write_text(
            "Conv2D quantization can fail when calibration stats are missing.",
            encoding="utf-8",
        )

        retriever = SemanticRetriever(store=store, knowledge_dir=knowledge_dir)
        results = retriever.find_similar("dtype_error", "Conv2D quantization failed", top_k=2)

        assert len(results) == 1
        assert results[0]["kind"] == "document"
        assert results[0]["source"] == "compiler_notes.md"


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

    def test_run_command_via_wrapper_script(self, tmp_path: Path) -> None:
        script = tmp_path / "docker_wrapper.sh"
        script.write_text(
            "#!/usr/bin/env bash\n"
            "bash -lc \"$1\"\n",
            encoding="utf-8",
        )

        executor = DockerExecutor(docker_script_path=str(script))
        result = executor.run("echo wrapped")

        assert result.success
        assert "wrapped" in result.stdout


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
                config_hints="01-1_yolo.yaml | Config/legacy.yaml",
                error_category="shape_mismatch",
                error_count=3,
                key_log_snippet="expected shape [64,3,7,7] but got [64,3,3,3]",
                history_match="是",
                suggested_fix="update conversion config",
                fix_executed="否",
                fix_result="pending",
                status="pending",
                comment="needs compiler owner follow-up",
            ),
            ReportRow(
                model_name="bert-base",
                log_path="/tmp/bert-base.log",
                log_line=7,
                package_summary="demo-kit | v1.2.4",
                quantization="fp16",
                has_test_data="是",
                config_hints="02-1_qwen2.yaml",
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
                "discovery_rule": "{model_name}.yaml + package_info.json + latest file in Converter_result/convert/.log",
                "source_tree": "target-dir/\n  01-1_model/\n    01-1_model.yaml\n    package_info.json\n    Converter_result/convert/.log/\n      latest log file",
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
        assert 'cell-suggested_fix' in content
        assert 'data-col-key="checked_by">Checked By</th><th data-col-key="comment">Comment</th><th data-col-key="model_name"' in content
        assert 'data-col-key="error_category"' in content
        assert 'data-col-key="log">Log</th>' in content
        assert content.count('data-col-key="comment">Comment</th>') == 1
        assert "Config Hints" in content
        assert "01-1_yolo.yaml | Config/legacy.yaml" in content
        assert 'data-column-toggle="has_test_data"' in content
        assert 'data-column-toggle="config_hints"' in content
        assert 'data-col-key="has_test_data" class="col-hidden"' in content
        assert 'data-col-key="config_hints" class="col-hidden"' in content
        assert "column-toggle-panel" in content
        assert "显示列" in content
        assert 'data-filter-kind="checked"' in content
        assert "Unchecked" in content
        assert "column-resizer" in content
        assert 'data-row-key="resnet50"' in content
        assert 'data-checked="false"' in content
        assert "cell-fix_result" in content
        assert "needs compiler owner follow-up" in content
        assert "comment-input" in content
        assert "Passed Models" in content
        assert ">2</div>" in content
        assert "Agent Assist" in content
        assert "/demo/Models_35" in content
        assert "Target Dir: /demo/Models_35" in content
        assert "deepseek-chat" in content
        assert "demo-kit | v1.2.3" in content


class TestCharts:
    def test_label_falls_back_to_english_without_cjk_font(self, monkeypatch) -> None:
        monkeypatch.setattr(charts, "_CJK_FONT", None)
        assert charts._label("错误数量", "Error Count") == "Error Count"
