"""Provider-agnostic local LLM interface. All providers run on localhost; none call paid APIs."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol


class ProviderUnavailable(RuntimeError):
    pass


class GenerationCancelled(RuntimeError):
    pass


@dataclass
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class GenerationResult:
    text: str
    model: str
    provider: str
    first_token_ms: float | None
    total_ms: float
    completion_tokens: int | None
    prompt_tokens: int | None
    tokens_per_second: float | None
    cancelled: bool = False
    raw: dict = field(default_factory=dict)


class CancelToken:
    def __init__(self) -> None:
        self._ev = threading.Event()

    def cancel(self) -> None:
        self._ev.set()

    @property
    def cancelled(self) -> bool:
        return self._ev.is_set()


class LLMProvider(Protocol):
    name: str

    def available(self) -> tuple[bool, str]: ...

    def list_models(self) -> list[dict]: ...

    def stream(self, messages: list[ChatMessage], *, model: str, temperature: float = 0.3, max_tokens: int = 256, cancel: CancelToken | None = None, timeout: float = 60.0) -> Iterator[str]: ...


def collect(provider: LLMProvider, messages: list[ChatMessage], *, model: str, cancel: CancelToken | None = None, **kw) -> GenerationResult:
    """Drive a provider's stream and measure first-token latency and throughput."""
    t0 = time.perf_counter()
    first: float | None = None
    parts: list[str] = []
    cancelled = False
    try:
        for piece in provider.stream(messages, model=model, cancel=cancel, **kw):
            if first is None:
                first = time.perf_counter()
            parts.append(piece)
    except GenerationCancelled:
        cancelled = True
    total = time.perf_counter() - t0
    text = "".join(parts)
    approx_tokens = max(1, len(text) // 4) if text else 0
    gen_time = (time.perf_counter() - first) if first else None
    tps = (approx_tokens / gen_time) if gen_time and gen_time > 0 else None
    return GenerationResult(
        text=text, model=model, provider=provider.name, first_token_ms=((first - t0) * 1000) if first else None,
        total_ms=total * 1000, completion_tokens=approx_tokens or None, prompt_tokens=None, tokens_per_second=tps, cancelled=cancelled,
    )
