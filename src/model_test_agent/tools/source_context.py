"""Extract source file locations from logs and load nearby code context."""

from __future__ import annotations

import re
from pathlib import Path


_LOCATION_PATTERNS = [
    re.compile(
        r"(?P<path>[/\w.\-]+?\.(?:cpp|cc|cxx|h|hpp|py)):(?P<line>\d+)(?::\d+)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<path>[/\w.\-]+?\.(?:cpp|cc|cxx|h|hpp|py))\((?P<line>\d+)\)",
        re.IGNORECASE,
    ),
]

_SOURCE_NOT_FOUND = "源码未找到，请仅根据日志推理"


class SourceContextResolver:
    """Resolve log-referenced source files and load surrounding lines."""

    def __init__(self, codebase_root: str | Path = "", context_lines: int = 15) -> None:
        self.codebase_root = Path(codebase_root).resolve() if codebase_root else None
        self.context_lines = context_lines

    def extract_error_location(self, text: str) -> tuple[str, int]:
        """Return the best-effort `(file_path, line_num)` extracted from the log."""
        matches: list[tuple[int, str, int]] = []
        for pattern in _LOCATION_PATTERNS:
            for match in pattern.finditer(text):
                path = match.group("path")
                line = int(match.group("line"))
                score = path.count("/") * 10 + len(path)
                matches.append((score, path, line))
        if not matches:
            return "Unknown", 0
        _, path, line = max(matches, key=lambda item: item[0])
        return path, line

    def retrieve_code_context(self, file_path: str, line_num: int) -> str:
        """Read nearby source code lines around `line_num`, or return a fallback message."""
        if not file_path or file_path == "Unknown":
            return _SOURCE_NOT_FOUND

        resolved = self._resolve_source_path(file_path)
        if resolved is None:
            return _SOURCE_NOT_FOUND

        try:
            lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return _SOURCE_NOT_FOUND

        if not lines:
            return _SOURCE_NOT_FOUND

        line_num = line_num or 1
        start = max(1, line_num - self.context_lines)
        end = min(len(lines), line_num + self.context_lines)
        rendered: list[str] = []
        for current in range(start, end + 1):
            marker = ">>" if current == line_num else "  "
            rendered.append(f"{marker} {current:>5} | {lines[current - 1]}")
        return "\n".join(rendered)

    def describe_codebase_root(self) -> str:
        """Return the active codebase root for UI display."""
        return str(self.codebase_root) if self.codebase_root else "current runtime"

    def _resolve_source_path(self, file_path: str) -> Path | None:
        raw = Path(file_path)
        for candidate in self._candidate_paths(raw):
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        return None

    def _candidate_paths(self, raw: Path) -> list[Path]:
        candidates: list[Path] = []
        seen: set[str] = set()

        def _add(path: Path) -> None:
            key = str(path)
            if key not in seen:
                seen.add(key)
                candidates.append(path)

        _add(raw)
        cwd = Path.cwd()
        roots = [cwd]
        if self.codebase_root:
            roots.insert(0, self.codebase_root)

        raw_parts = list(raw.parts)
        if raw.is_absolute():
            for root in roots:
                for idx in range(1, len(raw_parts)):
                    _add(root.joinpath(*raw_parts[idx:]))
        else:
            for root in roots:
                _add(root / raw)

        return candidates
