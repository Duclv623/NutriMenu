"""Save selected CDC sections transcribed from rendered browser pages on 2026-10-08.

These are excerpts and Vietnamese digests, not downloaded full HTML documents.
"""

import hashlib
import json
from datetime import UTC, datetime

from scripts.collect_rag_supplements import DEST, SOURCES

CONTENTS = {
    "cdc-carb-counting": [
        (
            "How are carbs measured?",
            "For diabetes meal planning, 1 carb serving is about 15 grams of carbs. This isn't always the same as what you think of as a serving of food.",
            "Carbohydrate được tính bằng gram. Một đơn vị carb trong lập kế hoạch bữa ăn thường khoảng 15 g carbohydrate; đây không phải 15 g khối lượng thực phẩm. Đọc tổng carbohydrate trên nhãn và nhân theo lượng thực tế ăn. Lượng carb phù hợp mỗi ngày tùy tuổi, cân nặng, mức vận động và điều trị; thực đơn mẫu 1.800 kcal/200 g carb trong bài không phải mức mặc định cho người dùng.",
        ),
        (
            "What are the different kinds of carbs?",
            "There are 3 types of carbs.",
            "Carb gồm đường, tinh bột và chất xơ. Đường có thể có sẵn trong trái cây/sữa hoặc được bổ sung. Tinh bột có trong ngũ cốc, rau củ giàu tinh bột và các loại đậu. Không chỉ nhìn dòng đường rồi coi đó là toàn bộ carbohydrate.",
        ),
    ],
    "cdc-carb-choices": [
        (
            "Starches / Fruits / Milk and milk substitutes / Non-starchy vegetables",
            "1 carbohydrate choice = 12 grams carbohydrate",
            "Giữ đúng cơ sở từng nhóm trong bảng: nhóm tinh bột và trái cây khoảng 15 g carb cho lượng thực phẩm ghi ở mỗi dòng; nhóm sữa 12 g; rau không nhiều tinh bột 5 g. Các nhóm đồ ngọt, món phối hợp và thức ăn nhanh còn có tiểu nhóm 15/30/45 g. Bảng gốc tái bản từ ADA năm 2014. Không lấy “cup” của bảng làm một bát Việt cố định. Ngũ cốc, mì và rau củ nhiều tinh bột ghi lượng đã nấu; riêng cân nặng trái cây trong bảng gồm vỏ, lõi, hạt. Sữa chua có thể khác đáng kể giữa sản phẩm, ưu tiên nhãn thực tế.",
        ),
    ],
    "cdc-meal-planning": [
        (
            "The plate method",
            "Fill half with nonstarchy veggies, such as salad, green beans, and broccoli.",
            "Dùng đĩa đường kính khoảng 9 inch: một nửa rau không chứa nhiều tinh bột, một phần tư nguồn đạm nạc, một phần tư nhóm thực phẩm chứa carbohydrate. Chọn nước hoặc đồ uống không đường phù hợp. Phương pháp chia diện tích đĩa giúp cân đối nhóm thực phẩm; không xác định sẵn gram cơm hay lượng carb chính xác cho từng người.",
        ),
        (
            "About portion size",
            "Portion size and serving size aren't always the same.",
            "Khẩu phần thực tế là lượng bạn chọn ăn; đơn vị phục vụ trên nhãn/tài liệu là lượng quy định dùng để công bố số liệu. Có thể chia món ăn ngoài, để riêng phần mang về và đong đồ ăn nhẹ thay vì ăn trực tiếp từ cả túi. Ước lượng bằng bàn tay chỉ là hướng dẫn gần đúng, không phải phép cân đã xác minh cho mọi người.",
        ),
    ],
    "cdc-eating-out": [
        (
            "Order wisely",
            "Order sauces, salad dressing, and spreads on the side and use just enough for flavor.",
            "Xem thực đơn trước khi đi. Chọn món hấp, nướng hoặc đút lò; hạn chế món chiên, tẩm bột, sốt kem. Gọi thêm rau thay cho món ăn kèm nhiều năng lượng; yêu cầu để riêng nước sốt và dùng lượng vừa đủ. Chia món hoặc mang một phần về nếu suất lớn. Nếu muốn ăn tráng miệng, tính phần carb đó trong bữa thay vì thêm không giới hạn.",
        ),
        (
            "Plan ahead",
            "If your meal will be later than normal, have a snack before you go out to avoid getting too hungry.",
            "Khi bữa ăn bị trễ, bài gợi ý cân nhắc phần ăn nhẹ có đạm/chất xơ để tránh quá đói, rồi tính phần đó vào tổng lượng ăn. Đây không phải yêu cầu mọi bệnh nhân đều phải có bữa phụ; lịch ăn còn phụ thuộc thuốc và kế hoạch cá nhân.",
        ),
    ],
    "cdc-dessert": [
        (
            "Diabetes-friendly dessert tips",
            "When you do enjoy desserts or sweets, do it in moderation.",
            "Có thể bố trí món tráng miệng với lượng vừa phải trong kế hoạch ăn. Tính carbohydrate của món đó vào tổng bữa/ngày, ăn chậm và chọn phần nhỏ. Đồ ngọt có thể chứa carb từ đường, bột và sữa. Trái cây, chuối nghiền hoặc táo nghiền dùng thay chất tạo ngọt vẫn chứa đường/carb; không phải lựa chọn ăn không giới hạn.",
        ),
    ],
    "cdc-holidays": [
        (
            "Holiday-proof your plan / Outsmart the buffet",
            "Don't skip meals to save up for a feast. When you're really hungry you might be more likely to overeat.",
            "Giữ giờ ăn gần lịch thường lệ khi có thể, không bỏ bữa để dồn ăn tiệc. Tính trước phần carb, chọn lượng món thích ăn trong giới hạn kế hoạch và có thể mang phần còn lại về. Khi ăn buffet, dành ít nhất nửa đĩa cho rau và ăn chậm. Có thể mang theo một món phù hợp; người tổ chức nên để riêng nước sốt và các phần thêm. Bài cũng nhắc hạn chế rượu và theo dõi đường huyết theo kế hoạch điều trị.",
        ),
    ],
    "cdc-hypoglycemia": [
        (
            "The 15-15 rule / Foods to treat low blood sugar / Treating severely low blood sugar",
            "Have 15 grams of carbs, then wait 15 minutes.",
            "Tài liệu tham chiếu an toàn, chưa bật thành hướng dẫn xử trí của chatbot. CDC mô tả đường huyết dưới 70 mg/dL là thấp; dùng 15 g carbohydrate tác dụng nhanh, chờ 15 phút, đo lại và lặp nếu vẫn dưới ngưỡng. Nguồn phân biệt tình trạng nặng có thể không tự xử trí được và cần hỗ trợ y tế; chỉ cho ăn/uống khi tỉnh và nuốt được. Không sử dụng đoạn ngắn này độc lập để thiết kế nhánh cấp cứu. Phải đọc toàn bộ CDC và NIDDK, kiểm tra mức nặng/triệu chứng/khả năng nuốt/nhóm trẻ em trước khi triển khai. Không tự thay thuốc hoặc liều insulin.",
        ),
    ],
    "cdc-shift-work": [
        (
            "Lifestyle tips for shift workers / Eating Habits / Medication Schedule",
            "Prepping your food ahead is a great way to set yourself up for success and have healthy options at any hour.",
            "Chuẩn bị đồ ăn trước ca, cố gắng giữ thời điểm ăn ổn định và tránh bữa rất lớn giữa đêm. Theo dõi đường huyết phù hợp với ca và mức hoạt động. “Đo buổi sáng” không tự đồng nghĩa “đo lúc đói” nếu vừa ăn khi làm ca đêm. Trao đổi với bác sĩ về lịch dùng thuốc và những thuốc cần dùng cùng thức ăn; chatbot không tự dời liều. Lịch ngủ và ăn cần phù hợp ca thực tế, không áp một giờ biểu cố định cho mọi người.",
        ),
    ],
}


