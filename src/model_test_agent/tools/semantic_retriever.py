"""Semantic retrieval over historical debug cases.

Uses the company's embedding + rerank services to find the most relevant
historical cases for a given error query.

Falls back to HistoryStore.find_similar (keyword-overlap scoring) when
the embedding service is unavailable or misconfigured.
"""

from __future__ import annotations

import math
import urllib.error
import urllib.parse
import urllib.request
import json
import logging
from typing import Any

from openai import OpenAI

from model_test_agent.llm.client import _load_profiles
from model_test_agent.tools.history_store import HistoryStore

logger = logging.getLogger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b + 1e-9)


class SemanticRetriever:
    """Find similar historical cases using embedding + rerank services.

    Parameters
    ----------
    store :
        Backing :class:`HistoryStore`; created with defaults if omitted.
    embed_profile :
        Profile name in ``config/llm.yaml`` for the embedding service.
    rerank_profile :
        Profile name in ``config/llm.yaml`` for the reranker service.
    """

    def __init__(
        self,
        store: HistoryStore | None = None,
        embed_profile: str = "embedding",
        rerank_profile: str = "reranker",
    ) -> None:
        self._store = store or HistoryStore()
        profiles = _load_profiles()
        self._embed_cfg = profiles.get(embed_profile)
        self._rerank_cfg = profiles.get(rerank_profile)
        self._use_semantic = self._probe_embedding()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_similar(
        self,
        error_category: str,
        key_log: str = "",
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        """Return the *top_k* most relevant historical cases.

        Falls back to keyword scoring if the embedding service is down.
        """
        if not self._use_semantic:
            return self._store.find_similar(error_category, key_log, top_k)

        cases = self._store.get_all()
        if not cases:
            return []

        query = f"{error_category}: {key_log}"
        texts = [f"{c['error_category']}: {c.get('key_log', '')}" for c in cases]

        try:
            query_vec, case_vecs = self._embed([query] + texts)
        except Exception as exc:
            logger.warning("Embedding call failed (%s), falling back to keyword search.", exc)
            return self._store.find_similar(error_category, key_log, top_k)

        # Cosine similarity ranking
        scores = [_cosine(query_vec, cv) for cv in case_vecs]
        candidate_k = min(top_k * 3, len(cases))
        ranked = sorted(range(len(cases)), key=lambda i: scores[i], reverse=True)
        candidates = [cases[i] for i in ranked[:candidate_k]]

        if self._rerank_cfg:
            try:
                return self._rerank(query, candidates, top_k)
            except Exception as exc:
                logger.warning("Rerank call failed (%s), using embedding ranking.", exc)

        return candidates[:top_k]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _probe_embedding(self) -> bool:
        """Return True if the embedding service is reachable."""
        if not self._embed_cfg:
            return False
        try:
            client = OpenAI(
                base_url=self._embed_cfg["base_url"],
                api_key=self._embed_cfg["api_key"],
                timeout=5,
            )
            client.embeddings.create(model=self._embed_cfg["model"], input=["ping"])
            return True
        except Exception as exc:
            logger.info("Embedding service unavailable (%s), using keyword fallback.", exc)
            return False

    def _embed(self, texts: list[str]) -> tuple[list[float], list[list[float]]]:
        """Embed *texts* and return (query_vec, case_vecs)."""
        client = OpenAI(
            base_url=self._embed_cfg["base_url"],
            api_key=self._embed_cfg["api_key"],
            timeout=self._embed_cfg.get("timeout", 10),
        )
        resp = client.embeddings.create(model=self._embed_cfg["model"], input=texts)
        vecs = [item.embedding for item in resp.data]
        return vecs[0], vecs[1:]

    def _rerank(
        self, query: str, candidates: list[dict[str, Any]], top_n: int
    ) -> list[dict[str, Any]]:
        """Rerank *candidates* using a Cohere-compatible rerank endpoint."""
        documents = [
            f"{c['error_category']}: {c.get('key_log', '')} | {c.get('root_cause', '')}"
            for c in candidates
        ]
        cfg = self._rerank_cfg
        payload = json.dumps({
            "model": cfg["model"],
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }).encode()
        req = urllib.request.Request(
            url=f"{cfg['base_url'].rstrip('/')}/rerank",
            data=payload,
            headers={
                "Authorization": f"Bearer {cfg['api_key']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=cfg.get("timeout", 10)) as resp:
            results = json.loads(resp.read())["results"]
        return [candidates[r["index"]] for r in results]
