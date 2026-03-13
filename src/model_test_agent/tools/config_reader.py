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
