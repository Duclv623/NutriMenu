"""Publish the last complete snapshot and quota interruption without rewriting grades."""
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime

import numpy as np

from rag_app.config import ROOT, Settings
from scripts.run_expanded_eval import write_report


def read_rows(folder):
    return [json.loads(line) for line in (folder / 'results.jsonl').read_text(encoding='utf-8').splitlines()]


def api_errors(rows):
    return sum(bool(r.get('execution_error')) or r.get('http_status') != 200 for r in rows)


def main():
    root = ROOT / 'docs/eval_expanded'
    run = 'final_model'
    rows = read_rows(root / run)
    dataset = json.loads((ROOT / 'evals/expanded_questions.json').read_text(encoding='utf-8'))['cases']
    if Counter(r['id'] for r in rows) != Counter(c['id'] for c in dataset):
        raise ValueError('Snapshot must preserve exactly all 250 rows, including failures')
    metadata = json.loads((root / run / 'run.json').read_text(encoding='utf-8'))
    combined = root / 'final'
    combined.mkdir(exist_ok=True)
    (combined / 'results.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in sorted(rows, key=lambda r:r['id'])), encoding='utf-8')
    summary = write_report(combined, rows, {**metadata, 'component_runs':[run],
        'validation_scope':'Last complete snapshot BEFORE subsequent fixes; not current release validation.',
        'current_release_verified':False})
    summary['api_error_rows'] = api_errors(rows)
    summary['origin_counts'] = dict(Counter(r.get('actual',{}).get('answer_origin','http_error') for r in rows))
    latencies = [r['actual']['latency_ms'] for r in rows if r.get('actual',{}).get('status') == 'answered']
    summary['answered_latency_ms'] = {'p50':round(float(np.percentile(latencies,50))), 'p95':round(float(np.percentile(latencies,95)))}
    summary['generated_at'] = datetime.now(UTC).isoformat()
    (combined / 'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    path = combined / 'answers.md'
    path.write_text('# Phạm vi kết quả\n\nLượt 250 câu `final_model` TRƯỚC các sửa tiếp theo. Không phải điểm nghiệm thu code hiện tại. Giữ nguyên lỗi và điểm cũ.\n\n'+path.read_text(encoding='utf-8'),encoding='utf-8')
    partial = read_rows(root / 'verified_final')
    partial_meta = json.loads((root / 'verified_final' / 'summary.json').read_text(encoding='utf-8'))
    partial_meta.update({'interrupted_for_quota':True,'planned_cases':250,'unrun_cases':250-len(partial),
                        'api_error_rows':api_errors(partial),'current_release_verified':False})
    write_report(root / 'verified_final',partial,partial_meta)
    cfg = Settings()
    blocker = {'recorded_at':summary['generated_at'],'host':'api.openai.com','http_status':429,
        'verified_error_marker':'insufficient_quota','exact_credit_balance_known':False,
        'basis':'Tiny real embedding probe returned 429/insufficient_quota; key previously succeeded.',
        'current_app_code_sha256':hashlib.sha256(b''.join(p.read_bytes() for p in sorted((ROOT/'rag_app').glob('*.py')))).hexdigest(),
        'partial_run_app_code_sha256':partial_meta['app_code_sha256'],
        'planned_cases':250,'recorded_rows':len(partial),'passed_rows':sum(r['passed'] for r in partial),
        'api_error_rows':api_errors(partial),'unrun_cases':250-len(partial),
        'pending_supplemental_cases':20,'pending_stability_runs':60,
        'next_action':'Restore API credits/usage availability, then use NEW output folders; do not bypass version checks.'}
    (root/'quota-blocker.json').write_text(json.dumps(blocker,ensure_ascii=False,indent=2),encoding='utf-8')
    ingestion = json.loads((ROOT/'storage/ingestion_report.json').read_text(encoding='utf-8'))
    lines = ['# Báo cáo triển khai và đánh giá RAG mở rộng','',f"Ngày tạo: {summary['generated_at']}",'',
        '## Tình trạng bàn giao','',
        'Đã triển khai RAG 4 nguồn/59 chunk, bộ 250 câu có tiêu chí và chạy nhiều vòng API thật để sửa lỗi. **Chưa nghiệm thu code hiện tại**: OpenAI trả HTTP 429 `insufficient_quota` kể cả embedding rất nhỏ. Key đã hoạt động ở các vòng trước; chưa biết chính xác số dư hoặc hạn mức tài khoản. Không có fallback mock/offline.','',
        f"Lượt 250 câu chạy đủ gần nhất (`final_model`, trước các sửa tiếp theo): **{summary['passed']}/250 đạt**, {summary['api_error_rows']} hàng có lỗi API/chấm. Giữ nguyên toàn bộ 23 hàng chưa đạt; không đổi điểm cũ thành PASS sau sửa code.",'',
        f"Lượt xác nhận mới (`verified_final`): {len(partial)} hàng ghi, **18 đạt, {api_errors(partial)} lỗi API/thực thi**, còn {250-len(partial)} câu chưa chạy. Không phải 71 câu AI trả lời thành công. Job đã dừng khi xác nhận quota.",'',
        '124 kiểm thử logic đạt; Ruff đạt. Hai smoke API thật từng đạt trên bản trước sửa cuối, chưa chạy lại AI smoke bản hiện tại. Đã khóa checksum 20 cách hỏi/tổ hợp bổ sung **chưa chạy API**; vòng ổn định 30 câu × 2 lượt cũng còn chờ.','',
        '## Dữ liệu và phương pháp','',
        '- PDF đọc trực tiếp bằng pypdf, không cần chuyển DOCX. DOCX đọc XML, giữ vị trí đoạn/bảng/hàng/cột; bảng thực đơn giữ cột ngày. Không tự tải/index mọi link trong DOCX.',
        '- Duyệt phạm vi và SHA256; chia theo mục tối đa 420 token, overlap 60, ưu tiên biên câu/dòng/từ. BM25 tiếng Việt + cosine embedding + RRF 60, top 5, giữ một hit lexical; lọc nguồn/mục/chủ thể khi hỏi rõ.',
        f'- Cấu hình hiện tại: embedding `{cfg.embedding_model}`, sinh câu `{cfg.openai_model}`, kiểm nguồn `{cfg.grounding_model or cfg.openai_model}`, judge `gpt-4.1`; Responses Structured Outputs, store=False.',
        '- Kiểm ID dòng bằng chứng/ví dụ thực phẩm/chủ thể bữa phụ phía server. Tối đa hai lần sinh/kiểm (tối đa bốn Responses); bản sửa phải kiểm lại. Usage cộng các lượt, chưa tính embedding.',
        '- Câu chào/an toàn/ngoài phạm vi là static có nhãn. answer_origin/model/grounding_model/response IDs/token phân biệt lượt AI thật và thông báo quy tắc.','',
        '| Nguồn | Chunk | Bao phủ chữ đã duyệt |','|---|---:|---|']
    for source in ingestion['sources']:
        coverage = source.get('approved_text_coverage')
        text = f'{coverage*100:.0f}% chữ DOCX được chọn' if coverage is not None else 'PDF mục 5.2, trang vật lý 30–34'
        lines.append(f"| {source['source_id']} | {source['chunks']} | {text} |")
    lines.extend(['','Không index mọi file: DOCX trùng loại bỏ; ADA 2026 reference_only theo điều kiện nguồn; FCT 2007 dành cho TV2; tài liệu thuốc/phạm vi chưa duyệt bị loại. Ảnh chưa OCR. Bao phủ chữ được chọn không phải bao phủ toàn tài liệu/y khoa.','',
        '## Đánh giá từng câu','',
        '250 câu khóa checksum trước API: 200 phát triển, 50 giữ lại đến vòng riêng đầu tiên. Sau đọc lỗi/sửa, cả 250 là hồi quy. 20 câu mới chưa có kết quả, là biến thể cùng nhóm nguồn, không phải benchmark lâm sàng độc lập.','',
        'Kiểm HTTP/status/intent/citation/vị trí/provenance; judge riêng dùng gold/source định trước với bốn điểm 0–2: bám nguồn, trọng tâm, đủ ý, an toàn. PASS cần tất cả 2, không unsupported_claims/lỗi quy tắc. Judge khác generator nhưng hiện cùng model critic; vẫn có thể sai tương quan. Không dùng runtime review làm gold.','',
        'Rà thủ công 25 ca an toàn, các lỗi và mẫu số liệu/hội thoại: C008 từng được judge cho đạt dù trích năng lượng chung không có chủ thể bữa phụ; đã sửa retrieval/kiểm chủ thể. O009 bị judge hiểu sai thông báo chưa tích hợp; giữ nguyên điểm gốc. Không có chuyên gia thẩm định/không tuyên bố đọc thủ công toàn bộ 250 đáp án.','',
        '## Snapshot chạy đủ trước sửa cuối','',
        '| Nhóm | Đạt | Tổng |','|---|---:|---:|'])
    for group, stats in summary['groups'].items():
        lines.append(f"| {group} | {stats['passed']} | {stats['total']} |")
    lines.extend(['','Các hàng chưa đạt: '+', '.join(summary['failed_ids'])+'.','',
        '## Sửa lỗi và việc còn mở','',
        '- Sửa parser/cột ngày/preview, hiểu nhầm “tài liệu” thành “liều”, bỏ thuốc lá, bệnh được phủ định và giữ an toàn qua nhiều lượt.',
        '- Lịch sử đúng owner kể cả lượt sau không lưu; tách câu hỏi hiện tại khỏi query truy hồi. Lọc chủ thể bữa phụ, tránh dùng bảng thực đơn để chứng minh lý thuyết đạm.',
        '- Sửa kiểm ví dụ chặn nhầm “như sau”, ngoặc, từ đồng nghĩa, “cũng chứa”, “nên chiếm”; vẫn chặn dầu dừa không có nguồn. C002 replay cục bộ từ bản nháp API lưu trước đạt kiểm literal, **chưa xác nhận API mới**, giữ nguyên grade cũ.',
        '- Bỏ payload text lặp chưa đánh số, thêm allowed_line_ids; tối đa một vòng sửa nếu critic yêu cầu hoặc mọi block bị loại.',
        '- K068/K079/K093 còn bị chấm thiếu ý ở lượt gần cuối: đường tự do, trao đổi chuyên gia trước vận động, chăm sóc chân. K079/K093 có gold rộng hơn câu hỏi cụ thể, cần rà rubric độc lập; chưa sửa gold/đổi điểm/chứng minh ổn định.',
        '- Runner đọc accepted_statuses có sẵn; chat lỗi không gọi tiếp judge. Tự dừng hàng chờ khi xác định quota, các job đang chạy có thể hoàn tất.',
        '- Còn chờ API quota: 250 câu trên code hiện tại; 20 câu mới; 30 câu × 2 đo ổn định; AI smoke HTTP sau sửa cuối. Dùng thư mục mới vì checksum code đã thay đổi.','',
        '## Lịch sử các vòng','',
        'Các vòng khác model/prompt/code/selection, không so điểm trực tiếp. Partial không đại diện bộ đầy đủ. Token có phí.','',
        '| Vòng | Đạt | Hàng ghi |','|---|---:|---:|'])
    for path in sorted(root.glob('*/summary.json')):
        if path.parent.name == 'final':
            continue
        record = json.loads(path.read_text(encoding='utf-8'))
        lines.append(f"| {path.parent.name} | {record['passed']} | {record['total']} |")
    lines.extend(['',f"Snapshot origins: `{json.dumps(summary['origin_counts'],ensure_ascii=False)}`.",'',
        f"Độ trễ answered p50 {summary['answered_latency_ms']['p50']} ms, p95 {summary['answered_latency_ms']['p95']} ms; không phải kiểm tải production.",'',
        f"Token sinh/kiểm nguồn/judge snapshot: `{json.dumps(summary['generation_and_judge_tokens'])}`. Chưa tính embedding/retry/các vòng khác; không suy ra số dư tài khoản.",'',
        '## Truy hồi BYT cũ','',
        'Đo trước bộ lọc bảng mới, không đại diện code cuối. 20 câu gold mục BYT dù corpus có bốn nguồn; nguồn khác đúng không tính hit BYT.','',
        '| Mode | Hit@1 | Hit@3 | Hit@5 | MRR@5 |','|---|---:|---:|---:|---:|'])
    for mode in ['lexical','dense','hybrid']:
        data = json.loads((ROOT/f'docs/evaluation_expanded_{mode}.json').read_text(encoding='utf-8'))
        lines.append(f"| {mode} | {data['hit_at_1']:.2f} | {data['hit_at_3']:.2f} | {data['hit_at_5']:.2f} | {data['mrr_at_5']:.3f} |")
    lines.extend(['','Hybrid chưa luôn tốt hơn BM25 theo thước đo này; cần đo lại code hiện tại khi API khả dụng.','',
        '## Toàn đồ án còn thiếu','',
        '- TV1/JWT gateway, TV2 Food Service, sinh/đổi thực đơn CP-SAT chưa nối. food_menu đạt nhờ báo đúng chưa tích hợp, không chứng minh chức năng thực đơn hoàn thành.',
        '- 853 thực phẩm/1250 món NIN đã chuẩn hóa theo 100 g (08/10/2026); còn thiếu quy đổi bát/hộp/ml và công thức nếu cần chức năng đó. Thiếu dữ liệu giữ null, không để LLM đoán.',
        '- Chưa thẩm định chuyên gia/OCR ảnh/kiểm tải/triển khai production. Bộ hữu hạn không bao phủ mọi cách hỏi.','',
        '## Hồ sơ kiểm tra','',
        '- [Kế hoạch trước code và việc còn chờ](IMPLEMENTATION_RAG_PLAN.md)',
        '- [250 câu + tiêu chí](CHAT_CHECK_250.md)',
        '- [20 câu bổ sung chưa chạy](CHAT_CHECK_SUPPLEMENTAL_20.md)',
        '- [Từng đáp án/điểm snapshot trước sửa cuối](eval_expanded/final/answers.md)',
        '- [Kết quả gốc snapshot](eval_expanded/final/results.jsonl)',
        '- [Lượt mới bị quota chặn](eval_expanded/verified_final/answers.md)',
        '- [Trạng thái blocker](eval_expanded/quota-blocker.json)',
        '- [124 kiểm thử logic](expanded-unit-tests.xml)',
        '- [Giao diện API thật trước sửa cuối](eval_expanded/ui-proof.png)',
        '- [Giao diện hiện tại báo quota thật, không trả mock](eval_expanded/ui-quota-proof.png)',
        '- [Replay C002 cục bộ, không phải API mới](eval_expanded/c002-local-replay.json)','',
        'Lệnh chạy tiếp trong README. Cần kiểm tra [Billing/Usage API theo hướng dẫn OpenAI](https://developers.openai.com/api/docs/guides/error-codes); retry không bổ sung tín dụng.'])
    (ROOT/'docs/EXPANDED_RAG_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'snapshot_passed':summary['passed'],'snapshot_total':250,
        'snapshot_api_errors':summary['api_error_rows'],'partial_rows':len(partial),
        'partial_api_errors':api_errors(partial),'current_release_verified':False},indent=2))


if __name__ == '__main__':
    main()
