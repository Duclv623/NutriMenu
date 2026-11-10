# NutriGuide — Chatbot dinh dưỡng RAG

Chatbot giáo dục dinh dưỡng tiếng Việt cho người trưởng thành mắc đái tháo đường típ 2. Backend FastAPI phục vụ luôn giao diện web; không cần chạy Node.js cho giao diện này.

Ứng dụng tìm tài liệu bằng BM25 kết hợp embedding Gemini, tạo câu trả lời và kiểm chứng theo nguồn. Có tra cứu thành phần thực phẩm và giao diện hồ sơ/thực đơn mẫu để demo hỏi đáp.

## 1. Yêu cầu

- Git và Python **3.12** (phiên bản đã dùng để kiểm tra dự án).
- Gemini API key còn quyền sử dụng các model cấu hình trong `.env`.
- Internet khi cài thư viện, tải tokenizer lần đầu, tạo embedding và hỏi kiến thức qua Gemini.

Các lệnh bên dưới dành cho **PowerShell trên Windows**, chạy tại thư mục dự án.

## 2. Lấy code và cài thư viện

```powershell
git clone --branch chatbot-service --single-branch https://github.com/Duclv623/NutriMenu.git
cd NutriMenu
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Nếu đã có repo, chuyển sang nhánh `chatbot-service` và cập nhật code trước khi chạy. Chỉ sao chép `.env.example` khi chưa có `.env`, để giữ cấu hình và key đang dùng.

Không cần kích hoạt virtualenv: các lệnh gọi trực tiếp Python trong `.venv`.

### Dữ liệu nguồn cần nhận riêng

**Clone code chưa đủ để chạy đầy đủ ứng dụng.** Nhánh này không đóng gói toàn bộ dữ liệu nguồn thô. Trước khi tạo chỉ mục hoặc khởi động, nhận bộ thư mục `data/` đã được duyệt từ thành viên phụ trách chatbot và đặt đúng cấu trúc tại thư mục dự án. Không cần nhận `.env` hoặc `storage/` của người khác.

Các phần runtime cần đối chiếu gồm:

- Tài liệu và tệp gốc được tham chiếu trong `config/sources.json`.
- Bản thu thập nguồn bổ sung tại `data/collected/rag_supplements_2026-10-08/raw/`, theo `data/structured/supplements/manifest.json`.
- Bằng chứng hiệu chỉnh tại `data/collected/review_2026-10-30/nin_foods/records.json` và tệp `data/collected/review_2026-10-30/raw/ada-sitting.html`.
- Các bảng `data/structured/` đúng phiên bản/hash của manifest đi kèm.

Giữ nguyên từng byte của bản nguồn, kể cả dấu xuống dòng. Nếu thiếu tệp hoặc checksum không khớp, cần bổ sung đúng bộ dữ liệu trước; không bỏ kiểm tra hash hoặc tự thay bằng một bản tải web mới. Fixture nhỏ của giao diện demo có trong repo nhưng vẫn sử dụng kho thực phẩm nguồn để tính dinh dưỡng.

## 3. Cấu hình `.env`

Mở `.env` bằng trình soạn thảo, điền key vào `GEMINI_API_KEY`. Để hiện **hồ sơ và thực đơn mẫu ngay trên giao diện cổng 8000**, đặt:

```dotenv
APP_ENV=development
ANSWER_MODE=gemini
EMBEDDING_MODE=gemini
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GEMINI_MODEL=gemini-3.1-flash-lite
GEMINI_GROUNDING_MODEL=gemini-3.1-flash-lite
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
GEMINI_EMBEDDING_DIMENSIONS=768
MEAL_SERVICE_MODE=mock
MEAL_DEMO_DATASET=named
```

Thay chuỗi `YOUR_GEMINI_API_KEY` bằng key thật tại máy của bạn. Chọn model mà key có quyền sử dụng; khởi động lại backend sau khi đổi cấu hình. Đổi model hoặc số chiều embedding cần tạo lại chỉ mục; chỉ đổi model trả lời không yêu cầu vector hóa lại tài liệu.

`.env` được Git bỏ qua. Không đưa key vào frontend hoặc commit. Câu hỏi kiến thức, trích đoạn nguồn và thông tin hồ sơ liên quan có thể được gửi tới nhà cung cấp AI; dùng dữ liệu giả lập khi demo.

## 4. Tạo chỉ mục lần đầu

```powershell
.\.venv\Scripts\python.exe -X utf8 -m rag_app.cli ingest --mode hybrid
```

Bước này đọc nguồn được duyệt trong `config/sources.json`, chia tài liệu và gọi API tạo embedding. Thực hiện sau khi clone nếu chưa có chỉ mục. Có sử dụng hạn mức API; thời gian phụ thuộc mạng và nhà cung cấp.

Kết quả lưu tại `storage/rag.sqlite3`. Các tệp `storage/chunks.jsonl` và `storage/ingestion_report.json` giúp kiểm tra nội dung chỉ mục. Thư mục `storage/` không nằm trong Git và có thể chứa lịch sử chat, nên mỗi máy tạo chỉ mục riêng; không chia sẻ nguyên database đang sử dụng để bàn giao vector.

Không cần tạo lại chỉ mục mỗi lần chạy server. Cache giúp tái sử dụng embedding khi nội dung và cấu hình tương thích. Khi thêm/sửa nguồn được duyệt hoặc đổi cấu hình embedding, chạy lại lệnh trên.

## 5. Chạy ứng dụng

```powershell
.\.venv\Scripts\python.exe -X utf8 -m uvicorn rag_app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Mở **http://127.0.0.1:8000/** trên Chrome. Nhấn `Ctrl+C` tại cửa sổ chạy server để dừng.

