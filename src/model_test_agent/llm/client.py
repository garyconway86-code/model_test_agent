"""Unified LLM client that reads profiles from config/llm.yaml.

All internal models expose an OpenAI-compatible ``/v1/chat/completions``
endpoint, so we use ``langchain-openai`` under the hood.  Switching models
is as simple as changing the profile name in the YAML file.

Usage::

    client = get_llm_client("classifier")   # profile defined in llm.yaml
    response = client.invoke("Classify this error: ...")
"""

from __future__ import annotations

import functools
import json
import urllib.request
from pathlib import Path
from typing import Any

import os
import re

import yaml
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
from langchain_openai import ChatOpenAI

# Default config location (relative to project root).
_DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "config" / "llm.yaml"


def _expand_env_vars(obj: Any) -> Any:
    """Recursively expand ${VAR} placeholders in string values."""
    if isinstance(obj, str):
        return re.sub(r"\$\{([^}]+)\}", lambda m: os.environ.get(m.group(1), m.group(0)), obj)
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(i) for i in obj]
    return obj


def _load_profiles(config_path: Path | str = _DEFAULT_CONFIG) -> dict[str, dict[str, Any]]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"LLM config not found: {path}")
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return _expand_env_vars(raw)


def _infer_profile_kind(name: str, cfg: dict[str, Any]) -> str:
    """Infer the service kind for a profile."""
    explicit = str(cfg.get("type", "")).strip().lower()
    if explicit in {"chat", "embedding", "reranker"}:
        return explicit
    if "top_n" in cfg:
        return "reranker"
    if "embed" in name.lower():
        return "embedding"
    return "chat"


class LLMClient:
    """Facade over one LLM profile.

    Parameters
    ----------
    profile : str
        Name of the profile in ``config/llm.yaml``.
    config_path : Path | str
        Override the default config location.
    overrides : dict
        Runtime overrides merged on top of the YAML values (e.g. temperature).
    """

    def __init__(
        self,
        profile: str = "default",
        config_path: Path | str = _DEFAULT_CONFIG,
        **overrides: Any,
    ) -> None:
        profiles = _load_profiles(config_path)
        if profile not in profiles:
            available = ", ".join(profiles.keys())
            raise KeyError(f"Unknown LLM profile '{profile}'. Available: {available}")

        cfg = {**profiles[profile], **overrides}
        kind = _infer_profile_kind(profile, cfg)
        if kind != "chat":
            raise ValueError(
                f"Profile '{profile}' is a {kind} service and cannot be used as a chat model."
            )
        self.profile_name = profile
        self.model_name: str = cfg.pop("model")
        self._chat = ChatOpenAI(
            model=self.model_name,
            openai_api_base=cfg.pop("base_url"),
            openai_api_key=cfg.pop("api_key"),
            temperature=cfg.pop("temperature", 0.1),
            max_tokens=cfg.pop("max_tokens", 4096),
            request_timeout=cfg.pop("timeout", 120),
            **cfg,
        )

    # --- Public API ---

    def invoke(self, prompt: str) -> str:
        """Send a single user message and return the assistant reply."""
        result = self._chat.invoke(prompt)
        return str(result.content)

    def invoke_messages(self, messages: list[dict[str, str]]) -> str:
        """Send a full message list (system / user / assistant) and return reply."""
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        _MAP = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}
        lc_msgs = [_MAP[m["role"]](content=m["content"]) for m in messages]
        result = self._chat.invoke(lc_msgs)
        return str(result.content)

    @property
    def langchain_model(self) -> ChatOpenAI:
        """Expose the underlying LangChain model for direct use in graph nodes."""
        return self._chat

    def health_check(self, timeout: int = 10) -> dict[str, Any]:
        """Ping the LLM API and return status info.

        Returns a dict with keys: ``ok``, ``profile``, ``model``, ``latency_ms``, ``error``.
        """
        import time

        result: dict[str, Any] = {
            "ok": False,
            "profile": self.profile_name,
            "model": self.model_name,
            "latency_ms": 0,
            "error": "",
        }
        start = time.monotonic()
        try:
            # Minimal request to test connectivity
            original_timeout = self._chat.request_timeout
            self._chat.request_timeout = timeout
            response = self._chat.invoke("ping")
            elapsed = (time.monotonic() - start) * 1000
            result["ok"] = True
            result["latency_ms"] = round(elapsed, 1)
            self._chat.request_timeout = original_timeout
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            result["latency_ms"] = round(elapsed, 1)
            result["error"] = str(exc)
        return result

    def __repr__(self) -> str:
        return f"LLMClient(profile={self.profile_name!r}, model={self.model_name!r})"


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

@functools.lru_cache(maxsize=16)
def get_llm_client(
    profile: str = "default",
    config_path: str = str(_DEFAULT_CONFIG),
) -> LLMClient:
    """Return a cached :class:`LLMClient` for *profile*."""
    return LLMClient(profile=profile, config_path=config_path)


def check_all_profiles(
    config_path: str = str(_DEFAULT_CONFIG),
    timeout: int = 10,
) -> list[dict[str, Any]]:
    """Health-check every LLM profile defined in the config.

    Returns a list of status dicts (one per profile).
    """
    profiles = _load_profiles(config_path)
    results = []
    for name, cfg in profiles.items():
        kind = _infer_profile_kind(name, cfg)
        try:
            if kind == "embedding":
                results.append(_check_embedding_profile(name, cfg, timeout))
            elif kind == "reranker":
                results.append(_check_reranker_profile(name, cfg, timeout))
            else:
                client = LLMClient(profile=name, config_path=config_path)
                result = client.health_check(timeout=timeout)
                result["kind"] = "chat"
                results.append(result)
        except Exception as exc:
            results.append({
                "ok": False,
                "profile": name,
                "kind": kind,
                "model": cfg.get("model", "?"),
                "latency_ms": 0,
                "error": str(exc),
            })
    return results


def _check_embedding_profile(name: str, cfg: dict[str, Any], timeout: int) -> dict[str, Any]:
    """Health-check an embedding endpoint."""
    import time

    result = {
        "ok": False,
        "profile": name,
        "kind": "embedding",
        "model": cfg.get("model", "?"),
        "latency_ms": 0,
        "error": "",
    }
    start = time.monotonic()
    try:
        client = OpenAI(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            timeout=timeout,
        )
        client.embeddings.create(model=cfg["model"], input=["ping"])
        result["ok"] = True
    except Exception as exc:
        result["error"] = str(exc)
    result["latency_ms"] = round((time.monotonic() - start) * 1000, 1)
    return result


def _check_reranker_profile(name: str, cfg: dict[str, Any], timeout: int) -> dict[str, Any]:
    """Health-check a Cohere-compatible rerank endpoint."""
    import time

    result = {
        "ok": False,
        "profile": name,
        "kind": "reranker",
        "model": cfg.get("model", "?"),
        "latency_ms": 0,
        "error": "",
    }
    payload = json.dumps({
        "model": cfg["model"],
        "query": "ping",
        "documents": ["ping", "pong"],
        "top_n": 1,
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
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        if "results" not in data:
            raise ValueError("missing 'results' in rerank response")
        result["ok"] = True
    except Exception as exc:
        result["error"] = str(exc)
    result["latency_ms"] = round((time.monotonic() - start) * 1000, 1)
    return result
