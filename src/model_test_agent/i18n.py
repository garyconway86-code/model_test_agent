"""Lightweight i18n helper — loads strings from config/i18n.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_DEFAULT_I18N = Path(__file__).resolve().parents[2] / "config" / "i18n.yaml"
_STRINGS: dict[str, str] = {}


def load_strings(config_path: str | Path = _DEFAULT_I18N, locale: str | None = None) -> None:
    """Load locale strings into the module-level cache."""
    global _STRINGS
    path = Path(config_path)
    if not path.exists():
        return
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    active = locale or data.get("active_locale", "zh")
    _STRINGS = data.get(active, data.get("zh", {}))


def t(key: str, **kwargs: Any) -> str:
    """Translate *key*.  Supports ``{placeholder}`` formatting."""
    if not _STRINGS:
        load_strings()
    text = _STRINGS.get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text
