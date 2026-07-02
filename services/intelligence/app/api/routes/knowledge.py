from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.knowledge import (
    AskDfpRequest,
    AskDfpResponse,
    DecisionOutcomeCreate,
    DecisionOutcomeListResponse,
    DecisionOutcomeResponse,
    KnowledgeDocumentCreate,
    KnowledgeDocumentResponse,
    KnowledgeSearchResponse,
)
from app.security import verify_internal_token
from app.services.ask_dfp import answer_question
from app.services.decision_log import list_decision_outcomes, record_decision_outcome
from app.services.knowledge import create_knowledge_document, search_knowledge

router = APIRouter(tags=["knowledge"], dependencies=[Depends(verify_internal_token)])


@router.post("/knowledge/documents", response_model=KnowledgeDocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(payload: KnowledgeDocumentCreate, db: AsyncSession = Depends(get_db)):
    return await create_knowledge_document(db, payload)


@router.get("/knowledge/search", response_model=KnowledgeSearchResponse)
async def search_documents(
    q: str = Query(min_length=1),
    limit: int = Query(default=5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    return KnowledgeSearchResponse(items=await search_knowledge(db, q, limit=limit))


@router.post("/ask", response_model=AskDfpResponse)
async def ask_dfp(payload: AskDfpRequest, db: AsyncSession = Depends(get_db)):
    return await answer_question(db, payload)


@router.post("/decision-outcomes", response_model=DecisionOutcomeResponse, status_code=status.HTTP_201_CREATED)
async def create_decision_outcome(payload: DecisionOutcomeCreate, db: AsyncSession = Depends(get_db)):
    return await record_decision_outcome(db, payload)


@router.get("/decision-outcomes", response_model=DecisionOutcomeListResponse)
async def list_outcomes(limit: int = Query(default=50, ge=1, le=250), db: AsyncSession = Depends(get_db)):
    return DecisionOutcomeListResponse(items=await list_decision_outcomes(db, limit=limit))
