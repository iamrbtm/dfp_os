"""New category discovery for the Trend Scout microservice.

Phase 3 ships the structure: it returns a stable shape with zero clusters so
the orchestrator does not crash. The full DBSCAN + text-embedding-3-small
implementation lands in Phase 10 — that work is deferred because it requires
the openai/numpy/scikit-learn stack to be present at runtime and tested in
isolation, which is more disruptive than the scoring-only Phase 3 needs to be.
"""

from __future__ import annotations

from typing import Any


async def discover_new_categories(
    session: Any | None = None,
    *,
    api_key: str = "",
    min_samples: int = 5,
) -> dict[str, Any]:
    """Return a stable empty-cluster response.

    The Phase 10 implementation will:
    - Extract noun phrases from snapshot titles via spaCy / regex
    - Embed them with ``text-embedding-3-small``
    - Cluster with DBSCAN(eps=0.4, min_samples=min_samples)
    - Return ``{"clusters": [{"id": ..., "top_phrases": [...], "size": ...}], ...}``
    """
    return {
        "clusters": [],
        "total_clusters_found": 0,
        "total_titles_analyzed": 0,
        "notes": "category discovery deferred to Phase 10 (DBSCAN + embeddings).",
    }
