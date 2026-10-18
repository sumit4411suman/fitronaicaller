"""Ollama adapter (http://127.0.0.1:11434). Uses the documented /api/chat streaming endpoint."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from sellagent_ai.llm.base import CancelToken, ChatMessage, GenerationCancelled, ProviderUnavailable


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434", client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client

    def _c(self) -> httpx.Client:
        return self._client or httpx.Client(base_url=self.base_url, timeout=10.0, trust_env=False)

    def available(self) -> tuple[bool, str]:
        try:
            r = self._c().get(f"{self.base_url}/api/version")
            r.raise_for_status()
            return True, f"ollama {r.json().get('version', '?')}"
        except Exception as exc:  # noqa: BLE001
            return False, f"Ollama not reachable at {self.base_url}: {exc.__class__.__name__}"

    def list_models(self) -> list[dict]:
        try:
            r = self._c().get(f"{self.base_url}/api/tags")
            r.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailable(str(exc)) from exc
        return [
            {"name": m.get("name"), "size_bytes": m.get("size"), "family": (m.get("details") or {}).get("family"),
             "parameter_size": (m.get("details") or {}).get("parameter_size"), "quantization": (m.get("details") or {}).get("quantization_level")}
            for m in r.json().get("models", [])
        ]

    def pull(self, model: str, *, allow_network: bool) -> Iterator[dict]:
        """Download a model through Ollama. Only allowed when the user enabled external network."""
        if not allow_network:
            raise PermissionError("external network is disabled in privacy settings; enable it to download models")
        with self._c().stream("POST", f"{self.base_url}/api/pull", json={"name": model, "stream": True}, timeout=None) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line:
                    yield json.loads(line)

    def stream(self, messages: list[ChatMessage], *, model: str, temperature: float = 0.3, max_tokens: int = 256, cancel: CancelToken | None = None, timeout: float = 60.0) -> Iterator[str]:
        body = {
            "model": model, "stream": True, "messages": [{"role": m.role, "content": m.content} for m in messages],
            "options": {"temperature": temperature, "num_predict": max_tokens}, "keep_alive": "10m", "think": False,
        }
        try:
            with self._c().stream("POST", f"{self.base_url}/api/chat", json=body, timeout=timeout) as r:
                if r.status_code == 404:
                    raise ProviderUnavailable(f"model {model!r} is not installed in Ollama")
                r.raise_for_status()
                for line in r.iter_lines():
                    if cancel and cancel.cancelled:
                        raise GenerationCancelled()
                    if not line:
                        continue
                    data = json.loads(line)
                    if "error" in data:
                        raise ProviderUnavailable(data["error"])
                    piece = (data.get("message") or {}).get("content", "")
                    if piece:
                        yield piece
                    if data.get("done"):
                        return
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"Ollama request failed: {exc}") from exc
