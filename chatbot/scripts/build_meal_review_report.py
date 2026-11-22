"""Build a readable audit from recorded live runs and case-by-case human review."""
import json
from collections import Counter
from datetime import datetime

from rag_app.config import ROOT

DIRECTORY = ROOT / 'docs/meal-review-2026-11-07'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def answer(row):
    result = row['response']
    text = result.get('answer') or json.dumps(result.get('detail'), ensure_ascii=False)
    if result.get('clarification_question'):
        text += '\n\nCâu hỏi làm rõ: ' + result['clarification_question']
    return '\n'.join('> ' + line for line in text.splitlines())


def main():
    phases = {name: read(DIRECTORY / name / 'responses.json') for name in ('baseline', 'after-fixes', 'final-targeted')}
    before = {row['id']: row for row in phases['baseline']}
    latest = {row['id']: row for row in phases['after-fixes']}
    latest.update({row['id']: row for row in phases['final-targeted']})
    targeted = {row['id'] for row in phases['final-targeted']}
    manual = read(ROOT / 'evals/meal_manual_review_2026-11-07.json')['cases']
    assert len(manual) == 50 and {row['id'] for row in manual} == set(before) == set(latest)
    calls = []
    for phase in phases:
        calls.extend(read(DIRECTORY / phase / 'gemini_calls.json'))
    calls.sort(key=lambda row: row['at'])
    gaps = [(datetime.fromisoformat(b['at']) - datetime.fromisoformat(a['at'])).total_seconds()
            for a, b in zip(calls, calls[1:], strict=False)]
    summary = {
        'cases': 50,
        'manual_before': dict(Counter(row['before'] for row in manual)),
        'manual_after': dict(Counter(row['after'] for row in manual)),
        'gemini_before': dict(Counter(row['gemini_review']['verdict'] for row in before.values())),
        'gemini_after_main_run': dict(Counter(row['gemini_review']['verdict'] for row in phases['after-fixes'])),
        'gemini_latest_mixed_runs': dict(Counter(row['gemini_review']['verdict'] for row in latest.values())),
        'app_after_origins': dict(Counter(row['response'].get('answer_origin') for row in latest.values())),
        'logical_gemini_calls': len(calls),
        'successful_logical_calls': sum(bool(row.get('success')) for row in calls),
        'failed_logical_calls': sum(not row.get('success') for row in calls),
        'quota_errors': sum('429' in row.get('error', '') for row in calls),
        'minimum_logged_start_gap_seconds': round(min(gaps), 2),
        'offline_tests': '456 passed, 3 live deselected; 212.15 seconds',
        'ui_checks': read(DIRECTORY / 'ui-check.json'),
        'note': 'Latest answers overlay nine targeted rechecks on the complete 50-case after-fixes run. Judge v1 inspected text/citations but not full UI/proposals; manual review corrected that limitation. The reusable runner now uses v2 inputs, not retroactively rerun or relabeled here.',
    }
    (DIRECTORY / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = [
        '# 50 câu hỏi thực đơn: câu trả lời trước/sau và nhận xét từng câu', '',
        'Kiểm tra ngày 07–08/11/2026. Đã dùng khóa Gemini thật đang cấu hình; không ghi khóa vào báo cáo. Món A/B/C, hồ sơ và phương án đổi là dữ liệu giả lập từ ví dụ recom.docx. Đây là đánh giá trải nghiệm và tính nhất quán dữ liệu mẫu, chưa phải nghiệm thu CP-SAT thật hay thẩm định dinh dưỡng cá nhân.', '',
        '## Cách đọc kết quả', '',
        '- Chạy 50 câu trước sửa, chạy lại đủ 50 câu sau lượt sửa chính; sau đó kiểm tra bổ sung 9 câu vừa chỉnh lần cuối. Phần “sau sửa cuối” dưới đây lấy bản mới nhất theo từng câu, không giả nhận là một lượt chạy duy nhất.',
        '- Mỗi câu là một tài khoản/phiên thử độc lập; chỉ câu có “prior” mới nối với câu trước được chỉ định. Câu hỏi mơ hồ được thử cùng món đang chọn trên màn hình nếu có.',
        '- Gemini thật được bật. Số liệu thực đơn có sẵn trả bằng logic dữ liệu, không buộc AI tính lại. Bản sau có 47 câu origin=static, 3 câu origin=gemini. Gemini còn chấm lời văn cho từng câu theo nhóm nhỏ.',
        '- Có câu cần hỏi lại, có câu cần báo chưa hỗ trợ: phản hồi phù hợp không có nghĩa là chức năng chưa kết nối đã được triển khai.',
        '- Nhận xét thủ công dưới đây đối chiếu cả lời văn, dữ liệu trả về và giao diện. Nhận xét Gemini là ý kiến bổ sung, không phải kết luận chuyên môn.', '',
        '## Kết quả tổng hợp', '',
        '| Cách đánh giá | Trước sửa | Sau sửa |', '|---|---|---|',
        '| Gemini, lượt đủ 50 câu | 23 đạt, 27 cần sửa | 47 đạt, 3 cần sửa |',
        '| Đối chiếu thủ công theo phạm vi thử | 11 đạt, 13 cần cải thiện, 26 chưa đạt | 49 đạt tiêu chí, 1 có thể gọn hơn |', '',
        'Còn một góp ý về lời văn ở M043: câu giải thích carbohydrate có thể gọn hơn. Các trạng thái ĐẠT chỉ áp dụng tiêu chí của bộ câu hỏi và dữ liệu mẫu; không phải tỷ lệ chính xác y khoa hay cam kết cho mọi cách hỏi.', '',
        '## Lưu ý khi dùng điểm Gemini', '',
        'Lượt chấm v1 chỉ xem phần chữ, trích dẫn và thông tin chuẩn bị, chưa thấy đầy đủ nút lựa chọn và phương án. Vì vậy Gemini từng bỏ sót M042: phương án tăng calo dù người dùng muốn giảm. Ngược lại, M024 bị chấm thiếu lựa chọn dù API và giao diện có các nút chọn bữa/món. Những điểm này được sửa bằng đối chiếu dữ liệu và kiểm tra Chrome.', '',
        'Ở lượt bổ sung, Gemini còn yêu cầu M019 không lặp M018 dù hai câu nằm trong hai phiên độc lập, và yêu cầu M025 thêm câu hỏi gợi ý dù đã trả đủ và chức năng đổi bữa trưa chưa có. Không áp dụng máy móc những gợi ý làm dài hoặc lạc câu trả lời. Script kiểm tra lần sau đã bổ sung thông tin phiên độc lập, choices và tổng trước/sau vào đầu vào chấm v2; các kết quả đã ghi vẫn giữ nhãn v1.', '',
        f"Tổng nhật ký: {len(calls)} lượt gọi Gemini ở mức hàm API, {summary['successful_logical_calls']} thành công, {summary['failed_logical_calls']} lỗi kết nối; không ghi nhận 429. Khoảng cách bắt đầu nhỏ nhất giữa các lượt được ghi là {summary['minimum_logged_start_gap_seconds']} giây. Không gọi song song. Bộ cung cấp có cơ chế thử lại một lần cho lỗi dịch vụ tạm thời, nên số này không khẳng định số request HTTP vật lý hoặc tiền thanh toán.", '',
        'Lỗi kết nối thứ nhất nằm ở M003 của bản trước; lỗi thứ hai xảy ra khi chấm nhóm cuối ở bản sau, đã tiếp tục riêng nhóm còn thiếu. Không sinh câu trả lời giả để thay lỗi mạng.', '',
        '## Nhận xét từng câu', '',
    ]
    for review in manual:
        key = review['id']
        a, b = before[key], latest[key]
        setup = ', '.join(f'{name}={a[name]}' for name in ('selection', 'prior', 'scenario', 'no_context') if a.get(name)) or 'ngữ cảnh thực đơn đang mở'
        source = 'final-targeted' if key in targeted else 'after-fixes'
        judge = b['gemini_review']
        payload = b['response'].get('meal_result') or {}
        lines.extend([
            f"### {key}. {a['question']}", '', f'**Chuẩn bị:** {setup}.', '',
            '**Mong đợi:** ' + a['expect'], '', '**Trước sửa — ' + review['before'] + ':**', '', answer(a), '',
            '**Vấn đề/điểm tốt:** ' + review['finding'], '', '**Cách xử lý:** ' + review['fix'], '',
            '**Sau sửa cuối — ' + review['after'] + ':**', '', answer(b), '',
            '**Nhận xét:** ' + review['assessment'], '',
            f"**Bản ghi:** {source}/responses.json · HTTP {b['http_status']} · origin={b['response'].get('answer_origin')} · status={b['response'].get('status')}", '',
        ])
        if payload.get('choices'):
            lines.extend(['**Nút lựa chọn người dùng thấy:** ' + '; '.join(c['label'] for c in payload['choices']), ''])
        proposal = payload.get('proposal')
        if proposal:
            old_total, new_total = payload['plan']['totals']['energyKcal'], proposal['plan']['totals']['energyKcal']
            lines.extend([f'**Dữ liệu phương án:** Tổng ngày {old_total:g} → {new_total:g} kcal; chỉ xem trước, chưa lưu.', ''])
        lines.extend([
            f"**Gemini chấm bản này:** {judge['verdict']}. {judge['reason']}", '',
            f"Điểm trọng tâm/thân thiện/dễ hiểu/đúng dữ liệu mẫu: {judge['relevance']}/{judge['friendliness']}/{judge['plain_language']}/{judge['factuality_within_fixture']} (mỗi tiêu chí tối đa 2). ID lượt chấm: {b['judge_response_id']}.", '',
        ])
    lines.extend([
        '## Tài liệu đi kèm', '',
        '- [Kế hoạch sửa và tích hợp](REVIEW_AND_FIX_PLAN.md)',
        '- [Danh sách 50 câu hỏi có tiêu chí](../../evals/meal_questions_50.json)',
        '- [Nhận xét thủ công có cấu trúc](../../evals/meal_manual_review_2026-11-07.json)',
        '- [Kết quả trước sửa](baseline/answers.md) · [Sau lượt sửa chính](after-fixes/answers.md) · [9 câu kiểm tra cuối](final-targeted/answers.md)',
        '- [Tổng hợp số liệu](summary.json) · [Kiểm tra tự động](offline-tests.txt) · [Kiểm tra giao diện](ui-check.json)', '',
    ])
    (DIRECTORY / '50_QUESTIONS_BEFORE_AFTER.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
