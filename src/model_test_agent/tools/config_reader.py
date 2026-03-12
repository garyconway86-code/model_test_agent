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

        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if data is None:
            return []

        return ConfigReader._parse(data)

    @staticmethod
    def read_directory(dir_path: str | Path, suffix: str = ".yaml") -> list[ModelInfo]:
        """Read all YAML files in *dir_path* and merge into one list."""
        results: list[ModelInfo] = []
        for p in sorted(Path(dir_path).glob(f"*{suffix}")):
            results.extend(ConfigReader.read_file(p))
        return results

    # ------------------------------------------------------------------

    @staticmethod
    def _parse(data: Any) -> list[ModelInfo]:
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
                name=item.get("name", "unknown"),
                quantization=item.get("quantization", "fp32"),
                has_test_data=bool(item.get("has_test_data", False)),
                config_path=str(item.get("config_path", "")),
                extra=item.get("extra", {}),
            ))
        return infos
