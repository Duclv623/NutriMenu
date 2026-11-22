# NutriGuide — Chatbot RAG

Service FastAPI trả lời câu hỏi dinh dưỡng, đọc hồ sơ/thực đơn qua Gateway và lưu lịch sử hội thoại trong PostgreSQL. Corpus và embedding nằm trong ChromaDB. Giao diện dùng chung của nhóm ở `../frontend/`.

## Chạy bản tích hợp hiện tại

Từ `C:\testda`, chạy script trong terminal riêng:

```powershell
.\run-chatbot.ps1
```

Script này gọi `chatbot/run.ps1`. Cần có môi trường `.venv`, PostgreSQL, index Chroma và các service của nhóm đã cấu hình. Hướng dẫn đầy đủ cho Gateway/Java: [gateway/README.md](../gateway/README.md).

Chatbot hiện dùng API nội bộ của Gateway để đọc thực đơn và xác minh phiên đăng nhập:

```dotenv
MEAL_SERVICE_MODE=http
MEAL_API_BASE_URL=http://127.0.0.1:8080/api/internal/
GATEWAY_AUTH_URL=http://127.0.0.1:8080/api/internal/identity
```

Giữ API key, DSN PostgreSQL và `GATEWAY_SERVICE_KEY` trong cấu hình riêng của máy chạy. Gateway và chatbot phải dùng cùng service key. Không ghi đè `.env` hiện tại bằng bản mẫu. Khi dùng container, đổi URL sang DNS service phù hợp.

Frontend gọi `/api/chatbot` qua Gateway 8080. Không dùng launcher mock cho việc nghiệm thu thực đơn thật. Xem [docs/TEAM_INTEGRATION.md](docs/TEAM_INTEGRATION.md).

## Những phần cần giữ

- `rag_app/`: API, RAG, truy xuất dữ liệu, kiểm tra nguồn, provider, hội thoại và xác thực.
- `web/`: FastAPI vẫn phục vụ giao diện riêng, API docs và CSS cho trang xem nguồn trích dẫn.
- `config/`: manifest nguồn và dữ liệu tham chiếu đã kiểm tra.
- `data/`: tài liệu đang bật, bản nguồn gốc dùng kiểm tra checksum, bảng dữ liệu và đầu vào tái lập bộ dữ liệu.
- `storage/chroma/`: index/vector Chroma đang dùng.
- `storage/postgres-local/`: cluster PostgreSQL cục bộ nếu cấu hình sử dụng; không xóa từng file bên trong.
- `.venv`, `run.ps1`, `requirements*.txt`, `Dockerfile`, `compose.yaml`: môi trường/công cụ chạy theo từng phương án triển khai.

Muốn nạp lại corpus bằng launcher, dùng `run-chatbot.ps1 -Reindex` từ thư mục gốc. Việc này có thể gọi API embedding; chỉ thực hiện khi cần cập nhật nguồn/index.

## Phát triển và kiểm thử

Giữ `tests/`, `evals/`, `scripts/` và `contracts/` trong mã nguồn. Các nhóm này phục vụ kiểm thử, thu thập và kiểm tra dữ liệu, không chạy theo từng câu hỏi của người dùng.

Cài công cụ kiểm thử bằng `requirements-dev.txt`; công cụ trích xuất PDF offline bổ sung nằm trong `requirements-data.txt`. Test đầy đủ có những ca cần HTTP/PostgreSQL thử nghiệm; dùng database/schema kiểm thử riêng, không trỏ vào lịch sử thật. Các kiểm thử `live` có thể gọi API trả phí và cần chủ động chọn khi muốn chạy.

Các snapshot/raw/derived đang được manifest thu thập tham chiếu vẫn được giữ để hỗ trợ kiểm tra và dựng lại dữ liệu. Các script đọc kết quả đánh giá lịch sử cần khôi phục báo cáo tương ứng trước khi dùng lại; không chạy lại một script cũ chỉ để tạo lại thư mục báo cáo đã dọn.

## Báo cáo và dữ liệu cũ đã tách khỏi thư mục chạy

Đợt dọn ngày 22/11/2026 lưu báo cáo, file tạm, bản phát hành và dữ liệu cũ tại [cleanup-archive-20261122](../cleanup-archive-20261122/README.md). Có journal, kiểm tra checksum và script khôi phục không ghi đè file đang tồn tại.

Mã nghiệp vụ, cấu hình kết nối, nguồn tri thức đang dùng và database không bị sửa bởi đợt dọn này. Hướng dẫn cũ được giữ nguyên trong bản lưu trữ.