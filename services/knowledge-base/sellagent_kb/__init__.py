"""FITRON knowledge base: approved facts only, FTS5 retrieval with citations, injection screening."""

from sellagent_kb.service import (
    KnowledgeError,
    RetrievedChunk,
    approve,
    create_document,
    expire_outdated,
    reject,
    retrieve,
    screen_for_injection,
    seed_fitron_defaults,
    supersede,
)

__all__ = [
    "KnowledgeError", "RetrievedChunk", "approve", "create_document", "expire_outdated", "reject", "retrieve",
    "screen_for_injection", "seed_fitron_defaults", "supersede",
]
