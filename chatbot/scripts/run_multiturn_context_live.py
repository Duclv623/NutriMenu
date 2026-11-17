"""Run multi-turn context conversations against the configured chatbot."""
import argparse
import copy
import hashlib
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx

from rag_app.config import ROOT, Settings
from rag_app.domain import ChatRequest
from rag_app.gemini_provider import GeminiProvider
from rag_app.meal_gateway import MockMealGateway, create_meal_gateway
from rag_app.meal_models import ApplySwap
from rag_app.provider import ProviderFailure
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
    parser.add_argument("--dataset", default="evals/everyday_conversations_2026-11-17.json")
    parser.add_argument("--output", default="tmp/multiturn-context-live-2026-11-17")
    parser.add_argument("--ids", default="")
    args = parser.parse_args()
    dataset_path = (ROOT / args.dataset).resolve()
    output = (ROOT / args.output).resolve()
    if not dataset_path.is_relative_to(ROOT) or not output.is_relative_to(ROOT):
        raise ValueError("Dataset and output must stay within project root")
    dataset = json.loads(dataset_path.read_text(encoding="utf-8-sig"))
    conversations = dataset["conversations"]
    if not conversations or any(not c.get("turns") for c in conversations):
        raise ValueError("Expected conversations with at least one turn each")
    if len({c["id"] for c in conversations}) != len(conversations):
        raise ValueError("Conversation ids must be unique")
    selected = set(args.ids.split(",")) if args.ids else None
    if selected and not selected.issubset({c["id"] for c in conversations}):
        raise ValueError("Unknown conversation id in --ids")

    cfg = Settings()
    if cfg.answer_mode != "gemini" or not cfg.has_key:
        raise ValueError("A configured Gemini key is required")
    source_index = cfg.storage_dir / "rag.sqlite3"
    if not source_index.is_file():
        raise ValueError("Approved local retrieval index is required")
    chunks, vectors, metadata = Store(source_index).load_index()
    if not chunks:
        raise ValueError("Approved local retrieval index is empty")
    output.mkdir(parents=True, exist_ok=True)
    runtime = output / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    store = Store(runtime / "rag.sqlite3")
    store.replace_index(chunks, metadata, vectors)

    result_path, calls_path, run_path = (output / "responses.json", output / "gemini_calls.json", output / "run.json")
    results = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else []
    ledger = json.loads(calls_path.read_text(encoding="utf-8")) if calls_path.exists() else []
    dataset_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    index_hash = hashlib.sha256(json.dumps(
        {"chunks": [(chunk.id, chunk.text) for chunk in chunks], "metadata": metadata},
        ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    code_hash = hashlib.sha256(b"".join(
        path.read_bytes() for path in sorted((ROOT / "rag_app").glob("*.py")))).hexdigest()
    if run_path.exists():
        run = json.loads(run_path.read_text(encoding="utf-8"))
        if (run.get("dataset_sha256") != dataset_hash or run.get("model") != cfg.active_model
                or run.get("code_sha256") != code_hash or run.get("index_sha256") != index_hash):
            raise ValueError("Output folder belongs to another dataset/model/code/index")
    else:
        run = {"run_id": str(uuid4()), "started_at": datetime.now(UTC).isoformat(),
               "model": cfg.active_model, "dataset_sha256": dataset_hash,
               "index_sha256": index_hash, "code_sha256": code_hash,
               "transport": "direct_chat_service", "meal_service_mode": cfg.meal_service_mode,
               "note": "Actual ChatService responses preserved; answer_origin identifies static fallback."}

    proxy = urllib.request.getproxies().get("https")
    transport = httpx.HTTPTransport(proxy=proxy) if proxy else None
    run["http_proxy_transport"] = "configured HTTPS proxy via httpx.HTTPTransport" if proxy else "default configured httpx transport"
    provider = GeminiProvider(cfg, transport=transport)
    original_post = provider.client.post

    def recorded_post(model, method, body):
        entry = {"at": datetime.now(UTC).isoformat(), "model": model, "method": method}
        try:
            value = original_post(model, method, body)
            entry.update(success=True, response_id=value.get("responseId"), usage=value.get("usageMetadata", {}))
            return value
        except Exception as error:
            causes, cause = [], error.__cause__
            while cause is not None and len(causes) < 5:
                causes.append(type(cause).__name__)
                cause = cause.__cause__
            entry.update(success=False, error_class=type(error).__name__, error=str(error), cause_classes=causes)
            raise
        finally:
            ledger.append(entry)
            save(calls_path, ledger)

    provider.client.post = recorded_post
    service_cfg = cfg.model_copy(update={"storage_dir": runtime, "vector_backend": "sqlite",
        "rate_limit_per_minute": 300})
    services = []
    done = {(r["conversation_id"], r["turn_number"]) for r in results}
    for conversation in conversations:
        prior_turns = {n for cid, n in done if cid == conversation["id"]}
        if prior_turns and prior_turns != set(range(1, len(conversation["turns"]) + 1)):
            raise ValueError(f"Conversation {conversation['id']} is partial; restart it in a new output folder")
    try:
        for conversation in conversations:
            if selected and conversation["id"] not in selected:
                continue
            fixture = conversation.get("fixture", "configured")
            gateway = MockMealGateway(fixture) if fixture in {"mathematical", "named"} else create_meal_gateway(cfg)
            service = ChatService(service_cfg, store, provider, gateway)
            services.append(service)
            prior = [r for r in results if r["conversation_id"] == conversation["id"]]
            owner = prior[0]["owner"] if prior else "multiturn-eval:" + conversation["id"] + ":" + str(uuid4())
            session = UUID(prior[0]["session_id"]) if prior else None
            pending_proposal = None
            for i, turn in enumerate(conversation["turns"], 1):
                key = (conversation["id"], i)
                if key in done:
                    continue
                first_call, started = len(ledger), datetime.now(UTC)
                body = None
                retry_attempts = []
                try:
                    request = ChatRequest(message=turn["question"], session_id=session, save_history=False)
                    history_before = service.transient_history(owner, session) if session else None
                    state_before = copy.deepcopy(getattr(gateway, "states", {}).get(owner))
                    try:
                        response = service.chat(request, owner)
                    except ProviderFailure as first_error:
                        history_after = service.transient_history(owner, session) if session else None
                        state_after = copy.deepcopy(getattr(gateway, "states", {}).get(owner))
                        same_history = json.dumps(history_before, ensure_ascii=False, sort_keys=True, default=str) == json.dumps(history_after, ensure_ascii=False, sort_keys=True, default=str)
                        if (fixture == "configured" and "HTTP 503" in str(first_error)
                                and same_history and state_before == state_after):
                            retry_attempts.append({"attempt": 1, "error_class": type(first_error).__name__,
                                                   "error": str(first_error), "history_unchanged": True,
                                                   "fixture_state_unchanged": True})
                            response = service.chat(request, owner)
                        else:
                            raise
                    body = response.model_dump(mode="json")
                    session = response.session_id
                    record = {"conversation_id": conversation["id"], "title": conversation.get("title"),
                              "turn_number": i, "question": turn["question"], "expected": turn.get("expected"),
                              "owner": owner, "session_id": str(session), "fixture": fixture,
                              "transport": "direct_chat_service",
                              "response": body, "answer": body.get("answer"), "answer_origin": body.get("answer_origin"),
                              "returned_session_id": body.get("session_id"),
                              "provider_model": cfg.active_model if body.get("provider_response_ids") else None,
                              "provider_response_ids": body.get("provider_response_ids", []),
                              "gemini_calls": ledger[first_call:], "error": None}
                    record["retry_attempts"] = retry_attempts
                except Exception as error:
                    causes, cause = [], error.__cause__
                    while cause is not None and len(causes) < 5:
                        causes.append(type(cause).__name__)
                        cause = cause.__cause__
                    record = {"conversation_id": conversation["id"], "title": conversation.get("title"),
                              "turn_number": i, "question": turn["question"], "expected": turn.get("expected"),
                              "owner": owner, "session_id": str(session) if session else None, "fixture": fixture,
                              "transport": "direct_chat_service",
                              "response": None, "answer": None, "answer_origin": "unavailable",
                              "returned_session_id": None,
                              "provider_model": cfg.active_model, "provider_response_ids": [],
                              "gemini_calls": ledger[first_call:],
                              "error": {"class": type(error).__name__, "message": str(error), "cause_classes": causes}}
                    record["retry_attempts"] = retry_attempts
                record["elapsed_seconds"] = round((datetime.now(UTC) - started).total_seconds(), 2)
                results.append(record)
                save(result_path, results)
                meal_result = (body or {}).get("meal_result") or {}
                if meal_result.get("proposal"):
                    pending_proposal = meal_result["proposal"]
                elif meal_result.get("pending"):
                    pending_proposal = meal_result["pending"]
                if (body or {}).get("meal_edit_cancelled"):
                    pending_proposal = None
                if turn.get("action_after") == "apply_pending":
                    proposal = pending_proposal or meal_result.get("pending") or meal_result.get("proposal")
                    if not proposal:
                        action_record = {"action": "apply_pending", "success": False,
                                         "error": "No pending proposal in preceding response"}
                    else:
                        try:
                            applied = service.apply_meal_swap(owner, ApplySwap(
                                plan_id=proposal.get("planId", proposal.get("plan_id")),
                                proposal_id=proposal["id"],
                                base_version=proposal.get("baseVersion", proposal.get("base_version"))))
                            action_record = {"action": "apply_pending", "success": True,
                                             "result": applied.model_dump(mode="json")}
                            pending_proposal = None
                        except Exception as error:
                            action_record = {"action": "apply_pending", "success": False,
                                             "error": {"class": type(error).__name__, "message": str(error)}}
                    record["ui_equivalent_action"] = action_record
                    save(result_path, results)
                save(run_path, {**run, "completed_turns": len(results), "updated_at": datetime.now(UTC).isoformat()})
                print(json.dumps({"conversation_id": conversation["id"], "turn": i,
                                  "origin": record["answer_origin"], "calls": len(record["gemini_calls"]),
                                  "error": record.get("error"), "answer": record["answer"]}, ensure_ascii=False), flush=True)
    finally:
        for service in services:
            service.meals.close()
        provider.close()
    save(run_path, {**run, "completed_turns": len(results), "finished_at": datetime.now(UTC).isoformat()})
    print(f"FINISHED {len(results)} turns; {len(ledger)} Gemini calls", flush=True)


if __name__ == "__main__":
    main()
