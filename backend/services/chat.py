from __future__ import annotations

import uuid
import logging
from typing import AsyncGenerator

from google import genai
from google.genai import types
from google.genai import errors as genai_errors
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.config import get_settings
from backend.db.models import Session, ChatTurn, ErrorLog
from backend.rag.retriever import HybridRetriever
from backend.rag.reranker import CrossEncoderReranker
from backend.rag.fusion import reciprocal_rank_fusion, hybrid_score, RetrievedChunk
from backend.rag.multi_query import MultiQueryTranslator
from backend.hallucination.gate import ConfidenceGate
from backend.hallucination.verifier import CitationVerifier

logger = logging.getLogger(__name__)
settings = get_settings()


class ChatService:

    def __init__(
        self,
        retriever: HybridRetriever,
        reranker: CrossEncoderReranker,
        db: AsyncSession,
    ):
        self.retriever = retriever
        self.reranker = reranker
        self.db = db
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._gate = ConfidenceGate()
        self._verifier = CitationVerifier()
        self._translator = MultiQueryTranslator(llm_fn=self._plain_llm_call)

    #Public SSE generator

    async def stream_response(
        self,
        session_id: str,
        user_message: str,
        jurisdiction: str = "HU",
    ) -> AsyncGenerator[str, None]:
        """
        Async generator yielding text tokens for SSE delivery.
        Persists the full turn to PostgreSQL after streaming completes.
        """
        turn_index = await self._next_turn_index(session_id)

        # Multi-query translation 
        query_variants = await self._translator.translate(user_message)
        logger.info(f"[{session_id}] {len(query_variants)} query variants generated")

        # Retrieve for each variant 
        all_dense: list[list[RetrievedChunk]] = []
        all_bm25: list[list[RetrievedChunk]] = []

        for variant in query_variants:
            dense, bm25 = self.retriever.retrieve(variant, jurisdiction=jurisdiction)
            all_dense.append(dense)
            all_bm25.append(bm25)

        # RAG Fusion 
        fused_dense = reciprocal_rank_fusion(all_dense)
        bm25_dedup: dict[str, RetrievedChunk] = {}
        for b_list in all_bm25:
            for c in b_list:
                if c.id not in bm25_dedup or c.bm25_score > bm25_dedup[c.id].bm25_score:
                    bm25_dedup[c.id] = c

        fused = hybrid_score(fused_dense, list(bm25_dedup.values()))
        candidates = fused[: settings.retrieval_top_k]

        # Cross-Encoder Reranking 
        top_chunks = self.reranker.rerank(user_message, candidates)
        top_score = self.reranker.top_confidence(top_chunks)

        # Confidence Gate
        gate_result = self._gate.evaluate(
            top_score, n_chunks=len(top_chunks),
            top_chunk=top_chunks[0] if top_chunks else None,
        )

        if not gate_result.passed:
            refusal = self._gate.refusal_message(gate_result)
            await self._log_error(session_id, "confidence_gate", user_message, gate_result.reason)
            await self._persist_turn(
                session_id=session_id,
                turn_index=turn_index,
                user_message=user_message,
                assistant_message=refusal,
                citations=[],
                confidence=gate_result.confidence,
                refused=True,
                refusal_reason=gate_result.reason,
            )
            yield refusal
            return

        # Build closed-context system prompt
        system_prompt = self._verifier.build_system_prompt(top_chunks)

        # Load session history (last 3 turns) 
        history = await self._load_history(session_id, limit=3)

        # Stream
        full_response = ""
        stream_error = False
        try:
            contents = history + [
                types.Content(
                    role="user",
                    parts=[types.Part(text=user_message)],
                )
            ]
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
            )
            stream = await self._client.aio.models.generate_content_stream(
                model=settings.llm_model,
                contents=contents,
                config=config,
            )
            async for chunk in stream:
                if chunk.text:
                    full_response += chunk.text
                    yield chunk.text

        except genai_errors.ClientError as exc:
            error_msg = f"Gemini API client error: {exc}"
            logger.error(f"[{session_id}] {error_msg}")
            await self._log_error(session_id, "gemini_client_error", user_message, error_msg)
            partial = " (partial response above may be incomplete)" if full_response else ""
            yield f"\n\n[ERROR]⚠ The AI service returned an error{partial}. Please try again."
            stream_error = True

        except genai_errors.ServerError as exc:
            error_msg = f"Gemini API server error: {exc}"
            logger.error(f"[{session_id}] {error_msg}")
            await self._log_error(session_id, "gemini_server_error", user_message, error_msg)
            partial = " (partial response above may be incomplete)" if full_response else ""
            yield f"\n\n[ERROR]⚠ The AI service is temporarily unavailable{partial}. Please try again in a moment."
            stream_error = True

        except Exception as exc:
            logger.exception(f"[{session_id}] Unexpected streaming error: {exc}")
            await self._log_error(session_id, "streaming_error", user_message, str(exc))
            partial = " (partial response above may be incomplete)" if full_response else ""
            yield f"\n\n[ERROR]⚠ An unexpected error occurred{partial}. Please try again."
            stream_error = True

        if stream_error:
            if full_response:
                await self._persist_turn(
                    session_id=session_id, turn_index=turn_index,
                    user_message=user_message, assistant_message=full_response,
                    citations=[], confidence=gate_result.confidence, refused=False,
                )
            return

        # Citation verification
        verification = self._verifier.verify(full_response, top_chunks)

        if not verification.verified:
            logger.warning(
                f"[{session_id}] Verifier found {len(verification.ungrounded_sentences)} "
                "ungrounded sentence(s). Appending disclaimer."
            )
            disclaimer = (
                "\n\n[DISCLAIMER]⚠ Some parts of this response could not be fully verified "
                "against official sources. Please double-check with the relevant authority."
            )
            yield disclaimer
            full_response += disclaimer
            await self._log_error(
                session_id, "verifier_fail", user_message,
                str(verification.ungrounded_sentences),
            )

        # Persistence
        await self._persist_turn(
            session_id=session_id,
            turn_index=turn_index,
            user_message=user_message,
            assistant_message=verification.clean_response,
            citations=[
                {"chunk_id": c.chunk_id, "doc_id": c.doc_id, "score": c.score}
                for c in verification.citations
            ],
            confidence=gate_result.confidence,
            refused=False,
        )

    # Helpers

    async def get_or_create_session(
        self, session_id: str | None, jurisdiction: str = "HU"
    ) -> str:
        if session_id is None:
            session_id = str(uuid.uuid4())
        existing = await self.db.get(Session, session_id)
        if not existing:
            self.db.add(Session(id=session_id, jurisdiction=jurisdiction))
            await self.db.commit()
        return session_id

    async def _next_turn_index(self, session_id: str) -> int:
        result = await self.db.execute(
            select(func.count()).where(ChatTurn.session_id == session_id)
        )
        return result.scalar() or 0

    async def _load_history(
        self, session_id: str, limit: int = 3
    ) -> list[types.Content]:
        result = await self.db.execute(
            select(ChatTurn)
            .where(ChatTurn.session_id == session_id, ChatTurn.refused == False)
            .order_by(ChatTurn.turn_index.desc())
            .limit(limit)
        )
        turns = list(reversed(result.scalars().all()))
        contents: list[types.Content] = []
        for t in turns:
            contents.append(types.Content(
                role="user",
                parts=[types.Part(text=t.user_message)],
            ))
            if t.assistant_message:
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text=t.assistant_message)],
                ))
        return contents

    async def _persist_turn(self, **kwargs) -> None:
        self.db.add(ChatTurn(**kwargs))
        await self.db.commit()

    async def _log_error(
        self, session_id: str, error_type: str, query: str, detail: str | None
    ) -> None:
        self.db.add(ErrorLog(
            session_id=session_id,
            error_type=error_type,
            query=query,
            detail=detail,
        ))
        await self.db.commit()

    async def _plain_llm_call(self, prompt: str) -> str:
        """
        Cheap, non-streaming call for internal tasks like query expansion.
        Uses a lower token limit to keep costs minimal.
        """
        try:
            response = await self._client.aio.models.generate_content(
                model=settings.llm_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=256,
                    temperature=0.5,
                ),
            )
            return response.text or ""

        except genai_errors.ClientError as exc:
            logger.warning(f"Plain LLM call failed — client error: {exc}")
            raise

        except genai_errors.ServerError as exc:
            logger.warning(f"Plain LLM call failed — server error: {exc}")
            raise

        except Exception as exc:
            logger.warning(f"Plain LLM call failed: {exc}")
            raise