"""Tests for LLM client helpers without real network calls."""

from model_test_agent.llm.client import check_all_profiles


class TestLLMClientHelpers:
    def test_check_all_profiles_uses_service_specific_health_checks(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "model_test_agent.llm.client._load_profiles",
            lambda config_path: {
                "default": {"model": "chat-model"},
                "embedding": {"model": "embed-model"},
                "reranker": {"model": "rerank-model", "top_n": 3},
            },
        )

        calls: list[tuple[str, str, int]] = []

        class DummyClient:
            def __init__(self, profile: str, config_path: str) -> None:
                self.profile = profile

            def health_check(self, timeout: int = 10) -> dict:
                calls.append(("chat", self.profile, timeout))
                return {
                    "ok": True,
                    "profile": self.profile,
                    "kind": "chat",
                    "model": "demo-model",
                    "latency_ms": timeout,
                    "error": "",
                }

        monkeypatch.setattr("model_test_agent.llm.client.LLMClient", DummyClient)
        monkeypatch.setattr(
            "model_test_agent.llm.client._check_embedding_profile",
            lambda name, cfg, timeout: {
                "ok": True,
                "profile": name,
                "kind": "embedding",
                "model": cfg["model"],
                "latency_ms": timeout,
                "error": "",
            },
        )
        monkeypatch.setattr(
            "model_test_agent.llm.client._check_reranker_profile",
            lambda name, cfg, timeout: {
                "ok": True,
                "profile": name,
                "kind": "reranker",
                "model": cfg["model"],
                "latency_ms": timeout,
                "error": "",
            },
        )

        results = check_all_profiles(timeout=3)

        assert calls == [("chat", "default", 3)]
        assert results == [
            {
                "ok": True,
                "profile": "default",
                "kind": "chat",
                "model": "demo-model",
                "latency_ms": 3,
                "error": "",
            },
            {
                "ok": True,
                "profile": "embedding",
                "kind": "embedding",
                "model": "embed-model",
                "latency_ms": 3,
                "error": "",
            },
            {
                "ok": True,
                "profile": "reranker",
                "kind": "reranker",
                "model": "rerank-model",
                "latency_ms": 3,
                "error": "",
            },
        ]
