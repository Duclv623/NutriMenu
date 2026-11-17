"""Run the everyday question set against the configured chatbot without loopback HTTP."""
import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

from rag_app.config import ROOT, Settings
from rag_app.domain import ChatRequest
from rag_app.gemini_provider import GeminiProvider
from rag_app.meal_gateway import create_meal_gateway
from rag_app.service import ChatService
from rag_app.store import Store


def save(path: Path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="tmp/everyday-live-2026-11-17")
    parser.add_argument("--ids", default="")
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError("Output must stay within project root")
    output.mkdir(parents=True, exist_ok=True)
    dataset_path = ROOT / "evals/everyday_questions_2026-11-17.json"
    rows = json.loads(dataset_path.read_text(encoding="utf-8-sig"))
    if len(rows) != 32 or len({row["id"] for row in rows}) != 32:
        raise ValueError("Expected 32 unique everyday questions")
    selected = set(args.ids.split(",")) if args.ids else None
    cfg = Settings()
    if cfg.answer_mode != "gemini" or not cfg.has_key:
        raise ValueError("A configured Gemini key is required")
    if not cfg.storage_dir.joinpath("rag.sqlite3").is_file():
        raise ValueError("Approved local retrieval index is required")
    chunks, vectors, metadata = Store(cfg.storage_dir / "rag.sqlite3").load_index()
    if not chunks:
        raise ValueError("Approved local retrieval index is empty")
    runtime = output / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    store = Store(runtime / "rag.sqlite3")
    store.replace_index(chunks, metadata, vectors)

    result_path = output / "responses.json"
    calls_path = output / "gemini_calls.json"
    run_path = output / "run.json"
    results = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else []
    ledger = json.loads(calls_path.read_text(encoding="utf-8")) if calls_path.exists() else []
    data_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    index_hash = hashlib.sha256(json.dumps(
        {"chunks": [(chunk.id, chunk.text) for chunk in chunks], "metadata": metadata},
        ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    code_hash = hashlib.sha256(b"".join(
        path.read_bytes() for path in sorted((ROOT / "rag_app").glob("*.py")))).hexdigest()
    if run_path.exists():
        run = json.loads(run_path.read_text(encoding="utf-8"))
        if (run.get("dataset_sha256") != data_hash or run.get("model") != cfg.active_model
                or run.get("code_sha256") != code_hash or run.get("index_sha256") != index_hash):
            raise ValueError("Output folder belongs to another dataset/model")
    else:
        run = {"run_id": str(uuid4()), "started_at": datetime.now(UTC).isoformat(),
               "model": cfg.active_model, "dataset_sha256": data_hash,
               "index_sha256": index_hash, "code_sha256": code_hash,
               "transport": "direct_chat_service",
               "meal_service_mode": cfg.meal_service_mode,
               "note": "Actual ChatService responses preserved; static fallback is identified by answer_origin."}

    proxies = urllib.request.getproxies()
    https_proxy = proxies.get("https")
    proxy_transport = httpx.HTTPTransport(proxy=https_proxy) if https_proxy else None
    run["http_proxy_transport"] = ("configured HTTPS proxy via httpx.HTTPTransport"
                                   if https_proxy else "default configured httpx transport")
    provider = GeminiProvider(cfg, transport=proxy_transport)
    original_post = provider.client.post

    def recorded_post(model, method, body):
        entry = {"at": datetime.now(UTC).isoformat(), "model": model, "method": method}
        try:
            value = original_post(model, method, body)
            entry.update(success=True, response_id=value.get("responseId"),
                         usage=value.get("usageMetadata", {}))
            return value
        except Exception as error:
            causes, cause = [], error.__cause__
            while cause is not None and len(causes) < 5:
                causes.append(type(cause).__name__)
                cause = cause.__cause__
            entry.update(success=False, error_class=type(error).__name__,
                         error=str(error), cause_classes=causes)
            raise
        finally:
            ledger.append(entry)
            save(calls_path, ledger)

    provider.client.post = recorded_post
    gateway = create_meal_gateway(cfg)
    service = ChatService(cfg.model_copy(update={"storage_dir": runtime, "vector_backend": "sqlite",
        "rate_limit_per_minute": 300}), store, provider, gateway)
    try:
        done = {row["id"] for row in results}
        for case in rows:
            if (selected and case["id"] not in selected) or case["id"] in done:
                continue
            owner = "everyday-eval:" + case["id"] + ":" + str(uuid4())
            request = ChatRequest(message=case["question"], save_history=False)
            first_call = len(ledger)
            started = datetime.now(UTC)
            try:
                response = service.chat(request, owner)
                body = response.model_dump(mode="json")
                record = {**case, "transport": "direct_chat_service", "response": body,
                          "answer": body.get("answer"), "answer_origin": body.get("answer_origin"),
                          "provider_model": cfg.active_model if body.get("provider_response_ids") else None,
                          "provider_response_ids": body.get("provider_response_ids", []),
                          "gemini_calls": ledger[first_call:], "error": None}
            except Exception as error:
                causes, cause = [], error.__cause__
                while cause is not None and len(causes) < 5:
                    causes.append(type(cause).__name__)
                    cause = cause.__cause__
                record = {**case, "transport": "direct_chat_service", "response": None,
                          "answer": None, "answer_origin": "unavailable",
                          "provider_model": cfg.active_model,
                          "provider_response_ids": [], "gemini_calls": ledger[first_call:],
                          "error": {"class": type(error).__name__, "message": str(error),
                                    "cause_classes": causes}}
            record["elapsed_seconds"] = round((datetime.now(UTC) - started).total_seconds(), 2)
            results.append(record)
            save(result_path, results)
            save(run_path, {**run, "completed_cases": len(results),
                            "updated_at": datetime.now(UTC).isoformat()})
            print(json.dumps({"id": case["id"], "origin": record["answer_origin"],
                              "calls": len(record["gemini_calls"]), "error": record.get("error"),
                              "answer": record["answer"]}, ensure_ascii=False), flush=True)
    finally:
        service.meals.close()
        provider.close()
    save(run_path, {**run, "completed_cases": len(results), "finished_at": datetime.now(UTC).isoformat()})
    print(f"FINISHED {len(results)} cases; {len(ledger)} Gemini calls", flush=True)


if __name__ == "__main__":
    main()
