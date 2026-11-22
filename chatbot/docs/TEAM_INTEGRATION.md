# Tích hợp qua Gateway 8080

Từ đợt sửa lỗi hồ sơ ngày 21/11/2026, phần BFF đã chuyển sang `gateway/gateway_app`.
Chatbot không còn chứa `team_integration.py`, `team_store.py` hoặc các route lưu hồ sơ/sinh thực đơn của frontend.

Xem [hướng dẫn gateway](../../gateway/README.md) để chạy, chuyển dữ liệu và kiểm tra các yêu cầu trước deploy.

Frontend dùng `/api` cho nghiệp vụ và `/api/chatbot` cho RAG; tất cả qua cổng 8080.
Chatbot dùng `HttpMealGateway` đọc MealSnapshot từ API nội bộ và xác minh danh tính qua gateway bằng phiên + service key.
Các module RAG, provider, ingestion, citation, history, security, model và meal_chat vẫn cần giữ; chỉ giữ riêng meal_chat.py sẽ làm chatbot không chạy được.

Cấu hình chatbot:

```dotenv
MEAL_SERVICE_MODE=http
MEAL_API_BASE_URL=http://127.0.0.1:8080/api/internal/
GATEWAY_AUTH_URL=http://127.0.0.1:8080/api/internal/identity
GATEWAY_SERVICE_KEY=<key riêng dùng chung với gateway>
```

Không dùng VITE_* cho key nội bộ. Không tắt xác thực khi gateway mất kết nối. Lịch sử RAG vẫn dùng PostgreSQL và corpus vẫn dùng ChromaDB.

## Đổi món từ hội thoại (22/11/2026)

RAG nhận yêu cầu như "Tôi không muốn ăn cá buổi tối" và trả `meal_result.editor` gồm planId/baseVersion/itemIds/instruction và tùy chọn excludedTerms/preferredTerms/requestedServings. Đây là thẻ mở bảng chỉnh sửa, chưa phải phương án solver và không ghi dữ liệu.

Yêu cầu "đổi ức gà sang cá" khớp tên rút gọn của món gốc; preferredTerms giữ loại món thay thế để frontend lọc catalog. Khi có nhiều món cùng tên rút gọn, ưu tiên bữa vừa hỏi trong cùng thực đơn hoặc yêu cầu chọn rõ. Câu "đổi ức gà sáng cá" cần xác nhận món và bữa vì "sáng" có thể là lỗi gõ "sang". Bấm lựa chọn hoặc xác nhận món chỉ mở bảng chỉnh sửa và giữ yêu cầu ban đầu; chưa lưu thực đơn.

Frontend dùng chung MealChangeModal với trang Thực đơn: người dùng chọn món/khẩu phần, gọi gateway swap-preview, kiểm tra kết quả rồi xác nhận swap bằng chữ ký preview. Khi lưu thành công, frontend cập nhật Plan và hội thoại ngay, không reload toàn ứng dụng làm mất đoạn chat. RAG không làm BFF lưu hồ sơ/sinh thực đơn.

Tạo mới vẫn ở trang Thực đơn. Thêm/bớt cả bữa chưa hỗ trợ trong chat. Dị ứng mới cần cập nhật Hồ sơ; yêu cầu đó hủy các thẻ chỉnh sửa cũ trong hội thoại. Trả lời “đồng ý” không tự ghi một lựa chọn chưa được xem trước và xác nhận.
