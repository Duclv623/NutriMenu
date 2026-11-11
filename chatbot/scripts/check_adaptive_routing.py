"""Real-provider evaluation on an isolated copy of the current source index."""
import json
import sqlite3

from fastapi.testclient import TestClient

from rag_app.config import ROOT, Settings
from rag_app.main import create_app
from rag_app.provider import create_provider


def main():
    cfg = Settings()
    folder = ROOT / 'tmp/adaptive-routing-live'
    folder.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(cfg.storage_dir / 'rag.sqlite3') as source, sqlite3.connect(folder / 'rag.sqlite3') as target:
        source.backup(target)
    cfg = cfg.model_copy(update={'storage_dir': folder, 'rate_limit_per_minute': 100})
    cases = [
        ('habit', 'Tôi hay quên chuẩn bị đồ ăn mang đi làm. Có cách nào giúp tôi duy trì việc này không?', 'direct_llm'),
        ('concept', 'Giải thích carb và chất đạm bằng ngôn ngữ dễ hiểu.', 'direct_llm'),
        ('pho', 'Khi ăn phở ngoài quán thì tôi nên chú ý gì để kiểm soát lượng ăn?', 'practical_rag'),
        ('shift', 'Tôi làm ca đêm, bữa chính và bữa phụ nên sắp xếp thế nào?', 'practical_rag'),
        ('shift_followup', 'Ca của tôi từ 22h đến 6h, ngủ từ 8h đến 14h.', 'practical_rag'),
        ('source', 'Theo NIDDK, thời điểm ăn có phụ thuộc lịch làm việc không?', 'evidence_rag'),
        ('lookup', '100g sữa bò tươi có bao nhiêu calo?', 'structured_lookup'),
        ('safety', 'Tôi muốn tăng liều insulin thì nên làm thế nào?', 'safety'),
    ]
    output = ROOT / 'docs/release-2026-10-31/adaptive-routing-live.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    results = []
    failures = []
    provider = create_provider(cfg)
    audit = {}
    original_plan = provider.plan_response
    original_direct = provider.generate_direct
    original_generate = provider.generate

    def audit_plan(*args, **kwargs):
        result = original_plan(*args, **kwargs)
        audit['plan'] = result[0].model_dump()
        return result

    def audit_direct(*args, **kwargs):
        result = original_direct(*args, **kwargs)
        audit['direct_review'] = result[0]._grounding_review
        return result

    def audit_generate(*args, **kwargs):
        result = original_generate(*args, **kwargs)
        audit['grounding_review'] = result[0]._grounding_review
        audit['retrieved_sections'] = [h.chunk.section for h in args[1]]
        return result

    provider.plan_response = audit_plan
    provider.generate_direct = audit_direct
    provider.generate = audit_generate
    with TestClient(create_app(cfg, provider)) as client:
        shift_session = None
        for case_id, question, expected in cases:
            audit.clear()
            request = {'message': question, 'save_history': False}
            if case_id == 'shift_followup':
                request['session_id'] = shift_session
            response = client.post('/api/chat', json=request)
            body = response.json()
            if case_id == 'shift':
                shift_session = body.get('session_id')
            problems = []
            if response.status_code != 200:
                problems.append(f'HTTP {response.status_code}')
            elif body.get('response_strategy') != expected:
                problems.append(f'Expected {expected}, got {body.get("response_strategy")}')
            elif expected == 'direct_llm' and (body['citations'] or 'embedding' in body['timings_ms']):
                problems.append('Direct answering unexpectedly retrieved evidence.')
            elif (expected in {'practical_rag', 'evidence_rag', 'structured_lookup'}
                  and body.get('status') != 'needs_clarification' and not body['citations']):
                problems.append('Expected sourced answer.')
            if case_id == 'shift' and not body.get('clarification_question'):
                problems.append('Missing question about work/sleep times.')
            if case_id == 'shift_followup' and body.get('clarification_question'):
                problems.append('Repeated clarification after times were provided.')
            results.append({'id': case_id, 'question': question, 'expected_strategy': expected,
                            'problems': problems, 'response': body, 'audit': dict(audit)})
            output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(case_id, response.status_code, body.get('response_strategy'), problems,
                  body.get('answer', body.get('detail')), body.get('clarification_question'), flush=True)
            failures.extend(f'{case_id}: {p}' for p in problems)
    if failures:
        raise SystemExit('; '.join(failures))


if __name__ == '__main__':
    main()
