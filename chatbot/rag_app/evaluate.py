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


def evaluate(settings: Settings, mode: str = "lexical", *, expanded: bool = False):
    filename = "expanded_questions.json" if expanded else "questions.json"
    dataset = json.loads((ROOT / "evals" / filename).read_text(encoding="utf-8"))
    store = Store.from_settings(settings)
    retriever = Retriever(store, chroma_path=store.path)
    if not retriever.chunks:
        raise ValueError("Cần ingest trước khi đánh giá")
    section_field = "gold_section" if expanded else "section_contains"
    knowledge = [c for c in dataset["cases"] if c.get(section_field)
                 and (not expanded or c.get("gold_source") and not c.get("history_questions"))]
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
        ranks = [i for i, h in enumerate(hits, 1) if case[section_field] in h.chunk.section
                 and (not expanded or case["gold_source"] == h.chunk.source_id)]
        rank = min(ranks) if ranks else None
        results.append(
            {
                "id": case["id"],
                "question": case["question"],
                "expected_section": case[section_field],
                "expected_source": case.get("gold_source"),
                "first_relevant_rank": rank,
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "retrieved_sections": [h.chunk.section for h in hits],
            }
        )
    n = len(results)
    routing = [
        {"id": c["id"], "expected": c["intent"], "actual": classify(c["question"])}
        for c in dataset["cases"] if not c.get("history_questions")
    ]
    return {
        "mode": mode,
        "dataset": filename,
        "annotation_note": dataset["annotation_note"],
        "chunk_count": len(retriever.chunks),
        "index_revision": retriever.metadata.get("revision"),
        "knowledge_cases": n,
        "hit_at_1": sum(r["first_relevant_rank"] == 1 for r in results) / n,
        "hit_at_3": sum(
            r["first_relevant_rank"] is not None and r["first_relevant_rank"] <= 3 for r in results
        )
        / n,
        "context_hit_rate": sum(r["first_relevant_rank"] is not None for r in results) / n,
        "hit_at_5": sum(0 < (r["first_relevant_rank"] or 0) <= 5 for r in results) / n,
        "mrr_at_5": sum(
            1 / r["first_relevant_rank"] if 0 < (r["first_relevant_rank"] or 0) <= 5 else 0 for r in results
        )
        / n,
        "standalone_router_cases": len(routing),
        "router_accuracy": sum(r["actual"] == r["expected"] for r in routing) / len(routing),
        "llm_answer_quality_evaluated": False,
        "unanswerable_generation_evaluated": False,
        "results": results,
        "routing": routing,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["lexical", "dense", "hybrid"], default="lexical")
    parser.add_argument("--expanded", action="store_true", help="Score standalone queries with a gold source and section")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(Settings(), args.mode, expanded=args.expanded)
    if args.output is None:
        args.output = ROOT / "docs" / (f"evaluation_section_expanded_{args.mode}.json" if args.expanded
                                       else "evaluation_lexical.json")
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
