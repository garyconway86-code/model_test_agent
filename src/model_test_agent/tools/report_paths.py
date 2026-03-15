"""Stable report paths derived from the target directory."""

from __future__ import annotations

import hashlib
from pathlib import Path


def stable_target_id(target_path: str | Path) -> str:
    """Return a stable filesystem-friendly identifier for one target directory."""
    resolved = Path(target_path).resolve()
    label = resolved.name or "target"
    digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:8]
    safe_label = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in label).strip("-")
    return f"{safe_label or 'target'}-{digest}"


def report_output_dir(output_dir: str | Path, target_dir: str | Path) -> Path:
    """Return the stable report directory for one target directory."""
    base = Path(output_dir or ".").resolve()
    resolved_target = Path(target_dir).resolve()
    report_dir = base / stable_target_id(resolved_target)
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def report_artifacts(output_dir: str | Path, target_dir: str | Path) -> dict[str, Path]:
    """Return stable report artifact paths for one target directory."""
    base_dir = report_output_dir(output_dir, target_dir)
    return {
        "dir": base_dir,
        "html": base_dir / "report.html",
        "xlsx": base_dir / "report.xlsx",
        "review": base_dir / "report.review.json",
    }