Cũng có thể chạy:

```powershell
.\run.ps1
```

`run.ps1` kiểm tra chỉ mục và tự tạo lại khi thiếu hoặc không tương thích. Hoặc, sau khi đã có chỉ mục, chạy bản demo có món ăn bằng:

```powershell
.\run-meal-demo.ps1
```

Script demo mặc định dùng cổng **8000**, bật `mock` + `named` cho tiến trình và khôi phục biến môi trường khi dừng. Nếu máy chặn chạy `.ps1`, dùng lệnh Python trực tiếp ở trên và cấu hình `.env` theo mục 3.

## 6. Demo hồ sơ và thực đơn

Trên giao diện:

1. Xem khung **Thông tin người dùng mẫu** phía trên. Mở **Chỉnh thông tin / chọn người dùng mẫu** để chọn mẫu A/B/C hoặc sửa tuổi, chiều cao, cân nặng, dị ứng, sở thích.
2. Bấm **Lưu hồ sơ mẫu và mở chat mới** để chatbot dùng phiên bản hồ sơ vừa lưu.
3. Xem thực đơn với tên món, lượng gram, kcal và chi tiết nguồn. Có phở gà, cơm trắng, cơm gạo lứt, ức gà, rau muống luộc và chuối.
4. Bấm câu hỏi gợi ý dưới thực đơn hoặc nhập câu hỏi vào khung chat.

Câu hỏi để thử:

- “Bữa trưa của tôi có những món gì?”
- “Bữa trưa của tôi có bao nhiêu calo?”
- “Tổng dinh dưỡng cả ngày trong thực đơn của tôi.”
- “Tôi nặng bao nhiêu?”
- “Nước ngọt zero sugar thì uống bao nhiêu lon cũng được đúng không?”, sau đó hỏi tiếp “Vậy mỗi ngày uống mấy lon được?” trong cùng cuộc trò chuyện.

Mẫu `named` dùng lượng ăn cố định để minh họa, số dinh dưỡng tính từ bản ghi đã có trong kho. **Chưa tối ưu hoặc xác nhận khẩu phần phù hợp cá nhân; đổi hồ sơ không tự thay lượng ăn.** Mẫu này chưa hỗ trợ đổi món. Hồ sơ/thực đơn demo lưu tạm theo người dùng trong bộ nhớ, hết hạn hoặc khởi động lại server sẽ được tạo lại.

Để thử luồng xem trước/áp dụng đổi món bằng mẫu toán học A/B/C cũ, dùng `MEAL_DEMO_DATASET=mathematical`, hoặc chạy `.\run-meal-demo.ps1 -Port 8002 -Dataset mathematical`.

## 7. Tích hợp với backend nhóm

| Chế độ | Cấu hình | Hành vi |
|---|---|---|
| Hỏi đáp/tra cứu độc lập | `MEAL_SERVICE_MODE=disabled` | Không kết nối hồ sơ/thực đơn |
| Demo tại máy | `MEAL_SERVICE_MODE=mock` | Hồ sơ và thực đơn giả lập |
| Kết nối backend | `MEAL_SERVICE_MODE=http`, `MEAL_API_BASE_URL=...` | Đọc dữ liệu và thực hiện thao tác qua API nhóm |

