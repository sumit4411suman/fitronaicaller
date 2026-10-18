from sellagent_ai.llm.base import (
    CancelToken,
    ChatMessage,
    GenerationResult,
    LLMProvider,
    ProviderUnavailable,
    collect,
)
from sellagent_ai.llm.llamacpp import LlamaCppProvider
from sellagent_ai.llm.null import NullProvider
from sellagent_ai.llm.ollama import OllamaProvider


def make_provider(kind: str, *, ollama_url: str = "http://127.0.0.1:11434", llamacpp_url: str = "http://127.0.0.1:8080") -> LLMProvider:
    if kind == "ollama":
        return OllamaProvider(ollama_url)
    if kind == "llamacpp":
        return LlamaCppProvider(llamacpp_url)
    return NullProvider()


__all__ = ["CancelToken", "ChatMessage", "GenerationResult", "LLMProvider", "LlamaCppProvider", "NullProvider", "OllamaProvider", "ProviderUnavailable", "collect", "make_provider"]
