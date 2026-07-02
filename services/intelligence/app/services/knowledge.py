from __future__ import annotations

import re
from collections import Counter

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeChunk, KnowledgeDocument
from app.schemas.knowledge import KnowledgeChunkSearchResult, KnowledgeDocumentCreate

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9-]{1,}", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def chunk_text(content: str, max_words: int = 160) -> list[str]:
    words = content.split()
    if not words:
        return []
    chunks: list[str] = []
    for start in range(0, len(words), max_words):
        chunks.append(" ".join(words[start : start + max_words]))
    return chunks


async def create_knowledge_document(db: AsyncSession, payload: KnowledgeDocumentCreate) -> KnowledgeDocument:
    document = KnowledgeDocument(
        source=payload.source,
        title=payload.title,
        document_type=payload.document_type,
        source_ref=payload.source_ref,
        content=payload.content,
        document_metadata=payload.metadata,
    )
    db.add(document)
    await db.flush()
    for index, chunk in enumerate(chunk_text(payload.content)):
        db.add(
            KnowledgeChunk(
                document_id=document.id,
                chunk_index=index,
                text=chunk,
                token_set=sorted(set(tokenize(chunk))),
            )
        )
    await db.commit()
    await db.refresh(document)
    return document


async def replace_document_chunks(db: AsyncSession, document: KnowledgeDocument) -> None:
    await db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
    for index, chunk in enumerate(chunk_text(document.content)):
        db.add(
            KnowledgeChunk(
                document_id=document.id,
                chunk_index=index,
                text=chunk,
                token_set=sorted(set(tokenize(chunk))),
            )
        )
    await db.commit()


async def search_knowledge(db: AsyncSession, query: str, limit: int = 5) -> list[KnowledgeChunkSearchResult]:
    query_tokens = Counter(tokenize(query))
    if not query_tokens:
        return []
    chunks = (await db.execute(select(KnowledgeChunk))).scalars().all()
    docs = {doc.id: doc for doc in (await db.execute(select(KnowledgeDocument))).scalars().all()}
    scored: list[tuple[int, KnowledgeChunk]] = []
    for chunk in chunks:
        chunk_tokens = set(chunk.token_set or [])
        score = sum(weight for token, weight in query_tokens.items() if token in chunk_tokens)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: (item[0], len(item[1].text)), reverse=True)
    results: list[KnowledgeChunkSearchResult] = []
    for score, chunk in scored[:limit]:
        doc = docs.get(chunk.document_id)
        if doc is None:
            continue
        results.append(
            KnowledgeChunkSearchResult(
                document_id=doc.id,
                title=doc.title,
                document_type=doc.document_type,
                source=doc.source,
                source_ref=doc.source_ref,
                chunk_id=chunk.id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                score=score,
            )
        )
    return results
