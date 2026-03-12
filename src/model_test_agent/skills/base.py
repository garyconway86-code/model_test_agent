"""Base class for all Skills.

A *Skill* is a unit of work that uses an LLM to make decisions.  Skills are
configurable: the prompt template, LLM profile, and output parser can all be
swapped via subclass overrides or constructor arguments.

Design goals:
  - Each Skill is a standalone callable — easy to test in isolation.
  - Skills compose with Tools: a Skill may call Tools before/after the LLM.
  - Skills are stateless; all context is passed explicitly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from model_test_agent.llm.client import LLMClient, get_llm_client


class BaseSkill(ABC):
    """Abstract base for all skills.

    Parameters
    ----------
    llm_profile : str
        Name of the LLM profile in ``config/llm.yaml``.
    llm_config_path : str | None
        Override the default LLM config path.
    """

    def __init__(
        self,
        llm_profile: str = "default",
        llm_config_path: str | None = None,
    ) -> None:
        kwargs: dict[str, str] = {"profile": llm_profile}
        if llm_config_path:
            kwargs["config_path"] = llm_config_path
        self._llm: LLMClient = get_llm_client(**kwargs)

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """Execute the skill with the given keyword arguments."""

    def _build_messages(self, system: str, user: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
