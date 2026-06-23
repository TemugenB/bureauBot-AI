from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.rag.chunker import structured_chunk
from backend.rag.fusion import RetrievedChunk, reciprocal_rank_fusion, hybrid_score
from backend.config import get_settings

logging.basicConfig(level=logging.WARNING)
logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)
settings = get_settings()


def _load_corpus(corpus_dir: Path):
    """Load and chunk all .txt files, return (chunks, doc_map)."""
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from backend.rag.retriever import HybridRetriever

    # Use a temp dir for ChromaDB; we clean up manually to avoid Windows lock issues
    tmp = tempfile.mkdtemp()
    original_persist = settings.chroma_persist_dir
    settings.chroma_persist_dir = tmp

    # Suppress ChromaDB telemetry noise
    chromadb_settings = ChromaSettings(
        chroma_db_impl="duckdb+parquet",
        anonymized_telemetry=False,
    )

    retriever = HybridRetriever()

    doc_map: dict[str, str] = {}  # doc_id -> filename
    for txt_file in sorted(corpus_dir.glob("*.txt")):
        text = txt_file.read_text(encoding="utf-8")
        if not text.strip():
            continue
        doc_id = txt_file.stem
        doc_map[doc_id] = txt_file.name
        chunks = structured_chunk(text, doc_id=doc_id)
        children = [c for c in chunks if c.parent_id is not None]
        to_embed = children or [c for c in chunks if c.parent_id is None]
        retriever.add_chunks([
            RetrievedChunk(
                id=c.id, content=c.content, doc_id=doc_id,
                parent_content=c.parent_content, section_title=c.section_title,
                metadata={"jurisdiction": "HU", "task_category": "",
                          "parent_id": c.parent_id or "",
                          "section_title": c.section_title,
                          "chunk_type": c.chunk_type},
            ) for c in to_embed
        ])

    settings.chroma_persist_dir = original_persist
    return retriever, doc_map, tmp


def _evaluate_retrieval(retriever, doc_map, in_scope, reranker):
    """Check if expected doc appears in top-k retrieved chunks."""
    from backend.hallucination.gate import ConfidenceGate
    gate = ConfidenceGate()

    results = []
    for item in in_scope:
        question = item["question"]
        expected_file = item["expected_doc"]
        expected_doc_id = Path(expected_file).stem

        dense, bm25 = retriever.retrieve(question, jurisdiction="HU")
        fused_dense = reciprocal_rank_fusion([dense])
        fused = hybrid_score(fused_dense, bm25)
        candidates = fused[:settings.retrieval_top_k]
        top_chunks = reranker.rerank(question, candidates)

        top3_docs = [c.doc_id for c in top_chunks[:3]]
        top5_docs = [c.doc_id for c in top_chunks[:5]]

        hit_at_3 = expected_doc_id in top3_docs
        hit_at_5 = expected_doc_id in top5_docs

        top_score = reranker.top_confidence(top_chunks)
        gate_result = gate.evaluate(top_score, n_chunks=len(top_chunks),
                                    top_chunk=top_chunks[0] if top_chunks else None)

        results.append({
            "question": question,
            "expected": expected_file,
            "hit@3": hit_at_3,
            "hit@5": hit_at_5,
            "top_score": round(top_score, 4),
            "gate_passed": gate_result.passed,
        })
    return results


def _evaluate_gate(retriever, out_of_scope, reranker):
    """Check if out-of-scope questions are correctly refused."""
    from backend.hallucination.gate import ConfidenceGate
    gate = ConfidenceGate()

    results = []
    for item in out_of_scope:
        question = item["question"]
        dense, bm25 = retriever.retrieve(question, jurisdiction="HU")
        fused_dense = reciprocal_rank_fusion([dense])
        fused = hybrid_score(fused_dense, bm25)
        candidates = fused[:settings.retrieval_top_k]
        top_chunks = reranker.rerank(question, candidates)

        top_score = reranker.top_confidence(top_chunks)
        gate_result = gate.evaluate(top_score, n_chunks=len(top_chunks),
                                    top_chunk=top_chunks[0] if top_chunks else None)

        results.append({
            "question": question,
            "top_score": round(top_score, 4),
            "correctly_refused": not gate_result.passed,
        })
    return results


