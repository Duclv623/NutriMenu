# Định tuyến câu trả lời NutriGuide — 31/10/2026

Bản trước thay đổi đã được lưu và đẩy lên nhánh `chatbot-service` tại commit `12cdb73`.

## Hành vi mới

Trước khi truy xuất kiến thức, model xác định kết quả người dùng cần: giải thích, thao tác thực hành, lịch ăn, quyết định, so sánh hoặc đối chiếu nguồn. Kết quả này dùng để chọn cách trả lời, không phải bằng chứng chuyên môn.

| Nhánh | Phạm vi |
| --- | --- |
| `direct_llm` | Giải thích khái niệm dinh dưỡng phổ thông, hỗ trợ thói quen và chuẩn bị đồ ăn. Không tìm tài liệu, không embedding, không tạo citation. Có kiểm tra độc lập về phạm vi và độ đúng trọng tâm. |
| `practical_rag` | Chuyển nguyên tắc có nguồn thành hướng dẫn thực hành theo tình huống. Bước sinh và kiểm đều nhận mục tiêu câu trả lời, thay vì chỉ kiểm có chung chủ đề. |
| `evidence_rag` | Câu hỏi yêu cầu nguồn, số liệu, khuyến cáo hoặc tác động sức khỏe cần căn cứ. Giữ đối chiếu từng nhận định với tài liệu. |
| `structured_lookup` | Các số liệu thực phẩm/nhãn vẫn đi qua kho dữ liệu và kiểm tra đơn vị hiện có. |
| `safety` | Thuốc, cấp cứu và đối tượng ngoài phạm vi được xử lý trước bước phân loại; không cần API để giữ ranh giới này. |

Câu hỏi lịch ăn thiếu mốc quan trọng trả `status=needs_clarification`, kèm một câu hỏi về giờ làm và giờ ngủ. Chatbot không truy xuất rồi lấp phần thiếu bằng nhiều đoạn kiến thức chung. Câu trả lời tiếp chứa giờ được giữ cùng chủ đề, cả trong ngữ cảnh tạm và lịch sử đã lưu.

Với câu hỏi diễn đạt lại phần giải thích phổ thông trước, ngữ cảnh tạm giữ tối đa 3.000 ký tự mỗi câu trả lời. Chỉ nội dung nhánh trực tiếp trước đó được chuyển vào phần tham chiếu để diễn đạt lại; nội dung này không được coi là nguồn chứng minh y khoa. Lựa chọn lưu lịch sử của người dùng vẫn được giữ nguyên.

## Ràng buộc

- Model phân loại không được bỏ qua yêu cầu nguồn/số liệu hoặc ranh giới an toàn của server.
- Nhánh trực tiếp không được tự đưa mục tiêu kcal/carb/gram/ml, lịch ăn điều trị, thuốc hoặc nhận định tác động đường huyết. Bản nháp không vượt kiểm tra được chuyển sang đối chiếu nguồn, không được phục vụ trực tiếp.
- Truy xuất thất bại không tự kích hoạt nhánh trả lời tự do.
- Nhánh thực hành được chuyển nguyên tắc thành thao tác, nhưng không tự tạo số liệu, giờ ăn điều trị hoặc kết luận cá nhân chưa có căn cứ.
- Dữ liệu hiện có chưa đủ để kê một lịch ăn cá nhân cho mọi ca đêm. Hỏi được giờ làm/giờ ngủ chưa đồng nghĩa chatbot có thể chốt giờ ăn hoặc điều chỉnh thuốc. Đây vẫn là giới hạn của câu trả lời thực hành sau khi có các mốc giờ.
- Kiểm tra bằng một model khác/lượt gọi khác không bảo đảm mọi khẳng định phổ thông đều đúng; nhãn giao diện phân biệt rõ câu trả lời có và không có nguồn truy xuất.

## API và quan sát

`ChatResponse.response_strategy` cho biết nhánh đã thực sự trả lời. `needs_clarification` là trạng thái bổ sung, HTTP vẫn là 200; câu hỏi nằm ở `clarification_question`. `/api/status` bổ sung `adaptive_response_routing=true`. Log ghi nhánh xử lý, trạng thái và thời gian, không ghi nội dung hội thoại.

Bước phân loại thêm một lượt gọi model cho câu hỏi kiến thức. Thời gian thực tế còn phụ thuộc giới hạn tốc độ API và việc cần sửa bản nháp. Lời chào, tra cứu số liệu có cấu trúc và ranh giới an toàn giữ đường xử lý riêng.

## Kiểm tra

- Bộ kiểm tra tự động: 346 bài qua, 3 bài gọi API thật được loại khỏi lượt chạy này; xem `tests-full.xml`. Sau bổ sung kiểm tra tỷ lệ phần trăm và quyết định ăn món, toàn bộ 27 bài định tuyến qua; xem `tests-routing.xml`.
- Tám tình huống API thật trên bản sao chỉ mục hybrid: xem `adaptive-routing-live.json`. Bao gồm hỗ trợ thói quen, giải thích khái niệm, ăn phở, ca đêm thiếu giờ, trả lời giờ ca/giờ ngủ, yêu cầu đúng nguồn, tra số liệu và giới hạn thuốc. Kết quả chứa câu trả lời, nhánh, token, ID API và biên bản kiểm nguồn; không phải chứng nhận lâm sàng.
- Chạy lại kiểm tra thật: `python -X utf8 -m scripts.check_adaptive_routing` (sử dụng API đã cấu hình).
- Máy chủ đang chạy đã được khởi động lại và kiểm tra trực tiếp hai trường hợp hỗ trợ thói quen / hỏi giờ ca đêm; xem `server-smoke.json`.

Bản hiện tại vẫn giữ các giới hạn của kho thực phẩm và việc chưa tích hợp dịch vụ sinh thực đơn.
