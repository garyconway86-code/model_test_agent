"""Extract error fragments from model conversion test logs.

This tool operates on raw log files — no LLM is involved.  It uses keyword
and regex matching (driven by ``config/error_keywords.yaml``) to pull out
relevant error snippets with surrounding context lines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from model_test_agent.state import ErrorEntry

_DEFAULT_KEYWORDS_CFG = Path(__file__).resolve().parents[3] / "config" / "error_keywords.yaml"

# Fallback generic keywords when no config is available.
_FALLBACK_KEYWORDS = ["error", "Error", "ERROR", "exception", "Traceback", "FAILED"]


@dataclass
class LogExtractor:
    """Read log files and yield :class:`ErrorEntry` instances.

    Parameters
    ----------
    keywords_config : Path | str
        Path to the error_keywords YAML config.
    context_lines : int
        How many lines of surrounding context to keep per match.
    """

    keywords_config: Path | str = _DEFAULT_KEYWORDS_CFG
    context_lines: int = 3

    # Loaded at first use.
    _categories: dict[str, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._categories:
            return
        path = Path(self.keywords_config)
        if path.exists():
            with open(path, encoding="utf-8") as fh:
                self._categories = yaml.safe_load(fh) or {}
        if not self._categories:
            self._categories = {"unknown": {"keywords": _FALLBACK_KEYWORDS, "patterns": [], "priority": 999}}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_from_file(self, log_path: str | Path, model_name: str = "") -> list[ErrorEntry]:
        """Parse a single log file and return extracted errors."""
        self._ensure_loaded()
        path = Path(log_path)
        if not path.exists():
            return []

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if not model_name:
            model_name = path.stem

        entries: list[ErrorEntry] = []
        visited: set[int] = set()

        for idx, line in enumerate(lines):
            if idx in visited:
                continue
            match = self._match_line(line)
            if match is None:
                continue

            category, keyword = match
            ctx_start = max(0, idx - self.context_lines)
            ctx_end = min(len(lines), idx + self.context_lines + 1)
            context = "\n".join(lines[ctx_start:ctx_end])
            visited.update(range(ctx_start, ctx_end))

            entries.append(ErrorEntry(
                model_name=model_name,
                line_number=idx + 1,
                message=line.strip(),
                log_path=str(path.resolve()),
                raw_context=context,
                category=category,
                matched_keyword=keyword,
            ))

        return entries

    def extract_from_directory(self, log_dir: str | Path, suffix: str = ".log") -> list[ErrorEntry]:
        """Recursively scan *log_dir* for log files and extract errors."""
        self._ensure_loaded()
        results: list[ErrorEntry] = []
        root = Path(log_dir)
        for path in sorted(root.rglob(f"*{suffix}")):
            model_name = self._infer_model_name(path, root)
            results.extend(self.extract_from_file(path, model_name=model_name))
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _match_line(self, line: str) -> tuple[str, str] | None:
        """Return ``(category, matched_keyword)`` or *None*."""
        best: tuple[int, str, str] | None = None  # (priority, category, keyword)

        for cat_name, cat_cfg in self._categories.items():
            priority = cat_cfg.get("priority", 999)
            # Keyword match
            for kw in cat_cfg.get("keywords", []):
                if self._keyword_matches(line, kw):
                    if best is None or priority < best[0]:
                        best = (priority, cat_name, kw)
                    break
            # Regex match
            for pat in cat_cfg.get("patterns", []):
                if re.search(pat, line, re.IGNORECASE):
                    if best is None or priority < best[0]:
                        best = (priority, cat_name, f"regex:{pat}")
                    break

        return (best[1], best[2]) if best else None

    @staticmethod
    def _keyword_matches(line: str, keyword: str) -> bool:
        escaped = re.escape(keyword)
        prefix = r"(?<!\w)" if keyword[:1].isalnum() else ""
        suffix = r"(?!\w)" if keyword[-1:].isalnum() else ""
        return re.search(f"{prefix}{escaped}{suffix}", line, re.IGNORECASE) is not None

    @staticmethod
    def _infer_model_name(path: Path, root: Path) -> str:
        try:
            rel = path.relative_to(root)
        except ValueError:
            return path.stem
        if len(rel.parts) > 1:
            return rel.parts[0]
        return path.stem
