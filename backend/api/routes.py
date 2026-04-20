from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.db.session import get_db
from backend.db.models import Session as SessionModel, ChatTurn, ErrorLog, Document, FeedbackFlag, User
from backend.rag.retriever import HybridRetriever
from backend.rag.reranker import CrossEncoderReranker
from backend.services.chat import ChatService
from backend.services.ingest import IngestService
from backend.services.auth import hash_password, verify_password, create_token, get_current_user
from backend.api.schemas import (
    ChatRequest, ChatResponse,
    IngestRequest, IngestResponse,
    SessionHistoryResponse, TurnOut,
    HealthResponse, ErrorLogOut,
    DocumentOut, FlagRequest, FlagResponse,
    RegisterRequest, LoginRequest, TokenResponse,
)
from backend.api.dependencies import get_retriever, get_reranker

logger = logging.getLogger(__name__)
router = APIRouter()


# Auth

@router.post("/auth/register", response_model=TokenResponse, tags=["auth"])
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where((User.username == req.username) | (User.email == req.email)))
    if existing.scalar():
        raise HTTPException(status_code=400, detail="Username or email already taken")
    user = User(username=req.username, email=req.email, hashed_password=hash_password(req.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return TokenResponse(access_token=create_token(user.id, user.username))


@router.post("/auth/login", response_model=TokenResponse, tags=["auth"])
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == req.username))
    user = result.scalar()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(access_token=create_token(user.id, user.username))


# Health

@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health():
    return HealthResponse()


# SSE streaming

@router.post("/chat/stream", tags=["chat"])
async def chat_stream(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    retriever: HybridRetriever = Depends(get_retriever),
    reranker: CrossEncoderReranker = Depends(get_reranker),
    _user: User = Depends(get_current_user),
):
    service = ChatService(retriever=retriever, reranker=reranker, db=db)
    session_id = await service.get_or_create_session(req.session_id, req.jurisdiction)

    async def event_generator() -> AsyncGenerator[str, None]:
        yield f"event: session\ndata: {json.dumps({'session_id': session_id})}\n\n"
        try:
            async for token in service.stream_response(
                session_id=session_id,
                user_message=req.message,
                jurisdiction=req.jurisdiction,
            ):
                if token.startswith("\n\n[ERROR]"):
                    msg = token.replace("\n\n[ERROR]", "").replace("\n", "\\n")
                    yield f"event: error\ndata: {json.dumps({'error': msg})}\n\n"
                elif token.startswith("\n\n[DISCLAIMER]"):
                    msg = token.replace("\n\n[DISCLAIMER]", "").replace("\n", "\\n")
                    yield f"event: disclaimer\ndata: {json.dumps({'message': msg})}\n\n"
                else:
                    safe_token = token.replace("\n", "\\n")
                    yield f"data: {safe_token}\n\n"
        except Exception as exc:
            logger.exception(f"Streaming error in session {session_id}: {exc}")
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
        finally:
            yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat_blocking(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    retriever: HybridRetriever = Depends(get_retriever),
    reranker: CrossEncoderReranker = Depends(get_reranker),
    _user: User = Depends(get_current_user),
):
    service = ChatService(retriever=retriever, reranker=reranker, db=db)
    session_id = await service.get_or_create_session(req.session_id, req.jurisdiction)
    full_text = ""
    async for token in service.stream_response(
        session_id=session_id, user_message=req.message, jurisdiction=req.jurisdiction,
    ):
        full_text += token
    return ChatResponse(session_id=session_id, message=full_text)


# Document ingest

@router.post("/ingest", response_model=IngestResponse, tags=["documents"])
async def ingest_document(
    req: IngestRequest,
    db: AsyncSession = Depends(get_db),
    retriever: HybridRetriever = Depends(get_retriever),
    _user: User = Depends(get_current_user),
):
    service = IngestService(retriever=retriever, db=db)
    try:
        doc_id = await service.ingest(
            text=req.text, title=req.title, jurisdiction=req.jurisdiction,
            task_category=req.task_category, source_url=req.source_url,
        )
    except Exception as exc:
        logger.exception(f"Ingest failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Ingest failed: {exc}")
    doc = await db.get(Document, doc_id)
    return IngestResponse(doc_id=doc_id, title=req.title, chunk_count=doc.chunk_count if doc else 0)


# Session history

@router.get("/sessions/{session_id}/history", response_model=SessionHistoryResponse, tags=["sessions"])
async def session_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    session = await db.get(SessionModel, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    result = await db.execute(
        select(ChatTurn).where(ChatTurn.session_id == session_id).order_by(ChatTurn.turn_index)
    )
    turns = result.scalars().all()
    return SessionHistoryResponse(
        session_id=session_id, jurisdiction=session.jurisdiction,
        turns=[TurnOut(
            turn_index=t.turn_index, user_message=t.user_message,
            assistant_message=t.assistant_message, citations=t.citations or [],
            confidence=t.confidence, refused=t.refused, created_at=t.created_at,
        ) for t in turns],
    )


# Error log

@router.get("/admin/errors", response_model=list[ErrorLogOut], tags=["admin"])
async def list_errors(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(select(ErrorLog).order_by(ErrorLog.created_at.desc()).limit(limit))
    errors = result.scalars().all()
    return [ErrorLogOut(
        id=e.id, session_id=e.session_id, error_type=e.error_type,
        query=e.query, detail=e.detail, created_at=e.created_at,
    ) for e in errors]


# Documents

@router.get("/documents", response_model=list[DocumentOut], tags=["documents"])
async def list_documents(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(select(Document).order_by(Document.ingested_at.desc()))
    docs = result.scalars().all()
    return [DocumentOut(
        id=d.id, title=d.title, jurisdiction=d.jurisdiction,
        task_category=d.task_category, ingested_at=d.ingested_at,
    ) for d in docs]


# Feedback flag

@router.post("/chat/flag", response_model=FlagResponse, tags=["chat"])
async def flag_answer(
    req: FlagRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    db.add(FeedbackFlag(session_id=req.session_id, turn_id=req.turn_id, category=req.category))
    await db.commit()
    return FlagResponse()