def main():
    sources = {s[0]: s for s in SOURCES}
    sources["cdc-shift-work"] = (
        "cdc-shift-work",
        "CDC — Diabetes and Shift Work",
        "en",
        "scenarios",
        "https://www.cdc.gov/diabetes/articles/diabetes-shift-work.html",
    )
    for sid, sections in CONTENTS.items():
        source = sources[sid]
        original = [
            {"source_section": section, "selected_original_excerpt": text}
            for section, text, _ in sections
        ]
        raw_path = f"raw/{sid}.selected-excerpts.en.json"
        raw = (json.dumps(original, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        (DEST / raw_path).write_bytes(raw)
        path = f"reviewed/{sid}.vi.md"
        body = f"# {source[1]} — nội dung chọn lọc tiếng Việt\n\nNguồn: {source[-1]}\n\nĐọc qua trình duyệt ngày 08/10/2026. Đây là bản tóm lược các mục chọn lọc, không phải bản dịch đầy đủ hoặc HTML gốc. Chưa index; chưa thẩm định lâm sàng.\n"
        for section, _, text in sections:
            body += f"\n## {section}\n\n{text}\n"
        (DEST / path).write_text(body, encoding="utf-8")
        entry = {
            "id": sid,
            "title": source[1],
            "language": "en",
            "prepared_language": "vi",
            "topic": source[3],
            "url": source[-1],
            "final_url": source[-1],
            "retrieved_at": datetime.now(UTC).isoformat(),
            "raw_file": raw_path,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "extracted_file": path,
            "extracted_sha256": hashlib.sha256((DEST / path).read_bytes()).hexdigest(),
            "acquisition_method": "browser_dom_read_selected_transcription_and_vietnamese_digest",
            "full_document_saved": False,
            "direct_download_issue": "HTTP 403",
            "status": "curated_excerpt_pending_integration",
            "rag_enabled": False,
            "clinical_review": False,
            "translation_method": "assistant_summary_with_original_section_locator",
        }
        (DEST / "entries" / f"{sid}.json").write_text(
            json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print("Saved 8 CDC selected-section digests with provenance.")


if __name__ == "__main__":
    main()
