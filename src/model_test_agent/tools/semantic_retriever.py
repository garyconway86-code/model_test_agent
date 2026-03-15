"""History retriever with a semantic-search compatible interface.

The current implementation keeps retrieval local and deterministic by
delegating to :class:`HistoryStore`.  The embedding client is initialized
only when history exists, which keeps tests and offline runs cheap.
"""

from __future__ import annotations

from pathlib import Path

from openai import OpenAI

from model_test_agent.debug_config import load_debug_settings
from model_test_agent.llm.client import _load_profiles, _profile_is_configured
from model_test_agent.tools.history_store import HistoryStore
from model_test_agent.tools.knowledge_base import KnowledgeBase


class SemanticRetriever:
    """Find similar historical cases for one error category."""

    def __init__(
        self,
        store: HistoryStore | None = None,
        config_path: str | Path | None = None,
        knowledge_dir: str | Path | None = None,
    ) -> None:
        settings = load_debug_settings()
        retrieval = settings.retrieval
        self.store = store or HistoryStore()
        self.config_path = config_path
        self.default_top_k = retrieval.top_k
        self.knowledge_base = (
            KnowledgeBase(
                knowledge_dir,
                chunk_size=retrieval.knowledge_chunk_size,
                overlap=retrieval.knowledge_chunk_overlap,
                excerpt_chars=retrieval.knowledge_excerpt_chars,
                embedding_input_chars=retrieval.embedding_input_chars,
            )
            if knowledge_dir
            else None
        )
        self._embedding_client: OpenAI | None = None

    def find_similar(
        self,
        error_category: str,
        key_log: str = "",
        top_k: int | None = None,
    ) -> list[dict]:
        """Return relevant history cases and optional local RAG snippets."""
        top_k = top_k or self.default_top_k
        results: list[dict] = []
        if self.store.get_all():
            results.extend(self.store.find_similar(error_category, key_log=key_log, top_k=top_k))

        if self.knowledge_base and self.knowledge_base.exists():
            query = f"{error_category}\n{key_log}".strip()
            results.extend(self.knowledge_base.search(
                query=query,
                top_k=top_k,
                embedding_client=self.embedding_client(),
                embedding_model=self.embedding_model_name(),
            ))
        return results[:top_k]

    def embedding_client(self) -> OpenAI | None:
        """Lazily build the embedding client when callers need it."""
        if self._embedding_client is not None:
            return self._embedding_client
        profiles = _load_profiles(self.config_path) if self.config_path else _load_profiles()
        cfg = profiles.get("embedding")
        if not cfg or not _profile_is_configured(cfg):
            return None
        self._embedding_client = OpenAI(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            timeout=cfg.get("timeout", 120),
        )
        return self._embedding_client

    def embedding_model_name(self) -> str:
        """Return the configured embedding model, if any."""
        profiles = _load_profiles(self.config_path) if self.config_path else _load_profiles()
        cfg = profiles.get("embedding") or {}
        if not _profile_is_configured(cfg):
            return ""
        return str(cfg.get("model", ""))
