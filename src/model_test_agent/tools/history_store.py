"""Persistent store for historical debug cases.

Uses a simple JSON file — no vector database needed.  Matching is done via
keyword overlap on ``error_category`` and ``key_log`` fields.  This keeps the
system lightweight and easy to audit.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_STORE = Path(__file__).resolve().parents[3] / "history" / "cases.json"


class HistoryStore:
    """Read and write historical debug cases.

    Parameters
    ----------
    store_path : Path | str
        JSON file that holds the case list.
    """

    def __init__(self, store_path: str | Path = _DEFAULT_STORE) -> None:
        self.store_path = Path(store_path)
        self._cases: list[dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> list[dict[str, Any]]:
        if self._cases is not None:
            return self._cases
        if self.store_path.exists():
            with open(self.store_path, encoding="utf-8") as fh:
                self._cases = json.load(fh)
        else:
            self._cases = []
        return self._cases

    def _save(self) -> None:
        cases = self._load()
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.store_path, "w", encoding="utf-8") as fh:
            json.dump(cases, fh, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def find_similar(
        self,
        error_category: str,
        key_log: str = "",
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Return up to *top_k* cases that match *error_category* or share
        keywords with *key_log*.
        """
        cases = self._load()
        scored: list[tuple[float, dict[str, Any]]] = []

        log_words = set(key_log.lower().split())

        for case in cases:
            score = 0.0
            if case.get("error_category", "").lower() == error_category.lower():
                score += 5.0
            case_words = set(case.get("key_log", "").lower().split())
            overlap = log_words & case_words
            score += len(overlap)
            if case.get("effective"):
                score += 2.0
            if score > 0:
                scored.append((score, case))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:top_k]]

    def get_all(self) -> list[dict[str, Any]]:
        return list(self._load())

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_case(
        self,
        error_category: str,
        model_name: str,
        quantization: str,
        key_log: str,
        root_cause: str,
        solution: str,
        effective: bool,
    ) -> str:
        """Append a new case and persist.  Returns the case ID."""
        cases = self._load()
        case_id = f"case-{uuid.uuid4().hex[:8]}"
        cases.append({
            "id": case_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error_category": error_category,
            "model_name": model_name,
            "quantization": quantization,
            "key_log": key_log,
            "root_cause": root_cause,
            "solution": solution,
            "effective": effective,
        })
        self._save()
        return case_id
