"""Collect full live /api/chat responses for the current 30-case meal eval."""
import argparse
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from rag_app.config import ROOT, Settings
from rag_app.domain import ChatRequest
from rag_app.domain import ChatRequest
from rag_app.main import create_app
from rag_app.meal_gateway import MockMealGateway
from rag_app.meal_models import ApplySwap, SwapRequest
from rag_app.provider import create_provider
from rag_app.store import Store
from rag_app.service import ChatService


def save(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def save_answers(path, rows):
    lines = ["# Meal evaluation responses", "",
             "The JSON file contains full API responses and structured fixture state. `static` means app-generated, not Gemini-authored.", ""]
    for row in rows:
        lines.extend([f"## {row['id']} — {row.get('fixture', row.get('dataset', 'mathematical'))}", "",
                      "**Expected:** " + str(row.get("expectation", row.get("expect", ""))), ""])
        for turn in row.get("turns", []):
            response = turn.get("response") or {}
            lines.extend(["**User:** " + turn.get("message", ""), "",
                          "**Answer:** " + str(response.get("answer", turn.get("error", "No response"))), "",
                          f"transport={turn.get('transport', 'direct_chat_service')} · HTTP={turn.get('http_status')} · origin={response.get('answer_origin', row.get('answer_origin', 'unavailable'))} · Gemini calls={len(turn.get('gemini_calls', []))}", ""])
        if row.get("apply_action"):
            action = row["apply_action"]
            lines.extend([f"**Apply action:** {action.get('action')} · HTTP={action.get('http_status')} · plan version {row.get('plan_version_before')} → {row.get('plan_version_after')}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def plan_state(snapshot):
    plan = snapshot.get("plan") or {}
    return {"plan_id": plan.get("id"), "version": plan.get("version"),
            "totals": plan.get("totals"), "items": plan.get("items", [])}


def prepare_scenario(case, gateway, owner, context):
    original = gateway.states[owner][1]
    name = case.get("scenario")
    if name == "unknown_allergy":
        original.profile.allergies = None
    elif name == "out_of_scope":
        original.profile.scope_status = "out_of_scope"
    elif name == "stale":
        p = gateway.preview(owner, SwapRequest(plan_id=original.plan.id, base_version=1,
            item_id="breakfast-1", instruction="Đổi món sáng"))
        gateway.apply(owner, ApplySwap(plan_id=original.plan.id, base_version=1, proposal_id=p.id))
    elif name == "wrong_owner":
        context["plan_id"] = gateway.snapshot("dev:" + str(uuid4())).plan.id


def run_case(case, cfg, provider, ledger):
    gateway = MockMealGateway(case.get("dataset", "mathematical"))
    app = create_app(cfg, provider, gateway)
    with TestClient(app) as client:
        snapshot_response = client.get("/api/meal-context")
        snapshot = snapshot_response.json()
        owner = "dev:" + client.cookies["datn_owner"]
        context = {"plan_id": snapshot["plan"]["id"], "plan_version": snapshot["plan"]["version"]}
        if case.get("selection"):
            context["item_id"] = case["selection"]
        prepare_scenario(case, gateway, owner, context)
        before = client.get("/api/meal-context").json()
        turns = []
        session_id = None
        apply_result = None
        last_chat = None
        first_proposal = None
        for index, message in enumerate(case["turns"]):
            request = {"message": message}
            if index == 0:
                request["meal_context"] = context
            elif session_id:
                request["session_id"] = session_id
            call_start = len(ledger)
            started = time.monotonic()
            response = client.post("/api/chat", json=request)
            result = response.json()
            session_id = result.get("session_id", session_id)
            last_chat = result
            if index == 0:
                first_proposal = ((result.get("meal_result") or {}).get("proposal"))
            turns.append({"message": message, "http_status": response.status_code,
                "elapsed_seconds": round(time.monotonic() - started, 2), "response": result,
                "gemini_calls": ledger[call_start:]})
            if response.status_code >= 500 or any(not c.get("success", False) for c in ledger[call_start:]):
                break
        # The chat affirmation is recorded separately from a user clicking Apply.
        after_chat = client.get("/api/meal-context").json()
        if case.get("apply_after_turn") is not None and last_chat:
            proposal = first_proposal
            if proposal:
                body = {"planId": proposal.get("plan_id"), "proposalId": proposal.get("id"),
                        "baseVersion": proposal.get("base_version")}
                applied = client.post("/api/meal-plans/apply-swap", json=body)
                apply_result = {"action": "explicit_apply_endpoint_click", "request": body,
                    "http_status": applied.status_code, "response": applied.json() if applied.content else None}
        after = client.get("/api/meal-context").json()
        last_meal = (last_chat or {}).get("meal_result") or {}
        proposal = last_meal.get("proposal") or {}
        return {**case, "fixture": case.get("dataset", "mathematical"),
            "fixture_before": before, "turns": turns,
            "ui_choices": last_meal.get("choices", []), "meal_view": last_meal.get("view"),
            "proposal_snapshot": proposal or None,
            "proposal_current_totals": (before.get("plan") or {}).get("totals"),
            "proposal_totals": ((proposal.get("plan") or {}).get("totals") if proposal else None),
            "fixture_after_chat_before_apply": after_chat,
            "apply_action": apply_result, "fixture_after": after,
            "plan_version_before": (before.get("plan") or {}).get("version"),
            "plan_version_after": (after.get("plan") or {}).get("version"),
            "answer_origin": (last_chat or {}).get("answer_origin")}


def run_case_direct(case, cfg, provider, ledger):
    """Run the same ChatService route without TestClient's Windows socketpair."""
    gateway = MockMealGateway(case.get("dataset", "mathematical"))
    store = Store(cfg.storage_dir / "rag.sqlite3")
    service = ChatService(cfg, store, provider, gateway)
    owner = "eval:" + case["id"] + ":" + str(uuid4())
    initial = gateway.snapshot(owner).model_dump(mode="json")
    context = {"plan_id": initial["plan"]["id"], "plan_version": initial["plan"]["version"]}
    if case.get("selection"):
        context["item_id"] = case["selection"]
    prepare_scenario(case, gateway, owner, context)
    before = gateway.snapshot(owner).model_dump(mode="json")
    turns, session_id, last_chat, first_proposal = [], None, None, None
    for index, message in enumerate(case["turns"]):
        request = ChatRequest(message=message, session_id=session_id,
            meal_context=context if index == 0 and not case.get("no_context") else None, save_history=False)
        call_start, started = len(ledger), time.monotonic()
        try:
            response = service.chat(request, owner)
            result = response.model_dump(mode="json")
            session_id = response.session_id
            last_chat = result
            if index == 0:
                first_proposal = ((result.get("meal_result") or {}).get("proposal"))
            turns.append({"message": message, "transport": "direct_chat_service",
                "http_status": 200, "elapsed_seconds": round(time.monotonic()-started, 2),
                "response": result, "gemini_calls": ledger[call_start:]})
        except Exception as error:
            turns.append({"message": message, "transport": "direct_chat_service",
                "http_status": 503 if type(error).__name__ == "ProviderFailure" else None,
                "error_class": type(error).__name__, "error": str(error),
                "elapsed_seconds": round(time.monotonic()-started, 2),
                "gemini_calls": ledger[call_start:]})
            break
    after_chat = gateway.snapshot(owner).model_dump(mode="json")
    apply_result = None
    if case.get("apply_after_turn") is not None and first_proposal:
        body = ApplySwap(plan_id=first_proposal.get("plan_id", first_proposal.get("planId")),
            proposal_id=first_proposal["id"],
            base_version=first_proposal.get("base_version", first_proposal.get("baseVersion")))
        try:
            result = service.apply_meal_swap(owner, body)
            apply_result = {"action": "explicit_apply_endpoint_contract_direct_service",
                "request": body.model_dump(mode="json"), "http_status": 200,
                "response": result.model_dump(mode="json")}
        except Exception as error:
            apply_result = {"action": "explicit_apply_endpoint_contract_direct_service",
                "request": body.model_dump(mode="json"), "error_class": type(error).__name__,
                "error": str(error)}
    after = gateway.snapshot(owner).model_dump(mode="json")
    meal = (last_chat or {}).get("meal_result") or {}
    proposal = meal.get("proposal") or {}
    service.meals.close()
    return {**case, "fixture": case.get("dataset", "mathematical"), "transport": "direct_chat_service",
        "fixture_before": before, "turns": turns, "ui_choices": meal.get("choices", []),
        "meal_view": meal.get("view"), "proposal_snapshot": proposal or None,
        "proposal_current_totals": (before.get("plan") or {}).get("totals"),
        "proposal_totals": ((proposal.get("plan") or {}).get("totals") if proposal else None),
        "fixture_after_chat_before_apply": after_chat, "apply_action": apply_result,
        "fixture_after": after, "plan_version_before": (before.get("plan") or {}).get("version"),
        "plan_version_after": (after.get("plan") or {}).get("version"),
        "answer_origin": (last_chat or {}).get("answer_origin")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--ids", default="")
    parser.add_argument("--interval", type=float, default=0)
    parser.add_argument("--transport", choices=["direct", "testclient"], default="direct")
    parser.add_argument("--dataset", choices=["current30", "meal50"], default="current30")
    args = parser.parse_args()
    out = (ROOT / args.output).resolve()
    if not out.is_relative_to(ROOT):
        raise ValueError("Output must stay within project root")
    out.mkdir(parents=True, exist_ok=True)
    data_path = ROOT / ("evals/meal_current_questions_30.json" if args.dataset == "current30"
                        else "evals/meal_questions_50.json")
    data = json.loads(data_path.read_text(encoding="utf-8-sig"))
    cases = data["cases"]
    expected_count = 30 if args.dataset == "current30" else 50
    if len(cases) != expected_count or len({c["id"] for c in cases}) != expected_count:
        raise ValueError(f"Expected {expected_count} unique cases")
    if args.dataset == "meal50":
        old_cases = {case["id"]: case for case in cases}
        for case in cases:
            if "turns" not in case:
                prior = old_cases.get(case.get("prior"))
                case["turns"] = ([prior["question"]] if prior else []) + [case["question"]]
            case["no_context"] = bool(case.get("no_context"))
            case.setdefault("dataset", "mathematical")
            case["expectation"] = case.pop("expect", "")
    cfg = Settings()
    if cfg.answer_mode != "gemini" or not cfg.has_key:
        raise ValueError("A configured real Gemini key is required")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("rag_app").setLevel(logging.WARNING)
    rows_path, calls_path, run_path = out / "responses.json", out / "gemini_calls.json", out / "run.json"
    rows = json.loads(rows_path.read_text(encoding="utf-8")) if rows_path.exists() else []
    ledger = json.loads(calls_path.read_text(encoding="utf-8")) if calls_path.exists() else []
    selected = set(args.ids.split(",")) if args.ids else None
    fingerprint = hashlib.sha256(data_path.read_bytes()).hexdigest()
    code_hash = hashlib.sha256(b"".join(p.read_bytes() for p in sorted((ROOT / "rag_app").glob("*.py")))).hexdigest()
    if run_path.exists():
        meta = json.loads(run_path.read_text(encoding="utf-8"))
        if (meta.get("dataset_sha256") != fingerprint or meta.get("code_sha256") != code_hash
                or meta.get("transport") != args.transport or meta.get("dataset_name") != args.dataset):
            raise ValueError("Output folder belongs to another dataset/code/transport; use a new output folder")
    else:
        meta = {"started_at": datetime.now(UTC).isoformat(), "scope": data["scope"],
        "dataset_sha256": fingerprint, "code_sha256": code_hash,
        "model": cfg.gemini_model, "interval_seconds": args.interval,
        "fixture_note": "Mock mathematical/named fixture; no CP-SAT or real patient plan.",
        "response_origin_note": "answer_origin and gemini_calls identify actual model responses; static app output is preserved as returned.",
        "transport": args.transport, "dataset_name": args.dataset}
    index_chunks, vectors, index_meta = Store(cfg.storage_dir / "rag.sqlite3").load_index()
    if not index_chunks:
        raise ValueError("Approved local retrieval index is required")
    isolated = out / "runtime"
    Store(isolated / "rag.sqlite3").replace_index(index_chunks, index_meta, vectors)
    cfg = cfg.model_copy(update={"storage_dir": isolated, "vector_backend": "sqlite",
        "meal_service_mode": "mock", "rate_limit_per_minute": 300})
    from scripts.live_pacer_audit import install_pacer
    for case in cases:
        if selected and case["id"] not in selected or any(r["id"] == case["id"] for r in rows):
            continue
        provider = create_provider(cfg)
        install_pacer(provider, args.interval, ledger)
        try:
            row = (run_case_direct(case, cfg, provider, ledger) if args.transport == "direct"
                   else run_case(case, cfg, provider, ledger))
            rows.append(row)
            meta["completed_cases"] = len(rows)
            save(rows_path, rows)
            save_answers(out / "answers.md", rows)
            save(calls_path, ledger)
            save(run_path, meta)
            print(case["id"], "turns", len(row["turns"]), "calls", len(ledger),
                  "origin", row.get("answer_origin"), flush=True)
        finally:
            provider.close()
    meta["finished_at"] = datetime.now(UTC).isoformat()
    meta["completed_cases"] = len(rows)
    save(run_path, meta)
    save_answers(out / "answers.md", rows)
    print("FINISHED", len(rows), "cases;", len(ledger), "Gemini calls", flush=True)


if __name__ == "__main__":
    main()
