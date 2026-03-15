"""Extract source file locations from logs and load nearby code context."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from model_test_agent.debug_config import load_debug_settings
from model_test_agent.tools.docker_executor import DockerExecutor


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

    def __init__(
        self,
        codebase_root: str | Path = "",
        context_lines: int | None = None,
        docker_script_path: str | Path = "",
    ) -> None:
        settings = load_debug_settings()
        self.codebase_root = Path(codebase_root).resolve() if codebase_root else None
        self.context_lines = context_lines or settings.source_context.context_lines
        self.docker_read_timeout = settings.source_context.docker_read_timeout_seconds
        self.docker_script_path = Path(docker_script_path).resolve() if docker_script_path else None
        self._resolved_path_cache: dict[str, Path | None] = {}
        self._local_context_cache: dict[tuple[str, int], str] = {}

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
        if resolved is not None:
            return self._read_local_context(resolved, line_num)

        container_context = self._read_container_context(file_path, line_num)
        if container_context:
            return container_context

        return _SOURCE_NOT_FOUND

    def _read_local_context(self, resolved: Path, line_num: int) -> str:
        cache_key = (str(resolved), line_num or 1)
        if cache_key in self._local_context_cache:
            return self._local_context_cache[cache_key]
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
        context = "\n".join(rendered)
        self._local_context_cache[cache_key] = context
        return context

    def describe_codebase_root(self) -> str:
        """Return the active codebase root for UI display."""
        if self.docker_script_path:
            if self.codebase_root:
                return f"{self.codebase_root} (docker fallback: {self.docker_script_path.name})"
            return f"docker script: {self.docker_script_path}"
        return str(self.codebase_root) if self.codebase_root else "current runtime"

    def _read_container_context(self, file_path: str, line_num: int) -> str:
        if not self.docker_script_path:
            return ""
        target_line = line_num or 1
        start = max(1, target_line - self.context_lines)
        end = target_line + self.context_lines
        command = (
            f"if [ ! -f {shlex.quote(file_path)} ]; then exit 44; fi; "
            f"awk 'NR>={start} && NR<={end} {{printf(\"%s %5d | %s\\n\", (NR=={target_line}?\">>\":\"  \"), NR, $0)}}' "
            f"{shlex.quote(file_path)}"
        )
        result = DockerExecutor(
            docker_script_path=str(self.docker_script_path),
            timeout=self.docker_read_timeout,
        ).run(command)
        if result.success and result.stdout.strip():
            return result.stdout.strip()
        return ""

    def _resolve_source_path(self, file_path: str) -> Path | None:
        if file_path in self._resolved_path_cache:
            return self._resolved_path_cache[file_path]
        raw = Path(file_path)
        for candidate in self._candidate_paths(raw):
            if candidate.exists() and candidate.is_file():
                resolved = candidate.resolve()
                self._resolved_path_cache[file_path] = resolved
                return resolved
        self._resolved_path_cache[file_path] = None
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
