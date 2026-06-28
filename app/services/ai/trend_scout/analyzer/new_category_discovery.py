from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import cosine_distances
from sqlalchemy.orm import Session

from app.models.trend import TrendSnapshot

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
MIN_CLUSTER_SIZE = 3
EPS = 0.35


def _extract_noun_phrases(text: str) -> list[str]:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    stop_words = {
        "the", "a", "an", "this", "that", "for", "with", "and", "or",
        "of", "to", "in", "on", "by", "is", "it", "its", "new", "set",
        "mini", "large", "small", "tiny", "big", "printed", "printable",
        "3d", "stl", "file", "model", "free", "custom",
    }

    candidates: list[str] = []
    words = text.split()
    current: list[str] = []
    for w in words:
        if w not in stop_words and len(w) > 2:
            current.append(w)
        else:
            if len(current) >= 1:
                candidates.append(" ".join(current))
                current = []
    if len(current) >= 1:
        candidates.append(" ".join(current))

    return candidates


def _get_embeddings(
    texts: list[str], api_key: str
) -> list[list[float]]:
    if not api_key:
        logger.warning("No OpenAI API key set; returning zero vectors")
        return [np.zeros(1536).tolist() for _ in texts]

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.embeddings.create(
            model=EMBEDDING_MODEL, input=texts
        )
        return [d.embedding for d in response.data]
    except Exception as exc:
        logger.warning("Embedding generation failed: %s", exc)
        return [np.zeros(1536).tolist() for _ in texts]


def discover_new_categories(
    db_session: Session,
    api_key: str = "",
    lookback_days: int = 14,
) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    rows = (
        db_session.query(TrendSnapshot)
        .filter(TrendSnapshot.scraped_at >= cutoff)
        .all()
    )

    titles: list[str] = []
    for row in rows:
        items = (row.raw_metadata or {}).get("items", [])
        for item in items:
            title = item.get("title", "")
            if title and len(title) > 5:
                titles.append(title)

    titles = list(set(titles))

    if not titles:
        return {
            "clusters": [],
            "total_titles_analyzed": 0,
            "notes": "No titles found in recent snapshots",
        }

    phrases = []
    title_map: list[tuple[str, str]] = []
    for title in titles:
        extracted = _extract_noun_phrases(title)
        for phrase in extracted:
            phrases.append(phrase)
            title_map.append((title, phrase))

    if not phrases:
        return {
            "clusters": [],
            "total_titles_analyzed": len(titles),
            "notes": "No noun phrases extracted from titles",
        }

    phrase_counter = Counter(phrases)
    unique_phrases = list(phrase_counter.keys())

    if len(unique_phrases) < MIN_CLUSTER_SIZE:
        return {
            "clusters": [],
            "total_titles_analyzed": len(titles),
            "notes": f"Too few unique phrases ({len(unique_phrases)}) for clustering",
        }

    embeddings = _get_embeddings(unique_phrases, api_key)
    emb_array = np.array(embeddings)

    if np.all(emb_array == 0):
        return {
            "clusters": [],
            "total_titles_analyzed": len(titles),
            "notes": "Embeddings unavailable (no API key or API error)",
        }

    dist_matrix = cosine_distances(emb_array)
    clustering = DBSCAN(eps=EPS, min_samples=MIN_CLUSTER_SIZE, metric="precomputed")
    labels = clustering.fit_predict(dist_matrix)

    clusters: dict[int, list[dict[str, Any]]] = {}
    for phrase, label in zip(unique_phrases, labels):
        if label == -1:
            continue
        clusters.setdefault(int(label), []).append(
            {
                "phrase": phrase,
                "frequency": phrase_counter[phrase],
                "example_titles": [
                    t for t, p in title_map if p == phrase
                ][:3],
            }
        )

    sorted_clusters = sorted(
        clusters.values(), key=lambda c: -sum(p["frequency"] for p in c)
    )

    emerging = [
        {
            "cluster_id": i + 1,
            "total_phrases": len(cluster),
            "total_frequency": sum(p["frequency"] for p in cluster),
            "top_phrases": [p["phrase"] for p in cluster[:5]],
            "representative_titles": [
                t for p in cluster[:3] for t in p["example_titles"]
            ][:5],
        }
        for i, cluster in enumerate(sorted_clusters)
    ]

    return {
        "clusters": emerging,
        "total_titles_analyzed": len(titles),
        "total_phrases_extracted": len(phrases),
        "total_clusters_found": len(emerging),
        "embedding_model": EMBEDDING_MODEL,
    }
