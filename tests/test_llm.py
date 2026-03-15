"""Tests for LLM client helpers without real network calls."""

from model_test_agent.llm.client import _load_profiles, check_all_profiles


class TestLLMClientHelpers:
    def test_load_profiles_expands_default_chat_env_vars(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("MY_API_KEY", "test-key")
        monkeypatch.setenv("MTA_MODEL_DEFAULT", "deepseek-chat")
        config_path = tmp_path / "llm.yaml"
        config_path.write_text(
            """
default:
  base_url: "https://api.deepseek.com/v1"
  api_key: "${MY_API_KEY}"
  model: "${MTA_MODEL_DEFAULT}"
""".strip(),
            encoding="utf-8",
        )

        profiles = _load_profiles(config_path)

        assert profiles["default"]["base_url"] == "https://api.deepseek.com/v1"
        assert profiles["default"]["api_key"] == "test-key"
        assert profiles["default"]["model"] == "deepseek-chat"

    def test_load_profiles_supports_fallback_env_vars(self, monkeypatch, tmp_path) -> None:
        monkeypatch.delenv("MTA_MODEL_CLASSIFIER", raising=False)
        monkeypatch.delenv("EMBED_BASE_URL", raising=False)
        monkeypatch.delenv("EMBED_API_KEY", raising=False)
        monkeypatch.delenv("EMBED_MODEL", raising=False)
        monkeypatch.setenv("MTA_BASE_URL", "https://api.example.com/v1")
        monkeypatch.setenv("MY_API_KEY", "shared-key")
        monkeypatch.setenv("MTA_MODEL_DEFAULT", "shared-model")
        config_path = tmp_path / "llm.yaml"
        config_path.write_text(
            """
classifier:
  base_url: "${MTA_BASE_URL}"
  api_key: "${MY_API_KEY}"
  model: "${MTA_MODEL_CLASSIFIER:-${MTA_MODEL_DEFAULT}}"
embedding:
  base_url: "${EMBED_BASE_URL:-${MTA_BASE_URL}}"
  api_key: "${EMBED_API_KEY:-${MY_API_KEY}}"
  model: "${EMBED_MODEL}"
""".strip(),
            encoding="utf-8",
        )

        profiles = _load_profiles(config_path)

        assert profiles["classifier"]["model"] == "shared-model"
        assert profiles["embedding"]["base_url"] == "https://api.example.com/v1"
        assert profiles["embedding"]["api_key"] == "shared-key"

    def test_check_all_profiles_uses_service_specific_health_checks(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "model_test_agent.llm.client._load_profiles",
            lambda config_path: {
                "default": {
                    "base_url": "https://api.example.com/v1",
                    "api_key": "key",
                    "model": "chat-model",
                },
                "embedding": {
                    "base_url": "https://api.example.com/v1",
                    "api_key": "key",
                    "model": "embed-model",
                },
                "reranker": {
                    "base_url": "https://api.example.com/v1",
                    "api_key": "key",
                    "model": "rerank-model",
                    "top_n": 3,
                },
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

    def test_check_all_profiles_skips_unconfigured_optional_profiles(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "model_test_agent.llm.client._load_profiles",
            lambda config_path: {
                "default": {
                    "base_url": "https://api.example.com/v1",
                    "api_key": "key",
                    "model": "chat-model",
                },
                "embedding": {
                    "base_url": "",
                    "api_key": "",
                    "model": "",
                },
            },
        )

        class DummyClient:
            def __init__(self, profile: str, config_path: str) -> None:
                self.profile = profile

            def health_check(self, timeout: int = 10) -> dict:
                return {
                    "ok": True,
                    "profile": self.profile,
                    "kind": "chat",
                    "model": "chat-model",
                    "latency_ms": timeout,
                    "error": "",
                }

        monkeypatch.setattr("model_test_agent.llm.client.LLMClient", DummyClient)

        results = check_all_profiles(timeout=3)

        assert results == [
            {
                "ok": True,
                "profile": "default",
                "kind": "chat",
                "model": "chat-model",
                "latency_ms": 3,
                "error": "",
            }
        ]
