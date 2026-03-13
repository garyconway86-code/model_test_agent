"""History retriever with a semantic-search compatible interface.

The current implementation keeps retrieval local and deterministic by
delegating to :class:`HistoryStore`.  The embedding client is initialized
only when history exists, which keeps tests and offline runs cheap.
"""

from __future__ import annotations

from pathlib import Path

from openai import OpenAI

from model_test_agent.llm.client import _load_profiles
from model_test_agent.tools.history_store import HistoryStore


class SemanticRetriever:
    """Find similar historical cases for one error category."""

    def __init__(
        self,
        store: HistoryStore | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        self.store = store or HistoryStore()
        self.config_path = config_path
        self._embedding_client: OpenAI | None = None

    def find_similar(
        self,
        error_category: str,
        key_log: str = "",
        top_k: int = 3,
    ) -> list[dict]:
        """Return similar cases without initializing remote clients for empty history."""
        if not self.store.get_all():
            return []
        return self.store.find_similar(error_category, key_log=key_log, top_k=top_k)

    def embedding_client(self) -> OpenAI | None:
        """Lazily build the embedding client when callers need it."""
        if self._embedding_client is not None:
            return self._embedding_client
        profiles = _load_profiles(self.config_path) if self.config_path else _load_profiles()
        cfg = profiles.get("embedding")
        if not cfg:
            return None
        self._embedding_client = OpenAI(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            timeout=cfg.get("timeout", 120),
        )
        return self._embedding_client