Hợp đồng dữ liệu thực đơn nằm trong [`contracts/meal-service.schema.json`](contracts/meal-service.schema.json). Adapter HTTP nằm trong [`rag_app/meal_gateway.py`](rag_app/meal_gateway.py); nhóm cần thống nhất các endpoint và xác thực tương ứng. Không có cơ chế tự chuyển từ lỗi backend thật sang dữ liệu giả lập.

Tài khoản, hồ sơ và thực đơn thật thuộc backend nhóm. Hiện dịch vụ chatbot vẫn dùng SQLite cho chỉ mục/cache và lịch sử chat được chọn lưu; **chưa triển khai chuyển sang MySQL hoặc Chroma**. Cấu hình `http` không tự di chuyển database.

Khi dùng `APP_ENV=production`, cần `JWT_PUBLIC_KEY_PATH`, `JWT_ISSUER`, `JWT_AUDIENCE`; chế độ `mock` bị chặn. Backend hiện xác thực JWT RS256. Lịch sử chat mặc định không lưu lâu dài; khi bật lưu, có ràng buộc người dùng và thời hạn theo `HISTORY_RETENTION_DAYS`.

Các địa chỉ kiểm tra khi server đang chạy:

- `GET /health`: tình trạng tiến trình.
- `GET /api/status`: chỉ mục, model và trạng thái kết nối thực đơn.
- `GET /docs`: hướng dẫn API tại máy.
- `GET /openapi.json`: đặc tả API.
- `POST /api/chat`: hỏi chatbot.
- `GET /api/meal-context`: hồ sơ/thực đơn hiện tại theo người dùng.

## 8. Cấu trúc thư mục

```text
rag_app/       Backend, retrieval, provider, kiểm chứng, adapter thực đơn
web/           HTML/CSS/JavaScript giao diện
config/        Manifest nguồn được duyệt
data/          Tài liệu và số liệu nguồn cần cho ứng dụng
contracts/     Schema trao đổi dữ liệu thực đơn
tests/         Kiểm thử chức năng
storage/       Chỉ mục/cache/lịch sử tại máy, không commit
```

Các tệp bằng chứng nguồn được kiểm tra checksum theo manifest; phần cần nhận riêng được nêu tại mục 2. Không tự xóa các tệp đó: nguồn thiếu hoặc sai checksum có thể khiến ứng dụng không khởi động hoặc không tạo được chỉ mục. Không cần chạy các script thu thập dữ liệu nếu đã có đúng bộ dữ liệu bàn giao.

## 9. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| Không thấy hồ sơ/thực đơn mẫu | Kiểm tra `.env` có `mock` + `named`, khởi động lại backend, rồi tải lại trang bằng `Ctrl+F5` |
| Cổng 8000 đã được sử dụng | Mở trang xem server có đang chạy không; hoặc dùng `--port 8002` và mở đúng cổng |
| Chưa có index | Chạy lệnh `ingest --mode hybrid` ở mục 4 |
| Embedding model/dimension mismatch | Kiểm tra model/số chiều trong `.env`, rồi ingest hybrid lại |
| API báo 429 | Kiểm tra hạn mức/billing của key; không chạy lại liên tục |
| API không tìm thấy hoặc không cho dùng model | Chọn model key được cấp quyền, rồi khởi động lại |
| Thiếu file hoặc sai checksum nguồn | Kiểm tra đã lấy đủ các tệp `data/` của nhánh; không bỏ kiểm tra checksum để chạy tiếp |
| Không tìm thấy cuộc trò chuyện | Bấm **Cuộc trò chuyện mới** nếu phiên tạm đã hết hạn hoặc server vừa khởi động lại |

## 10. Kiểm tra chức năng tùy chọn

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:RUN_LIVE_TESTS = '0'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/test_named_demo.py tests/test_rag_optimization.py -p no:cacheprovider
```

Các ca trên dùng dữ liệu mẫu và provider giả lập; không gọi Gemini thật. Kết quả này kiểm tra chức năng, không chứng minh chất lượng hoặc độ chính xác y khoa của mọi câu trả lời. Chatbot chưa thay thế tư vấn bác sĩ/chuyên gia dinh dưỡng; chưa chạy bộ tối ưu CP-SAT thật trong bản demo.
