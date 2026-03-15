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
_CHAIN_SPLIT_PATTERNS = [
    re.compile(r"during handling of the above exception, another exception occurred", re.IGNORECASE),
    re.compile(r"the above exception was the direct cause of the following exception", re.IGNORECASE),
    re.compile(r"\bcaused by:\b", re.IGNORECASE),
]


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
    max_segment_context_lines: int = 24

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

        candidates: list[dict[str, Any]] = []
        for idx, line in enumerate(lines):
            match = self._match_line(line)
            if match is None:
                continue
            category, keyword = match
            candidates.append({
                "idx": idx,
                "line": line.rstrip(),
                "category": category,
                "keyword": keyword,
            })

        if not candidates:
            return []

        entries: list[ErrorEntry] = []
        for segment in self._group_candidates(candidates, lines):
            primary = max(segment, key=self._candidate_score)
            seg_start = segment[0]["idx"]
            seg_end = segment[-1]["idx"]
            ctx_start, ctx_end = self._context_bounds(seg_start, seg_end, primary["idx"], len(lines))
            context = "\n".join(lines[ctx_start:ctx_end])
            entries.append(ErrorEntry(
                model_name=model_name,
                line_number=primary["idx"] + 1,
                message=primary["line"].strip(),
                log_path=str(path.resolve()),
                raw_context=context,
                category=primary["category"],
                matched_keyword=primary["keyword"],
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

    def extract_from_target_directory(self, target_dir: str | Path, suffix: str = ".log") -> list[ErrorEntry]:
        """Extract logs from each immediate child model directory under *target_dir*."""
        self._ensure_loaded()
        results: list[ErrorEntry] = []
        root = Path(target_dir)
        for model_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            for path in sorted(model_dir.rglob(f"*{suffix}")):
                results.extend(self.extract_from_file(path, model_name=model_dir.name))
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

        if best:
            return best[1], best[2]
        if re.search(r"\b(?:\w+(?:Error|Exception)):", line):
            return "unknown", "exception_type"
        return None

    def _group_candidates(self, candidates: list[dict[str, Any]], lines: list[str]) -> list[list[dict[str, Any]]]:
        split_indexes = {
            idx
            for idx, line in enumerate(lines)
            if any(pattern.search(line) for pattern in _CHAIN_SPLIT_PATTERNS)
        }
        if not split_indexes:
            return [candidates]

        groups: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        for candidate in candidates:
            if current and any(split_idx < candidate["idx"] and split_idx >= current[-1]["idx"] for split_idx in split_indexes):
                groups.append(current)
                current = []
            current.append(candidate)
        if current:
            groups.append(current)
        return groups or [candidates]

    def _context_bounds(self, seg_start: int, seg_end: int, primary_idx: int, total_lines: int) -> tuple[int, int]:
        window_start = max(seg_start, primary_idx - self.context_lines)
        window_end = min(seg_end, primary_idx + self.context_lines)
        span = window_end - window_start + 1
        if span < self.max_segment_context_lines and seg_end - seg_start + 1 <= self.max_segment_context_lines:
            window_start = max(0, seg_start - self.context_lines)
            window_end = min(total_lines - 1, seg_end + self.context_lines)
        return window_start, window_end + 1

    @staticmethod
    def _candidate_score(candidate: dict[str, Any]) -> tuple[int, int, int]:
        line = str(candidate.get("line", ""))
        signal = 0
        if re.search(r"\b(traceback|exception|fatal|failed|error)\b", line, re.IGNORECASE):
            signal += 5
        if re.search(r"\b(mismatch|unsupported|out of memory|filenotfound|no such file|cannot|failed)\b", line, re.IGNORECASE):
            signal += 3
        return (signal, candidate["idx"], len(line))

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
