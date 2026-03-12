"""Tests for the i18n module."""

from pathlib import Path
import tempfile

from model_test_agent.i18n import load_strings, t


class TestI18n:
    def test_load_zh(self, tmp_path: Path) -> None:
        cfg = tmp_path / "i18n.yaml"
        cfg.write_text(
            "active_locale: zh\n"
            "zh:\n"
            "  hello: 你好\n"
            "  greeting: 你好 {name}\n"
        )
        load_strings(cfg)
        assert t("hello") == "你好"
        assert t("greeting", name="世界") == "你好 世界"

    def test_fallback_key(self, tmp_path: Path) -> None:
        cfg = tmp_path / "i18n.yaml"
        cfg.write_text("active_locale: zh\nzh:\n  key1: val1\n")
        load_strings(cfg)
        assert t("nonexistent") == "nonexistent"

    def test_load_en(self, tmp_path: Path) -> None:
        cfg = tmp_path / "i18n.yaml"
        cfg.write_text(
            "active_locale: en\n"
            "en:\n"
            "  hello: Hello\n"
        )
        load_strings(cfg, locale="en")
        assert t("hello") == "Hello"