def main():
    parser = argparse.ArgumentParser(description="RAG evaluation runner")
    parser.add_argument("--corpus", default="./corpus", help="Path to corpus directory")
    parser.add_argument("--dataset", default="tests/e2e/eval_dataset.json", help="Path to eval dataset")
    args = parser.parse_args()

    corpus_dir = Path(args.corpus)
    dataset_path = Path(args.dataset)

    if not corpus_dir.is_dir():
        print(f"ERROR: Corpus directory not found: {corpus_dir}")
        sys.exit(1)
    if not dataset_path.exists():
        print(f"ERROR: Dataset not found: {dataset_path}")
        sys.exit(1)

    dataset = json.loads(dataset_path.read_text())

    print("Loading corpus and building index...")
    retriever, doc_map, tmp_dir = _load_corpus(corpus_dir)

    from backend.rag.reranker import CrossEncoderReranker
    reranker = CrossEncoderReranker()

    print(f"Indexed {len(doc_map)} documents: {list(doc_map.values())}\n")

    # --- In-scope evaluation ---
    print("=" * 70)
    print("IN-SCOPE RETRIEVAL EVALUATION")
    print("=" * 70)
    retrieval_results = _evaluate_retrieval(retriever, doc_map, dataset["in_scope"], reranker)

    hits_3 = sum(1 for r in retrieval_results if r["hit@3"])
    hits_5 = sum(1 for r in retrieval_results if r["hit@5"])
    gates_passed = sum(1 for r in retrieval_results if r["gate_passed"])
    total = len(retrieval_results)

    print(f"\n{'Question':<75} {'Hit@3':>5} {'Hit@5':>5} {'Score':>7} {'Gate':>5}")
    print("-" * 100)
    for r in retrieval_results:
        q = r["question"][:72] + "..." if len(r["question"]) > 72 else r["question"]
        print(f"{q:<75} {'✓' if r['hit@3'] else '✗':>5} {'✓' if r['hit@5'] else '✗':>5} "
              f"{r['top_score']:>7.4f} {'✓' if r['gate_passed'] else '✗':>5}")

    print(f"\nPrecision@3: {hits_3}/{total} = {hits_3/total:.1%}")
    print(f"Precision@5: {hits_5}/{total} = {hits_5/total:.1%}")
    print(f"Gate pass rate (in-scope): {gates_passed}/{total} = {gates_passed/total:.1%}")

    # --- Out-of-scope evaluation ---
    print(f"\n{'=' * 70}")
    print("OUT-OF-SCOPE GATE EVALUATION")
    print("=" * 70)
    gate_results = _evaluate_gate(retriever, dataset["out_of_scope"], reranker)

    correct_refusals = sum(1 for r in gate_results if r["correctly_refused"])
    total_oos = len(gate_results)

    print(f"\n{'Question':<75} {'Score':>7} {'Refused':>8}")
    print("-" * 92)
    for r in gate_results:
        q = r["question"][:72] + "..." if len(r["question"]) > 72 else r["question"]
        print(f"{q:<75} {r['top_score']:>7.4f} {'✓' if r['correctly_refused'] else '✗':>8}")

    print(f"\nGate accuracy (out-of-scope): {correct_refusals}/{total_oos} = {correct_refusals/total_oos:.1%}")

    # --- Summary ---
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)
    print(f"  Retrieval Precision@3:       {hits_3/total:.1%}")
    print(f"  Retrieval Precision@5:       {hits_5/total:.1%}")
    print(f"  In-scope gate pass rate:     {gates_passed/total:.1%}")
    print(f"  Out-of-scope refusal rate:   {correct_refusals/total_oos:.1%}")
    print(f"  Total questions evaluated:   {total + total_oos}")

    # Clean up temp ChromaDB dir (best-effort on Windows)
    import shutil
    try:
        del retriever
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
