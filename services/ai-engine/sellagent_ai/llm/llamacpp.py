"""llama.cpp server adapter (llama-server, OpenAI-compatible /v1/chat/completions on localhost)."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from sellagent_ai.llm.base import CancelToken, ChatMessage, GenerationCancelled, ProviderUnavailable


class LlamaCppProvider:
    name = "llamacpp"

    def __init__(self, base_url: str = "http://127.0.0.1:8080", client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client

    def _c(self) -> httpx.Client:
        return self._client or httpx.Client(timeout=10.0, trust_env=False)

    def available(self) -> tuple[bool, str]:
        try:
            r = self._c().get(f"{self.base_url}/health")
            r.raise_for_status()
            return True, "llama-server healthy"
        except Exception as exc:  # noqa: BLE001
            return False, f"llama-server not reachable at {self.base_url}: {exc.__class__.__name__}"

    def list_models(self) -> list[dict]:
        try:
            r = self._c().get(f"{self.base_url}/v1/models")
            r.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailable(str(exc)) from exc
        return [{"name": m.get("id")} for m in r.json().get("data", [])]

    def stream(self, messages: list[ChatMessage], *, model: str, temperature: float = 0.3, max_tokens: int = 256, cancel: CancelToken | None = None, timeout: float = 60.0) -> Iterator[str]:
        body = {"model": model, "stream": True, "temperature": temperature, "max_tokens": max_tokens, "messages": [{"role": m.role, "content": m.content} for m in messages]}
        try:
            with self._c().stream("POST", f"{self.base_url}/v1/chat/completions", json=body, timeout=timeout) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if cancel and cancel.cancelled:
                        raise GenerationCancelled()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        return
                    data = json.loads(payload)
                    delta = (data.get("choices") or [{}])[0].get("delta") or {}
                    if delta.get("content"):
                        yield delta["content"]
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"llama-server request failed: {exc}") from exc
