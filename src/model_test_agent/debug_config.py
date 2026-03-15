"""Load prompt-budget and retrieval settings for debug analysis.

The goal is to keep token-shaping choices in one small config file so that
switching to longer-context models is mostly a config change, not a refactor.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_DEFAULT_DEBUG_CFG = Path(__file__).resolve().parents[2] / "config" / "debug.yaml"


@dataclass(frozen=True)
class SourceContextSettings:
    context_lines: int = 15


@dataclass(frozen=True)
class PromptBudgetSettings:
    max_error_samples: int = 5
    max_log_chars_per_sample: int = 600
    max_source_chars_per_sample: int = 1200
    max_config_chars_per_model: int = 1200
    max_config_chars_per_file: int = 400
    max_history_items: int = 3
    max_history_excerpt_chars: int = 240


@dataclass(frozen=True)
class RetrievalSettings:
    top_k: int = 3
    knowledge_chunk_size: int = 1200
    knowledge_chunk_overlap: int = 120
    knowledge_excerpt_chars: int = 900
    embedding_input_chars: int = 4000


@dataclass(frozen=True)
class DebugSettings:
    source_context: SourceContextSettings
    prompt_budget: PromptBudgetSettings
    retrieval: RetrievalSettings


def load_debug_settings(config_path: str | Path | None = None) -> DebugSettings:
    """Return debug settings from ``config/debug.yaml`` or built-in defaults."""
    resolved_path = Path(config_path).resolve() if config_path else _DEFAULT_DEBUG_CFG.resolve()
    return _load_debug_settings_cached(str(resolved_path))


@lru_cache(maxsize=4)
def _load_debug_settings_cached(path: str) -> DebugSettings:
    cfg_path = Path(path)
    data: dict = {}
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

    source = data.get("source_context") if isinstance(data.get("source_context"), dict) else {}
    prompt = data.get("prompt_budget") if isinstance(data.get("prompt_budget"), dict) else {}
    retrieval = data.get("retrieval") if isinstance(data.get("retrieval"), dict) else {}

    return DebugSettings(
        source_context=SourceContextSettings(
            context_lines=_as_positive_int(source.get("context_lines"), 15),
        ),
        prompt_budget=PromptBudgetSettings(
            max_error_samples=_as_positive_int(prompt.get("max_error_samples"), 5),
            max_log_chars_per_sample=_as_positive_int(prompt.get("max_log_chars_per_sample"), 600),
            max_source_chars_per_sample=_as_positive_int(prompt.get("max_source_chars_per_sample"), 1200),
            max_config_chars_per_model=_as_positive_int(prompt.get("max_config_chars_per_model"), 1200),
            max_config_chars_per_file=_as_positive_int(prompt.get("max_config_chars_per_file"), 400),
            max_history_items=_as_positive_int(prompt.get("max_history_items"), 3),
            max_history_excerpt_chars=_as_positive_int(prompt.get("max_history_excerpt_chars"), 240),
        ),
        retrieval=RetrievalSettings(
            top_k=_as_positive_int(retrieval.get("top_k"), 3),
            knowledge_chunk_size=_as_positive_int(retrieval.get("knowledge_chunk_size"), 1200),
            knowledge_chunk_overlap=_as_non_negative_int(retrieval.get("knowledge_chunk_overlap"), 120),
            knowledge_excerpt_chars=_as_positive_int(retrieval.get("knowledge_excerpt_chars"), 900),
            embedding_input_chars=_as_positive_int(retrieval.get("embedding_input_chars"), 4000),
        ),
    )


def _as_positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _as_non_negative_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default
