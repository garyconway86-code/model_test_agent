"""Tests for state definitions and data classes."""

from model_test_agent.state import (
    AgentState,
    DebugResult,
    ErrorEntry,
    FixStatus,
    ModelInfo,
    ReportRow,
    _merge_dicts,
    _merge_lists,
)


class TestDataClasses:
    def test_model_info_defaults(self) -> None:
        m = ModelInfo(name="test")
        assert m.quantization == "fp32"
        assert m.has_test_data is False

    def test_error_entry(self) -> None:
        e = ErrorEntry(model_name="m", line_number=10, message="err")
        assert e.category == "unknown"
        e.category = "shape_mismatch"
        assert e.category == "shape_mismatch"

    def test_debug_result_defaults(self) -> None:
        dr = DebugResult(error_category="test")
        assert dr.fix_status == FixStatus.PENDING
        assert dr.retry_count == 0

    def test_fix_status_values(self) -> None:
        assert FixStatus.SUCCESS.value == "success"
        assert FixStatus.FAILED.value == "failed"


class TestReducers:
    def test_merge_lists(self) -> None:
        assert _merge_lists([1, 2], [3, 4]) == [1, 2, 3, 4]
        assert _merge_lists([], [1]) == [1]

    def test_merge_dicts(self) -> None:
        result = _merge_dicts({"a": [1]}, {"a": [2], "b": 3})
        assert result == {"a": [1, 2], "b": 3}

    def test_merge_dicts_overwrite(self) -> None:
        result = _merge_dicts({"a": "old"}, {"a": "new"})
        assert result == {"a": "new"}
