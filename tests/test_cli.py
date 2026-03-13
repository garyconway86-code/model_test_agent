"""Tests for CLI helpers and argument parsing."""

from __future__ import annotations

import sys

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
        assert _step_snapshot_title("extract", {"errors": [], "models": []}) == "输入路径"
        assert _step_snapshot_title("extract", {"errors": [object()], "models": []}) == "提取摘要"
        assert _step_snapshot_title("classification", {"errors": [], "error_groups": {}}) == "分类摘要"
