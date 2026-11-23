"""Shared MiniLM sentence embedder, used by the cache and the router."""
from functools import lru_cache

import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    # CPU keeps the GPU free for the local LLM, so GPU power readings stay clean.
    try:
        return SentenceTransformer(MODEL_NAME, device="cpu", local_files_only=True)  # works offline
    except Exception:
        return SentenceTransformer(MODEL_NAME, device="cpu")  # first run: download once


def embed(texts: list[str]) -> np.ndarray:
    """L2-normalised float32 embeddings, shape (n, 384). Dot product = cosine similarity."""
    return _model().encode(texts, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)
