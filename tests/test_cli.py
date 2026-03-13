"""Tests for CLI helpers and argument parsing."""

from __future__ import annotations

import sys

from model_test_agent import __main__ as cli
from model_test_agent.__main__ import _parse_args, _step_snapshot_lines, _step_snapshot_title
from model_test_agent.state import ErrorEntry


class TestCLIHelpers:
    def test_parse_args_supports_skip_health_check(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "argv", ["model-test-agent", "--skip-health-check"])
        args = _parse_args()
        assert args.skip_health_check is True

    def test_extract_snapshot_includes_paths_and_sample_hits(self, tmp_path) -> None:
        state = {
            "log_dir": str(tmp_path),
            "config_path": str(tmp_path / "models.yaml"),
            "errors": [
                ErrorEntry(
                    model_name="resnet50",
                    line_number=12,
                    message="Shape mismatch at layer conv1",
                    category="shape_mismatch",
                    matched_keyword="shape mismatch",
                ),
            ],
            "models": [],
        }

        lines = _step_snapshot_lines("extract", state)

        assert any(line.startswith("errors: 1") for line in lines)
        assert any("sample_hits:" == line for line in lines)
        assert any("resnet50:12 [shape mismatch]" in line for line in lines)

    def test_classification_snapshot_includes_categories_and_keywords(self) -> None:
        errors = [
            ErrorEntry(
                model_name="bert",
                line_number=7,
                message="unsupported dtype: bfloat16",
                category="dtype_error",
                matched_keyword="dtype",
            ),
        ]
        state = {
            "errors": errors,
            "error_groups": {"dtype_error": errors},
        }

        lines = _step_snapshot_lines("classification", state)

        assert any("categories: dtype_error(1)" in line for line in lines)
        assert any("keywords: dtype(1)" in line for line in lines)
        assert any("-> dtype_error" in line for line in lines)

    def test_classification_snapshot_keeps_sample_and_category_aligned(self) -> None:
        errors = [
            ErrorEntry(
                model_name="m1",
                line_number=99,
                message="INFO checkpoint loaded",
                category="weight_loading",
                matched_keyword="checkpoint",
            ),
            ErrorEntry(
                model_name="m2",
                line_number=10,
                message="ERROR unsupported dtype",
                category="dtype_error",
                matched_keyword="dtype",
            ),
        ]

        lines = _step_snapshot_lines("classification", {"errors": errors, "error_groups": {}})

        assert any("m2:10 [dtype] ERROR unsupported dtype -> dtype_error" in line for line in lines)

    def test_snapshot_titles_match_panel_content(self) -> None:
        assert _step_snapshot_title("extract", {"log_dir": "/tmp/x", "config_path": "/tmp/y"}) == "输入路径"
        assert _step_snapshot_title("extract", {"errors": [], "models": []}) == "提取摘要"
        assert _step_snapshot_title("extract", {"errors": [object()], "models": []}) == "提取摘要"
        assert _step_snapshot_title("classification", {"errors": [], "error_groups": {}}) == "分类摘要"

    def test_extract_snapshot_with_zero_errors_is_a_summary(self) -> None:
        lines = _step_snapshot_lines("extract", {"errors": [], "models": []})

        assert lines == ["errors: 0", "models: 0", "top_models: -"]

    def test_report_snapshot_includes_interactive_viewer_link(self, tmp_path) -> None:
        report_html = tmp_path / "report.html"
        lines = _step_snapshot_lines(
            "report",
            {
                "report_rows": [],
                "report_path": str(tmp_path / "report.xlsx"),
                "report_html_path": str(report_html),
            },
        )

        assert any(line == f"report_html: {report_html}" for line in lines)
        assert any(line == f"viewer: {report_html.resolve().as_uri()}" for line in lines)

    def test_main_forwards_llm_config_to_full_pipeline(self, monkeypatch, tmp_path) -> None:
        captured = {}

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "model-test-agent",
                "--skip-health-check",
                "--log-dir",
                str(tmp_path),
                "--llm-config",
                str(tmp_path / "llm.yaml"),
            ],
        )
        monkeypatch.setattr(cli, "_run_full_pipeline", lambda *args: captured.setdefault("args", args))

        cli.main()

        assert captured["args"][3] == str(tmp_path / "llm.yaml")

    def test_main_allows_config_only_run(self, monkeypatch, tmp_path) -> None:
        captured = {}
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "model-test-agent",
                "--skip-health-check",
                "--config",
                str(tmp_path / "models.yaml"),
            ],
        )
        monkeypatch.setattr(cli, "_run_full_pipeline", lambda *args: captured.setdefault("args", args))

        cli.main()

        assert captured["args"][0] == ""
        assert captured["args"][1] == str(tmp_path / "models.yaml")
