"""Read model test configuration files.

Parses per-model YAML config files that describe:
  - model name, quantization type, source path
  - whether pre-generated test data exists
  - any custom conversion flags

The reader is format-agnostic — it returns :class:`ModelInfo` objects that
the rest of the pipeline consumes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from model_test_agent.state import ModelInfo

_DEFAULT_TARGET_LAYOUT: dict[str, Any] = {
    "model_dir_pattern": "*",
    "config_patterns": [
        "{model_name}.yaml",
        "{model_name}.yml",
        "config.yaml",
        "config.yml",
    ],
    "config_context_patterns": [
        "{model_name}.yaml",
        "{model_name}.yml",
        "Config/legacy.yaml",
    ],
    "config_context_max_files": 4,
    "package_info_patterns": ["package_info.json"],
    "log_file_patterns": [],
    "log_dir_patterns": ["Converter_result/convert/.log", "*.log"],
    "latest_log_file": True,
}


class ConfigReader:
    """Load model configurations from a YAML file or directory of YAML files.

    Expected YAML structure (single-file, list of models)::

        models:
          - name: resnet50
            quantization: int8
            has_test_data: true
            config_path: /data/models/resnet50/config.yaml
            extra:
              input_shape: [1, 3, 224, 224]

    Or per-model files in a directory, each containing a single model dict.
    """

    @staticmethod
    def read_file(path: str | Path) -> list[ModelInfo]:
        """Parse a YAML file and return a list of :class:`ModelInfo`."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        if path.is_dir():
            return ConfigReader.read_directory(path)

        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if data is None:
            return []
        if not ConfigReader._looks_like_model_config(data):
            return []
        return ConfigReader._parse(data, source_path=path)

    @staticmethod
    def read_directory(dir_path: str | Path) -> list[ModelInfo]:
        """Read model YAML files in *dir_path* recursively and merge into one list."""
        results: list[ModelInfo] = []
        seen_names: set[str] = set()
        root = Path(dir_path)
        for pattern in ("*.yaml", "*.yml"):
            for p in sorted(root.rglob(pattern)):
                for info in ConfigReader.read_file(p):
                    if info.name in seen_names:
                        continue
                    seen_names.add(info.name)
                    results.append(info)
        return results

    @staticmethod
    def read_target_directory(
        target_dir: str | Path,
        layout_path: str | Path = "",
    ) -> list[ModelInfo]:
        """Read one model config from each immediate child directory in *target_dir*."""
        results: list[ModelInfo] = []
        root = Path(target_dir)
        layout = ConfigReader.load_target_layout(root, layout_path)
        for model_dir in ConfigReader._iter_model_dirs(root, layout["model_dir_pattern"]):
            cfg_path = ConfigReader._find_model_config(model_dir, layout["config_patterns"])
            if cfg_path:
                models = ConfigReader.read_file(cfg_path)
            else:
                models = [ModelInfo(name=model_dir.name)]

            for model in models:
                package_info_path = ConfigReader._resolve_package_info_path(
                    model_dir,
                    model.package_info_path,
                    layout["package_info_patterns"],
                )
                log_path = ConfigReader._resolve_log_path(
                    model_dir,
                    model.log_path,
                    layout["log_file_patterns"],
                    layout["log_dir_patterns"],
                    layout["latest_log_file"],
                )
                config_context = ConfigReader._build_config_context(
                    model_dir,
                    primary_config_path=model.config_path or str(cfg_path or ""),
                    patterns=layout["config_context_patterns"],
                    max_files=layout["config_context_max_files"],
                )
                results.append(ModelInfo(
                    name=model.name or model_dir.name,
                    quantization=model.quantization,
                    has_test_data=model.has_test_data,
                    config_path=model.config_path or str(cfg_path or ""),
                    log_path=log_path,
                    package_info_path=package_info_path,
                    extra={
                        **model.extra,
                        "model_dir": str(model_dir.resolve()),
                        "config_context": config_context["summary"],
                        "config_context_files": config_context["files"],
                    },
                ))
        return results

    @staticmethod
    def load_target_layout(target_dir: str | Path, layout_path: str | Path = "") -> dict[str, Any]:
        """Load target layout config or return defaults."""
        path = ConfigReader._find_layout_path(Path(target_dir), Path(layout_path) if layout_path else None)
        data: dict[str, Any] = {}
        if path and path.exists():
            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}

        logs_cfg = data.get("logs", {}) if isinstance(data.get("logs"), dict) else {}
        return {
            "model_dir_pattern": str(data.get("model_dir_pattern") or _DEFAULT_TARGET_LAYOUT["model_dir_pattern"]),
            "config_patterns": ConfigReader._as_patterns(
                data.get("config_patterns"),
                _DEFAULT_TARGET_LAYOUT["config_patterns"],
            ),
            "package_info_patterns": ConfigReader._as_patterns(
                data.get("package_info_patterns"),
                _DEFAULT_TARGET_LAYOUT["package_info_patterns"],
            ),
            "config_context_patterns": ConfigReader._as_patterns(
                data.get("config_context_patterns"),
                _DEFAULT_TARGET_LAYOUT["config_context_patterns"],
            ),
            "config_context_max_files": ConfigReader._as_positive_int(
                data.get("config_context_max_files"),
                _DEFAULT_TARGET_LAYOUT["config_context_max_files"],
            ),
            "log_file_patterns": ConfigReader._as_patterns(
                data.get("log_file_patterns", logs_cfg.get("file_patterns")),
                _DEFAULT_TARGET_LAYOUT["log_file_patterns"],
            ),
            "log_dir_patterns": ConfigReader._as_patterns(
                data.get("log_dir_patterns", logs_cfg.get("directory_patterns")),
                _DEFAULT_TARGET_LAYOUT["log_dir_patterns"],
            ),
            "latest_log_file": bool(
                data.get("latest_log_file", logs_cfg.get("latest_file", _DEFAULT_TARGET_LAYOUT["latest_log_file"]))
            ),
            "config_path": str(path.resolve()) if path and path.exists() else "",
        }

    @staticmethod
    def describe_target_layout(target_dir: str | Path, layout_path: str | Path = "") -> dict[str, str]:
        """Return a concise layout summary for the CLI and HTML report."""
        layout = ConfigReader.load_target_layout(target_dir, layout_path)
        config_label = layout["config_path"] or "built-in defaults"
        log_mode = "latest file in matched .log dirs" if layout["latest_log_file"] else "all matched files"
        config_example = ConfigReader._render_pattern_example(layout["config_patterns"][0]) if layout["config_patterns"] else "<model-name>.yaml"
        config_context_example = (
            ConfigReader._render_pattern_example(layout["config_context_patterns"][0])
            if layout["config_context_patterns"]
            else "Config/legacy.yaml"
        )
        package_example = ConfigReader._render_pattern_example(layout["package_info_patterns"][0]) if layout["package_info_patterns"] else "package_info.json"
        log_dir_example = ConfigReader._render_pattern_example(layout["log_dir_patterns"][0]) if layout["log_dir_patterns"] else ".log"
        source_tree = (
            "target-dir/\n"
            "  <model-dir>/\n"
            f"    {config_example}\n"
            f"    {config_context_example}\n"
            f"    {package_example}\n"
            f"    {log_dir_example}/\n"
            "      latest log file"
        )
        return {
            "target_dir": str(Path(target_dir).resolve()) if target_dir else "-",
            "layout_config": config_label,
            "discovery_rule": (
                f"{layout['model_dir_pattern']} => models; "
                f"config={', '.join(layout['config_patterns'])}; "
                f"config_context={', '.join(layout['config_context_patterns'])}; "
                f"log_files={', '.join(layout['log_file_patterns'])}; "
                f"log_dirs={', '.join(layout['log_dir_patterns'])}; "
                f"pick={log_mode}"
            ),
            "source_tree": source_tree,
        }

    # ------------------------------------------------------------------

    @staticmethod
    def _parse(data: Any, source_path: Path | None = None) -> list[ModelInfo]:
        if isinstance(data, dict) and "models" in data:
            raw_list = data["models"]
        elif isinstance(data, list):
            raw_list = data
        elif isinstance(data, dict):
            raw_list = [data]
        else:
            return []

        infos: list[ModelInfo] = []
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            infos.append(ModelInfo(
                name=item.get("name") or (source_path.parent.name if source_path else "unknown"),
                quantization=item.get("quantization", "fp32"),
                has_test_data=bool(item.get("has_test_data", False)),
                config_path=ConfigReader._resolve_path(item.get("config_path", source_path or ""), source_path),
                log_path=ConfigReader._resolve_path(item.get("log_path", ""), source_path),
                package_info_path=ConfigReader._resolve_path(item.get("package_info_path", ""), source_path),
                extra=item.get("extra", {}),
            ))
        return infos

    @staticmethod
    def _looks_like_model_config(data: Any) -> bool:
        if isinstance(data, dict) and "models" in data:
            return True
        if isinstance(data, list):
            return any(isinstance(item, dict) and "name" in item for item in data)
        if isinstance(data, dict):
            expected = {
                "name",
                "quantization",
                "has_test_data",
                "config_path",
                "log_path",
                "package_info_path",
                "extra",
            }
            return bool(expected.intersection(data.keys()))
        return False

    @staticmethod
    def _resolve_path(value: Any, source_path: Path | None) -> str:
        if not value:
            return ""
        path = Path(str(value))
        if path.is_absolute() or source_path is None:
            return str(path)
        return str((source_path.parent / path).resolve())

    @staticmethod
    def _build_config_context(
        model_dir: Path,
        primary_config_path: str,
        patterns: list[str],
        max_files: int,
    ) -> dict[str, Any]:
        files: list[Path] = []
        seen: set[str] = set()

        def _add(path: Path) -> None:
            resolved = path.resolve()
            key = str(resolved)
            if key in seen or not resolved.exists() or not resolved.is_file():
                return
            seen.add(key)
            files.append(resolved)

        if primary_config_path:
            _add(Path(primary_config_path))

        for pattern in ConfigReader._expand_patterns(patterns, model_dir.name):
            for path in ConfigReader._iter_pattern_matches(model_dir, pattern):
                _add(path)
                if len(files) >= max_files:
                    break
            if len(files) >= max_files:
                break

        summary_parts: list[str] = []
        for path in files[:max_files]:
            try:
                text = path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            if not text:
                continue
            summary_parts.append(f"[{path.relative_to(model_dir)}]\n{text}")

        return {
            "files": [str(path) for path in files[:max_files]],
            "summary": "\n\n".join(summary_parts),
        }

    @staticmethod
    def _find_model_config(model_dir: Path, config_patterns: list[str]) -> Path | None:
        expanded_patterns = ConfigReader._expand_patterns(config_patterns, model_dir.name)
        preferred = [model_dir / pattern for pattern in expanded_patterns if "/" not in pattern]
        for path in preferred:
            if path.exists():
                return path

        candidates = [
            path
            for pattern in expanded_patterns
            for path in ConfigReader._iter_pattern_matches(model_dir, pattern)
            if path.is_file() and path.name != "package_info.json"
        ]
        return candidates[0] if candidates else None

    @staticmethod
    def _iter_model_dirs(root: Path, pattern: str) -> list[Path]:
        if not root.exists():
            return []
        if pattern in {"", "*"}:
            return sorted(path for path in root.iterdir() if path.is_dir())
        return sorted(path for path in root.glob(pattern) if path.is_dir())

    @staticmethod
    def _resolve_package_info_path(model_dir: Path, explicit_path: str, patterns: list[str]) -> str:
        if explicit_path:
            path = Path(explicit_path)
            return str(path.resolve()) if path.exists() else ""
        for pattern in ConfigReader._expand_patterns(patterns, model_dir.name):
            for path in ConfigReader._iter_pattern_matches(model_dir, pattern):
                if path.is_file():
                    return str(path.resolve())
        return ""

    @staticmethod
    def _resolve_log_path(
        model_dir: Path,
        explicit_path: str,
        file_patterns: list[str],
        dir_patterns: list[str],
        latest_only: bool,
    ) -> str:
        if explicit_path:
            resolved = ConfigReader._pick_latest_log_source(Path(explicit_path), latest_only)
            return str(resolved.resolve()) if resolved else ""

        candidates: list[Path] = []
        for pattern in ConfigReader._expand_patterns(file_patterns, model_dir.name):
            candidates.extend(path for path in ConfigReader._iter_pattern_matches(model_dir, pattern) if path.is_file())
        for pattern in ConfigReader._expand_patterns(dir_patterns, model_dir.name):
            for log_dir in ConfigReader._iter_pattern_matches(model_dir, pattern):
                if log_dir.is_dir():
                    candidates.extend(path for path in log_dir.rglob("*") if path.is_file())

        chosen = ConfigReader._pick_latest(candidates) if latest_only else (sorted(candidates)[0] if candidates else None)
        return str(chosen.resolve()) if chosen else ""

    @staticmethod
    def _pick_latest_log_source(path: Path, latest_only: bool) -> Path | None:
        if not path.exists():
            return None
        if path.is_file():
            return path
        candidates = [candidate for candidate in path.rglob("*") if candidate.is_file()]
        if not candidates:
            return None
        return ConfigReader._pick_latest(candidates) if latest_only else sorted(candidates)[0]

    @staticmethod
    def _pick_latest(paths: list[Path]) -> Path | None:
        if not paths:
            return None
        return max(paths, key=lambda path: (path.stat().st_mtime, str(path)))

    @staticmethod
    def _find_layout_path(target_dir: Path, explicit_path: Path | None) -> Path | None:
        if explicit_path:
            return explicit_path
        for candidate in (target_dir / "target_layout.yaml", target_dir / "target_layout.yml"):
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _expand_patterns(patterns: list[str], model_name: str) -> list[str]:
        return [pattern.replace("{model_name}", model_name) for pattern in patterns]

    @staticmethod
    def _iter_pattern_matches(root: Path, pattern: str) -> list[Path]:
        normalized = pattern.strip()
        if not normalized:
            return []
        iterator = root.glob(normalized) if "/" in normalized or "\\" in normalized else root.rglob(normalized)
        return sorted(iterator)

    @staticmethod
    def _render_pattern_example(pattern: str) -> str:
        return pattern.replace("{model_name}", "<model-name>")

    @staticmethod
    def _as_patterns(value: Any, default: list[str]) -> list[str]:
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return list(default)

    @staticmethod
    def _as_positive_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default
