# Sửa hội thoại về lượng món ăn

- Sửa câu hỏi nối tiếp “tôi ăn bao nhiêu thì ổn”, “ăn mấy tô thì được”, giữ chủ thể món đang hỏi.
- Giữ chủ đề cả khi khôi phục lịch sử đã lưu; nhận câu trả lời cỡ phần ăn như “tô nhỏ, ăn hết”.
- Không dùng tỷ lệ diện tích đĩa để thay số tô/bát/gram; chặn việc tự suy chia đôi tô khi nguồn chỉ nói chia phần.
- Chọn đúng vế ăn/uống từ nguồn chung, bỏ ngôn ngữ truy xuất khỏi câu trả lời và ưu tiên câu ngắn.
- Thêm clarification_question vào API và hiển thị trong giao diện. Đây là câu hỏi làm rõ phần ăn, không phải số liệu y khoa hay lời kê khẩu phần. Không hỏi lặp thông tin phần ăn đã có.

Kiểm tra: 141 test liên quan đạt; Ruff và cú pháp JavaScript đạt. Sau chỉnh câu chữ cuối, thử lại đúng hội thoại 2 lượt bằng Gemini thật; cả hai HTTP 200, câu hỏi tiếp nhắc phở và có câu hỏi cỡ tô riêng. Tổng đợt kiểm model chỉ lặp cùng hội thoại đại diện 3 lần (6 lượt chat), không có AI judge. Dữ liệu dinh dưỡng và index không đổi.

Bằng chứng cuối: portion-dialogue.json, portion-dialogue-tests.xml. Câu hỏi cỡ tô hỗ trợ làm rõ phần ăn; không bảo đảm cỡ tô đủ để xác định lượng ăn cá nhân. Các số liệu món đang chờ xác minh vẫn bị chặn.
