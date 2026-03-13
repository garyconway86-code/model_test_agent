"""Interactive CLI prompts with history and path completion."""

from __future__ import annotations

from pathlib import Path

from rich.prompt import Confirm, Prompt

_HISTORY_DIR = Path.home() / ".model-test-agent"
_HISTORY_FILE = _HISTORY_DIR / "prompt-history.txt"

try:
    from prompt_toolkit import prompt
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import PathCompleter, WordCompleter
    from prompt_toolkit.history import FileHistory

    _HAS_PROMPT_TOOLKIT = True
except ImportError:  # pragma: no cover - exercised via fallback behavior
    _HAS_PROMPT_TOOLKIT = False


class InteractivePrompter:
    """Prompt wrapper with graceful fallback when prompt_toolkit is unavailable."""

    def __init__(self) -> None:
        self._history = None
        if _HAS_PROMPT_TOOLKIT:
            _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
            self._history = FileHistory(str(_HISTORY_FILE))

    def ask_path(
        self,
        message: str,
        default: str = "",
        only_directories: bool = False,
    ) -> str:
        if not _HAS_PROMPT_TOOLKIT or self._history is None:
            return Prompt.ask(message, default=default)

        value = prompt(
            f"{message}: ",
            default=default,
            history=self._history,
            auto_suggest=AutoSuggestFromHistory(),
            completer=PathCompleter(
                expanduser=True,
                only_directories=only_directories,
            ),
            complete_while_typing=True,
        )
        return value.strip()

    def ask_choice(self, message: str, choices: list[str], default: str) -> str:
        if not _HAS_PROMPT_TOOLKIT or self._history is None:
            return Prompt.ask(message, choices=choices, default=default)

        completer = WordCompleter(choices, ignore_case=False)
        while True:
            value = prompt(
                f"{message}: ",
                default=default,
                history=self._history,
                auto_suggest=AutoSuggestFromHistory(),
                completer=completer,
                complete_while_typing=True,
            ).strip()
            if value in choices:
                return value

    def confirm(self, message: str, default: bool = False) -> bool:
        if not _HAS_PROMPT_TOOLKIT or self._history is None:
            return Confirm.ask(message, default=default)

        suffix = "Y/n" if default else "y/N"
        while True:
            value = prompt(
                f"{message} [{suffix}]: ",
                history=self._history,
                auto_suggest=AutoSuggestFromHistory(),
            ).strip().lower()
            if not value:
                return default
            if value in {"y", "yes"}:
                return True
            if value in {"n", "no"}:
                return False
