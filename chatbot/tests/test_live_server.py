"""Opt-in check against an actual running localhost server, with a real paid answer."""

import json
import os
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

import pytest

from rag_app.config import ROOT


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_TESTS") != "1" or not os.environ.get("LIVE_SERVER_URL"),
    reason="Paid API and running server opt-in required",
)
def test_running_server_real_answer_and_static_safety():
    base = os.environ["LIVE_SERVER_URL"].rstrip("/")
    assert base in {"http://127.0.0.1:8000", "http://localhost:8000"}
    client = build_opener(ProxyHandler({}), HTTPCookieProcessor())
    with client.open(base + "/api/status", timeout=15) as result:
        state = json.load(result)
    mode = state["answer_mode"]
    assert mode in {"gemini", "openai"} and state[f"{mode}_configured"]

    def ask(message, consent, **extra):
        request = Request(base + "/api/chat", data=json.dumps({
            "message": message, "cloud_consent": consent, **extra,
        }).encode("utf-8"), headers={"Content-Type": "application/json"})
        with client.open(request, timeout=120) as response:
            return json.load(response)

    safety = ask("Bố tôi đang bất tỉnh", False)
    assert safety["answer_origin"] == "static" and not safety["provider_response_ids"]
    assert safety["status"] == "safety" and "115" in safety["answer"]
    answer = ask("Theo QĐ 5481 của Bộ Y tế, nên ăn trái cây nguyên miếng hay uống nước ép?", True)
    assert answer["status"] == "answered" and answer["answer_origin"] == mode
    assert len(answer["provider_response_ids"]) >= 2 and answer["usage"]["output_tokens"] > 0
    assert any(33 in c["pdf_pages"] for c in answer["citations"])
    # Legacy consent flag is accepted; it no longer controls provider access.
    first = ask("Theo Bộ Y tế bữa phụ cần cá nhân hóa không?", True, save_history=True)
    try:
        followup = ask("Năng lượng đó có tính vào cả ngày không?", True, session_id=first["session_id"])
        assert followup["status"] == "answered" and followup["answer_origin"] == mode
        assert "bữa phụ" in followup["answer"].lower()
        assert any("5.2.4" in c["section"] for c in followup["citations"])
        assert len(followup["provider_response_ids"]) >= 2
        assert not followup["history_saved"]
    finally:
        # Delete only this test-created, synthetic session.
        with client.open(Request(base + "/api/sessions/" + first["session_id"], method="DELETE")) as removed:
            assert removed.status == 204
    output = ROOT / "docs" / "eval_expanded" / "http-results.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "base_url": base, "status": state, "safety": safety,
        "real_answer": answer, "followup": followup,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
