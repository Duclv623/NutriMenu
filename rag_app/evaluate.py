"""Transparent retrieval/router baseline; NOT a medical correctness evaluator."""

import argparse
import json
import time
from pathlib import Path

from rag_app.config import ROOT, Settings
from rag_app.provider import create_provider
from rag_app.retrieval import Retriever
from rag_app.safety import classify
from rag_app.store import Store


def evaluate(settings: Settings, mode: str = "lexical"):
    dataset = json.loads((ROOT / "evals" / "questions.json").read_text(encoding="utf-8"))
    retriever = Retriever(Store(settings.storage_dir / "rag.sqlite3"))
    if not retriever.chunks:
        raise ValueError("Cần ingest trước khi đánh giá")
    knowledge = [c for c in dataset["cases"] if c.get("section_contains")]
    vectors = [None] * len(knowledge)
    if mode != "lexical":
        if (
            retriever.metadata.get("mode") != "hybrid"
            or retriever.metadata.get("embedding_identity", retriever.metadata.get("embedding_model")) != settings.embedding_identity
        ):
            raise ValueError("Đánh giá dense/hybrid cần index hybrid cùng embedding model")
        provider = create_provider(settings)
        try:
            vectors = provider.embed([c["question"] for c in knowledge])
        finally:
            provider.close()
    results = []
    for case, vector in zip(knowledge, vectors, strict=True):
        started = time.perf_counter()
        hits = retriever.search(
            case["question"],
            top_k=5,
            query_vector=vector,
            min_dense=settings.min_dense_score,
            mode=mode,
        )
        ranks = [i for i, h in enumerate(hits, 1) if case["section_contains"] in h.chunk.section]
        rank = min(ranks) if ranks else None
        results.append(
            {
                "id": case["id"],
                "question": case["question"],
                "expected_section": case["section_contains"],
                "first_relevant_rank": rank,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "retrieved_sections": [h.chunk.section for h in hits],
            }
        )
    n = len(results)
    routing = [
        {"id": c["id"], "expected": c["intent"], "actual": classify(c["question"])}
        for c in dataset["cases"]
    ]
    return {
        "mode": mode,
        "annotation_note": dataset["annotation_note"],
        "chunk_count": len(retriever.chunks),
        "index_revision": retriever.metadata.get("revision"),
        "knowledge_cases": n,
        "hit_at_1": sum(r["first_relevant_rank"] == 1 for r in results) / n,
        "hit_at_3": sum(
            r["first_relevant_rank"] is not None and r["first_relevant_rank"] <= 3 for r in results
        )
        / n,
        "hit_at_5": sum(r["first_relevant_rank"] is not None for r in results) / n,
        "mrr_at_5": sum(
            1 / r["first_relevant_rank"] if r["first_relevant_rank"] else 0 for r in results
        )
        / n,
        "router_accuracy": sum(r["actual"] == r["expected"] for r in routing) / len(routing),
        "llm_answer_quality_evaluated": False,
        "unanswerable_generation_evaluated": False,
        "results": results,
        "routing": routing,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["lexical", "dense", "hybrid"], default="lexical")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "evaluation_lexical.json")
    args = parser.parse_args()
    result = evaluate(Settings(), args.mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"results", "routing"}},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
