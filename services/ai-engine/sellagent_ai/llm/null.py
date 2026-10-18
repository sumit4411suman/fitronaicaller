from __future__ import annotations

from collections.abc import Iterator

from sellagent_ai.llm.base import CancelToken, ChatMessage, ProviderUnavailable


class NullProvider:
    """Used when no local LLM is configured. The conversation engine falls back to approved scripts."""

    name = "none"

    def available(self) -> tuple[bool, str]:
        return False, "no local LLM provider configured"

    def list_models(self) -> list[dict]:
        return []

    def stream(self, messages: list[ChatMessage], *, model: str, temperature: float = 0.3, max_tokens: int = 256, cancel: CancelToken | None = None, timeout: float = 60.0) -> Iterator[str]:
        raise ProviderUnavailable("no local LLM provider configured")
        yield ""  # pragma: no cover
