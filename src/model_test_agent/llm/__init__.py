"""LLM client abstraction — thin wrapper around OpenAI-compatible endpoints."""

from model_test_agent.llm.client import LLMClient, check_all_profiles, get_llm_client

__all__ = ["LLMClient", "check_all_profiles", "get_llm_client"]
