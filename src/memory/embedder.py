"""Azure OpenAI text embedding client for the HiveMind memory layer."""

from __future__ import annotations

import logging
import os
import time

from openai import AzureOpenAI

logger = logging.getLogger(__name__)

_MAX_CHARS = 32000
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)


def embed_text(text: str) -> list[float]:
    """Embed text using Azure OpenAI text-embedding-3-small (1536-dim).

    Synchronous and makes a network call — callers in async contexts must
    wrap with ``await asyncio.to_thread(embed_text, text)``.
    """

    client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"),
    )
    deployment = os.environ["AZURE_OPENAI_EMBEDDING_DEPLOYMENT"]
    truncated = text[:_MAX_CHARS]

    last_exc: Exception = RuntimeError("embed_text: no attempts were made")
    for attempt in range(_MAX_ATTEMPTS):
        try:
            response = client.embeddings.create(model=deployment, input=truncated)
            return response.data[0].embedding
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "embed_text attempt %s/%s failed: %s", attempt + 1, _MAX_ATTEMPTS, exc
            )
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(_BACKOFF_SECONDS[attempt])

    raise last_exc
