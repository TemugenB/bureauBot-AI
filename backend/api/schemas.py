"""
api/schemas.py — Pydantic v2 request/response models.
"""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


#Chat

class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(
        None, description="Existing session UUID. Omit to start a new session."
    )
    message: str = Field(..., min_length=1, max_length=2000)
    jurisdiction: str = Field("HU", description="ISO country code for locale-aware retrieval.")


class ChatResponse(BaseModel):
    session_id: str
    message: str


#Ingest

class IngestRequest(BaseModel):
    text: str = Field(..., min_length=50)
    title: str = Field(..., max_length=256)
    jurisdiction: str = "HU"
    task_category: Optional[str] = None
    source_url: Optional[str] = None


class IngestResponse(BaseModel):
    doc_id: str
    title: str
    chunk_count: int
    message: str = "Document ingested successfully."


#Session history

class TurnOut(BaseModel):
    turn_index: int
    user_message: str
    assistant_message: Optional[str]
    citations: list[dict]
    confidence: Optional[float]
    refused: bool
    created_at: datetime


class SessionHistoryResponse(BaseModel):
    session_id: str
    jurisdiction: str
    turns: list[TurnOut]


#Health

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"


#Error log

class ErrorLogOut(BaseModel):
    id: int
    session_id: Optional[str]
    error_type: str
    query: Optional[str]
    detail: Optional[str]
    created_at: datetime


#Documents

class DocumentOut(BaseModel):
    id: str
    title: str
    jurisdiction: str
    task_category: Optional[str]
    ingested_at: datetime


#Feedback flag

class FlagRequest(BaseModel):
    session_id: str
    turn_id: int
    category: str = Field(..., pattern="^(wrong_info|outdated|incomplete|other)$")


class FlagResponse(BaseModel):
    message: str = "Flag recorded. Thank you for your feedback."


#Auth

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: str = Field(..., min_length=5, max_length=256)
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
