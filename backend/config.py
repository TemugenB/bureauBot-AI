
"""Application settings loaded from environment variables with sensible defaults."""
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    gemini_api_key: str = ""
    llm_model: str = "gemini-2.5-flash-lite"
    llm_max_tokens: int = 1024
    llm_temperature: float = 0.2       

    embedding_model: str = "all-MiniLM-L6-v2"  
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    chroma_persist_dir: str = "./backend/chroma_db"
    chroma_collection: str = "admin_docs"

    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/db"

    chunk_size: int = 512
    chunk_overlap: int = 64
    retrieval_top_k: int = 20             
    rerank_top_k: int = 5             
    multi_query_count: int = 3          
    confidence_threshold: float = -0.25   
    soft_threshold: float = -2.0
    rrf_k: int = 60

    jwt_secret: str = "change-me-in-production"
    jwt_expiry_hours: int = 24

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: List[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file="backend/.env", env_file_encoding="utf-8")   




@lru_cache
def get_settings() -> Settings:
    return Settings()
