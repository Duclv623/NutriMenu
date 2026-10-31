# NutriGuide — Chatbot RAG của thành viên 3

> **Cập nhật triển khai 30/10/2026:** đã chặn phép tính 1.250 món NIN chờ xác minh cơ sở/đơn vị, sửa phân luồng và hội thoại, thu lại nguồn và bổ sung kiến thức ngắt thời gian ngồi. Dùng [ghi chú triển khai](RELEASE_NOTES_2026-10-30.md) để xem trạng thái và phần còn thiếu. Các số liệu/điểm kiểm tra ghi ngày cũ bên dưới là lịch sử. Gói bàn giao có checksum nằm trong `releases/NutriGuide-2026-10-30.zip`.

Ứng dụng FastAPI + giao diện web tiếng Việt, đọc PDF và DOCX đã duyệt, tìm kiếm hybrid BM25 + Gemini embedding, dùng Gemini tạo và kiểm câu trả lời có nguồn. Phần sinh thực đơn CP-SAT thuộc TV2 và chưa tích hợp.

**Hiện tại (11/10/2026):** index hybrid có **191 đoạn từ 31 nguồn được duyệt**, dùng Gemini embedding 768 chiều. Kho thực phẩm có **2.629 bản ghi**: 853 thực phẩm, 1.250 món ăn NIN và 526 thực phẩm PDF 2007. Kho bổ sung có **5.425 bản ghi**. Kiến thức dùng Gemini sinh và kiểm nguồn; thuốc, cấp cứu và đối tượng đặc biệt dùng thông báo cố định để hoạt động cả khi API lỗi. Tra cứu mơ hồ trả lựa chọn, hỏi khối lượng gram khi chưa quy đổi được. [Bản sửa và kiểm thử 11/10](docs/project-fix-2026-10-11/REPORT.md), [báo cáo kho bổ sung](docs/supplement-integration-2026-10-08/REPORT.md), [báo cáo kho thực phẩm](docs/food-integration/REPORT.md).

Kho `data/collected/rag_supplements_2026-10-08` và ZIP giữ nguyên bản chốt thu thập, nên các báo cáo/manifest trong đó vẫn ghi trạng thái **chưa triển khai tại thời điểm thu**. Trạng thái đang chạy được ghi riêng trong báo cáo triển khai và `data/structured/supplements/manifest.json`; không sửa lịch sử hoặc bật toàn bộ file gốc.

**Bản nâng cấp dữ liệu 08/10/2026:** bổ sung 4 PDF ADA về đọc nhãn, chất tạo ngọt, nhóm thực phẩm và chế biến (14 chunk mới); kiểm tra nguồn thay đổi trước khi khởi động, liên kết đoạn giải thích với điều kiện áp dụng và cache vector câu hỏi. Cấu hình máy hiện tại sinh/kiểm bằng `gemini-3.5-flash-lite`. Kết quả kiểm thử và giới hạn dữ liệu ở [báo cáo](docs/data-upgrade-2026-10-07/REPORT.md), [từng câu trả lời thật](docs/data-upgrade-2026-10-07/answers.md). Các lượt kiểm thử cũ bên dưới được giữ làm lịch sử, không phải điểm của bản hiện tại.

## Chạy ngay trên máy hiện tại

**Bổ sung 11/10:** sửa cách hỏi “tôi ăn phở buổi sáng được ko” và giữ chủ đề khi hỏi tiếp “nên ăn như thế nào”. [Bằng chứng trước/sau và cách tự thử](docs/pho-followup-2026-10-11/REPORT.md).

Đã có `.venv`, index hybrid **191 chunk từ 31 nguồn** và hai kho số liệu đã nối vào chat. Chạy trong PowerShell tại `C:\DATN`:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m uvicorn rag_app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Mở http://127.0.0.1:8000/ ; kiểm tra trạng thái tại http://127.0.0.1:8000/api/status . Nhấn Ctrl+C để dừng. Nếu báo port đã được dùng, có thể ứng dụng đang chạy; mở URL trước hoặc đổi `--port 8002`.

### Đặt key mới — không gửi vào chat

Nếu từng dán key vào chat, thu hồi key đó, tạo key mới. Copy `.env.example` thành `.env` bằng trình soạn thảo, chỉ thay dòng:

```dotenv
GEMINI_API_KEY=your_new_key_here
```

Không dùng chuỗi mẫu này làm key thật. File .env đã được gitignore và dockerignore. Không ghi key vào README, frontend, ảnh chụp, Git hoặc báo cáo. Không cần cung cấp key cho TV1/TV2 để họ dùng API chatbot.

Khởi động lại backend sau khi đổi `.env`. `ANSWER_MODE=gemini`, model mặc định `gemini-3.1-flash-lite`; đổi bằng `GEMINI_MODEL` và `GEMINI_GROUNDING_MODEL`. Giao diện thông báo câu hỏi kiến thức và trích đoạn liên quan gửi tới Gemini; chỉ tùy chọn lưu lịch sử. Ranh giới thuốc/cấp cứu/đối tượng đặc biệt không cần API. Lỗi API báo lỗi, không trả câu offline. Không nhập hồ sơ bệnh nhân thật. Có key chưa đồng nghĩa không có hạn mức. `GEMINI_REQUEST_INTERVAL=6.1` là tốc độ bổ sung lượt gọi; `GEMINI_BURST_REQUESTS=3` cho phép tối đa ba lượt liên tiếp khi còn tín dụng, thay vì bắt mỗi bước chờ 6,1 giây. Giới hạn được chia sẻ theo key/model trong một tiến trình, không phải quota toàn project trên nhiều máy. Không lưu lịch sử vẫn hỏi tiếp nối được: ngữ cảnh tạm giữ trong bộ nhớ tối đa 30 phút, ràng buộc người dùng; không ghi chat vào SQLite.

Có thể cấu hình thử gateway tương thích OpenAI Responses API qua `ANSWER_MODE=openai`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `GROUNDING_MODEL` và `OPENAI_API_KEY`; `EMBEDDING_MODE=gemini` vẫn dùng vector Gemini hiện có. Gateway TokenHarbor với model `deepseek-v4.1-flash:free` đã xác thực key và trả lời câu thử đơn giản, nhưng nhiều lượt chat thực tế trả JSON sai schema khiến ứng dụng báo 503. Vì vậy cấu hình chạy mặc định hiện giữ Gemini. `mode=openai` trong API chỉ tên adapter tương thích, không xác nhận nhà cung cấp thực tế; xem `model` trong phản hồi.

Bản sửa trọng tâm/tốc độ 06/10/2026: xem [báo cáo và đáp án thật](docs/chat-quality/REPORT.md). Kiểm tra logic và chuỗi câu hỏi từ đoạn chat được ghi riêng, không thay thế kết quả đánh giá 250 câu lịch sử bên dưới.

### Bật tìm kiếm hybrid

```powershell
.\.venv\Scripts\python.exe -X utf8 -m rag_app.cli ingest --mode hybrid
```

Lệnh này gửi title/section/chunk tài liệu lên Gemini embedding. Cache theo nội dung + provider/model/số chiều/prefix; lần sau chỉ tính phần chưa cache. Câu hỏi cũng cần embedding khi chạy hybrid. Thất bại không thay index đang hoạt động. Khi đổi `GEMINI_EMBEDDING_MODEL` hoặc số chiều, cần ingest hybrid lại; không trộn vector giữa các model.

### Chạy mặc định bằng API thật

```powershell
.\run.ps1
```

Script kiểm tra index hybrid, fingerprint manifest/file nguồn/cấu hình chunk và danh tính embedding; tạo lại nếu chưa phù hợp. Thiếu file hoặc sai hash nguồn được báo rõ, không lặng lẽ bỏ qua. Đã bỏ tham số `-Offline` và chế độ `extractive`. Kiến thức và xã giao sinh/kiểm qua API thật. Ranh giới y tế và yêu cầu làm rõ tra cứu có thể trả thông báo theo quy tắc, được ghi `answer_origin=static`. Tác vụ tìm nguồn lexical dùng để đo baseline.

## Cài ở máy khác

Python 3.12 trở lên (môi trường đã kiểm thử là Python 3.12 trên Windows):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -X utf8 -m rag_app.cli ingest --mode hybrid
.\.venv\Scripts\python.exe -X utf8 -m uvicorn rag_app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Tokenizer cần tải bảng mã công khai một lần đầu (không cần API key). Nếu chính sách PowerShell chặn `.ps1`, dùng trực tiếp các lệnh Python, không cần tắt bảo vệ hệ thống.

## Chức năng đã triển khai

- Manifest whitelist nguồn: không tự index tất cả PDF trong data; khóa SHA256, số trang, mốc đầu/cuối mục.
- Làm sạch text, chia theo mục + token/overlap với biên câu/dòng/từ; giữ trang PDF hoặc vị trí đoạn/bảng DOCX. Bảng DOCX được đọc riêng từng cột ngày, không trộn khẩu phần giữa ngày.
- BM25 với chuẩn hóa tiếng Việt; dense cosine; hybrid RRF; cache embedding, cập nhật index atomic.
- Gemini generateContent với JSON Schema, `store=False`; server kiểm tra ID nguồn từng block. Adapter OpenAI vẫn có cho backend API thật khác, không có lựa chọn provider trên UI.
- Từ chối khi chưa có bằng chứng hoặc lỗi nguồn; không biến lỗi/quota thành câu trả lời giả.
- Thuốc/cấp cứu/đối tượng đặc biệt trả thông báo an toàn cố định, không cần key/API. Giới hạn đối tượng đặc biệt giữ trong phiên cho tới khi tạo cuộc trò chuyện mới. Số liệu thực phẩm đã nối kho local; tạo thực đơn vẫn cần tích hợp TV2.
- Giao diện chat, đoạn trích, link PDF đúng trang hoặc bản xem DOCX đúng đoạn, nguồn tạo câu trả lời, model/token/latency.
- Lịch sử mặc định không lưu; opt-in, xóa từng cuộc trò chuyện, phản hồi câu trả lời, TTL mặc định 7 ngày.
- Development cookie ẩn danh; production yêu cầu JWT RS256 có exp/iat/sub/iss/aud; rate limit owner/IP; chống cross-origin request; không dùng HTML do LLM sinh để render.
- API docs local không phụ thuộc CDN, OpenAPI tại `/openapi.json`.

## Những điều chưa được xác minh / chưa triển khai

- OpenAI thật đã được kiểm tra sau khi cấu hình key; kết quả và các lỗi đã sửa nằm trong `docs/LIVE_TEST_REPORT.md`. Test mock KHÔNG chứng minh chất lượng câu trả lời thật; bộ câu hỏi hiện tại chưa có thẩm định độc lập.
- Chưa nối API TV1/TV2; chưa tạo/đổi thực đơn thật hoặc xác minh hồ sơ người dùng. Tra thành phần và quy đổi g/kg từ kho local đã có.
- Corpus có 191 chunk từ 31 nguồn; chi tiết tại `/api/documents` và `storage/ingestion_report.json`. Nguồn cũ và bản dịch vẫn cần chuyên gia rà soát.
- Kiểm tra citation ID không bảo đảm tất cả các mệnh đề được nguồn chứng minh. Hallucination, prompt injection và phân loại ý định bằng rule vẫn có thể sai.
- Chưa có OCR tự động, PDF table parser cho TV2, multilingual neural reranker, Qdrant hoặc đánh giá bởi chuyên gia. Không index bảng FCT thành chunk văn bản để thay thế số liệu thật.
- SQLite + cosine exhaustive hợp corpus nhỏ; chưa đo tải lớn. Rate limiter in-memory chỉ phù hợp 1 worker; production nhiều worker cần Redis/gateway limiter.
- Giao diện độc lập hiện phục vụ development. Frontend nhóm cần gửi JWT qua gateway khi bật production. JWT public key phải là RS256 của TV1; nếu TV1 chọn kiểu khác, cần thống nhất rồi sửa adapter.
- Lịch sử lưu SQLite chưa mã hóa ở cấp ứng dụng; purge là xóa logic/secure_delete, không hứa xóa mọi bản sao trong backup/WAL/cloud. Production cần chính sách dữ liệu, TLS, mã hóa lưu trữ, backup/retention và đồng ý người dùng.
- Docker chưa được build/run trên máy hiện tại nếu không có Docker. File cấu hình có sẵn không đồng nghĩa đã kiểm thử container.

## Thêm tài liệu đúng cách

1. Giữ PDF hoặc DOCX gốc trong `data`; PDF có lớp text không cần đổi DOCX. Với bài web, lưu URL/ngày và bản thu thập; không tự index nội dung trực tiếp từ các liên kết trong DOCX.
2. Đọc/rà soát nguồn, chọn đúng đối tượng và phần kiến thức. Không tự gán tài liệu cũ là mới nhất.
3. Thêm nguồn trong `config/sources.json`: ID, filename, format, title, URL, year/version, SHA256. PDF có segments/pages/mốc regex; DOCX có body_ranges, headings, text_corrections đã đối chiếu. Ảnh không được OCR tự động.
4. Không bật `enabled` cho bảng món/ingredient hoặc nội dung thuốc. Bảng khó đọc phải duyệt/chuyển cấu trúc trước, không cho parser suy đoán.
5. Kiểm tra `storage/chunks.jsonl` và `storage/ingestion_report.json`, nguồn/vị trí/bảng và phần bị loại, rồi ingest hybrid. Bộ `evals/expanded_questions.json` đã khóa SHA256 trước chạy; bổ sung bộ mới có phiên bản riêng thay vì sửa đáp án để khớp kết quả.

PDF 2879 trong data là bản cắt 6 trang: PDF trang 4 tương ứng trang gốc 14, không dùng “14” làm index trang của file 6 trang. FCT 2007 có font cũ, giá trị thiếu không phải 0, Celluloza không tự động là tổng chất xơ.

## Kiểm thử và đánh giá

Bộ mở rộng có **250 câu**, gồm 200 câu phát triển và 50 câu giữ lại cho đánh giá cuối: kiến thức, cách hỏi biến thể, hội thoại/mơ hồ, an toàn, số liệu/thực đơn, xã giao/vu vơ, tin sai/chỉ thị gây nhiễu. Xem `docs/CHAT_CHECK_250.md` để copy câu hỏi và đọc tiêu chí từng câu.

Chạy API thật và chấm từng câu (có phí):

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.run_expanded_eval --split dev --output docs/eval_expanded/new_dev_run --workers 2
.\.venv\Scripts\python.exe -X utf8 -m scripts.run_expanded_eval --split holdout --output docs/eval_expanded/new_holdout_run --workers 2
```

Mỗi thư mục có `results.jsonl` (câu hỏi/trả lời/nguồn/lượt API/grade), `answers.md`, `summary.json` và `run.json` ghi checksum dữ liệu/code/index/model. Dùng thư mục mới cho mỗi bản sửa; `--resume` chỉ tiếp tục cùng phiên bản. `--ids K001,C001` chạy nhóm cụ thể; `--repeat 2` đo độ ổn định. Runner dùng provider đang cấu hình; hiện tại sinh/kiểm nguồn/judge riêng bằng Gemini. Kết quả OpenAI cũ giữ để đối chiếu và không dùng làm điểm của Gemini. Judge vẫn có thể sai và có thể sai tương quan với critic. Sau đọc lỗi/sửa, 50 câu holdout cũ là hồi quy.

**Trạng thái 06/10/2026:** 124 test logic đạt. Lượt 250 câu chạy đủ gần nhất đạt 227/250 **trước các sửa cuối**. Lượt xác nhận mới ghi 71 hàng: 18 đạt, 53 lỗi API/thực thi, còn 179 chưa chạy vì OpenAI HTTP 429 `insufficient_quota`. Chưa nghiệm thu code hiện tại. Xem [báo cáo](docs/EXPANDED_RAG_REPORT.md), [từng đáp án snapshot](docs/eval_expanded/final/answers.md) và [20 câu mới chưa chạy](docs/CHAT_CHECK_SUPPLEMENTAL_20.md). Lỗi quota cần khôi phục khả năng sử dụng API, không retry liên tục; runner tự dừng hàng chờ khi xác định quota và không gọi judge nếu chat lỗi.

Sau khi API hoạt động lại, dùng thư mục **mới** cho code hiện tại; không bypass checksum để tiếp tục lượt cũ:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.run_expanded_eval --split all --output docs/eval_expanded/after_quota_regression --workers 1
.\.venv\Scripts\python.exe -X utf8 -m scripts.run_expanded_eval --dataset evals/supplemental_questions.json --split all --output docs/eval_expanded/after_quota_new20 --workers 1
.\.venv\Scripts\python.exe -X utf8 -m scripts.run_expanded_eval --ids K008,K011,K017,K024,K028,K035,K042,K053,K061,K068,K076,K079,K083,K093,K100,L007,L011,L024,L025,C002,C004,C008,C011,C018,S001,S006,S011,S019,A013,A020 --repeat 2 --output docs/eval_expanded/after_quota_stability --workers 1
```

Các bộ CSV trong `data/structured` đã nối qua `rag_app/food_data.py`. PDF FCT 2007 được trích theo tọa độ cột và font TCVN3: đủ 567 trang, 526 thực phẩm, 45.762 dòng thành phần; 41 trang hướng dẫn/danh mục vào RAG. Dữ liệu bảng trả qua công cụ có nguồn và link trang PDF. Cả 853 thực phẩm và 1.250 món ăn NIN đều theo 100 g, theo xác nhận của người thu thập ngày 08/10/2026; loader kiểm tra cơ sở này ở bảng core và từng dòng dinh dưỡng. Quy đổi g/kg bằng giá trị nguồn × gram/100; bát/hộp/ml cần dữ liệu quy đổi riêng. Thiếu giá trị được giữ là null, khác biệt nguồn được giữ riêng. ADA Standards 2026 và các nguồn khác chưa bật vẫn theo lý do trong manifest; thu thập đủ dữ liệu không bảo đảm bao phủ mọi câu hỏi y khoa.

[Danh sách tài liệu bổ sung và link tải đã kiểm tra](docs/DANH_SACH_TAI_LIEU_BO_SUNG_RAG_2026-10-08.md).

Để tái trích PDF (không cần làm mỗi lần chạy server): cài `requirements-data.txt`, chạy `python -m scripts.extract_fct2007`, rồi `python -m rag_app.cli ingest --mode hybrid`. Trích xuất chạy tại máy; bước hybrid dùng key Gemini để tạo embedding. Xuất CSV của PDF tại `data/structured/fct2007/foods_core.csv` và `nutrients_long.csv`; kiểm kê/checksum trong `quality_report.json`.

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m "not live" --cov=rag_app --cov-report=term-missing
.\.venv\Scripts\python.exe -m ruff check rag_app tests
.\.venv\Scripts\python.exe -X utf8 -m rag_app.evaluate --mode lexical
```

Đánh giá lexical: 20 câu tìm nguồn + phân loại 40 câu, lưu JSON trong docs. Hit@K là tỷ lệ câu tìm được ít nhất một chunk của mục gold trong K kết quả; MRR@5 đo hạng mục gold đầu tiên. Không gọi đây là “độ chính xác y khoa 100%”. Bộ câu hỏi chưa có thẩm định độc lập, có nguy cơ quá khớp; cần tập test mới tách biệt.

Sau khi có index hybrid, có thể chạy ablation:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m rag_app.evaluate --mode dense --output docs/evaluation_dense.json
.\.venv\Scripts\python.exe -X utf8 -m rag_app.evaluate --mode hybrid --output docs/evaluation_hybrid.json
```

Kiểm thử thật có phí, chỉ dùng key mới và câu hỏi thử không chứa thông tin cá nhân:

```powershell
$env:RUN_LIVE_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest -q -m live
```

Test thật kiểm tra embedding, câu trái cây có nguồn trang 33, và từ chối câu hỏi Java; chưa thay thế đánh giá y khoa toàn bộ. Không có key hoặc API thất bại phải báo lỗi, không được ghi thành pass.

Bộ `tests/test_live_quality.py` kiểm tra thêm 45 tình huống qua API thật trên bản sao index hybrid, không sửa lịch sử/index đang dùng. Kết quả từng câu, câu trả lời, nguồn, token và ID phản hồi API được lưu tại `docs/live-quality-results.json`. Test `tests/test_live_server.py` chỉ chạy khi có `LIVE_SERVER_URL=http://127.0.0.1:8000` và server đang chạy.

Giao diện hiển thị nguồn tạo câu trả lời, model sinh/kiểm nguồn và token. `answer_origin` phân biệt nội dung AI, thông báo theo quy tắc, trích đoạn và provider tùy chỉnh; chỉ thấy `mode=openai` chưa chứng minh câu đó do AI tạo. Mỗi bản nháp do AI sinh phải qua kiểm bằng chứng; tối đa một lần sửa nếu critic yêu cầu hoặc mọi block bị loại, bản sửa kiểm lại. Thường hai, tối đa bốn lượt Responses; token cộng các lượt, chưa tính embedding. Lỗi API trả 503, không tự chuyển offline/mock.

## Docker (tùy chọn, cần cài Docker trước)

Tạo .env, sau đó:

```powershell
docker compose build
docker compose run --rm chatbot python -m rag_app.cli ingest --mode hybrid
docker compose up -d
```

Port mặc định chỉ bind localhost. Không tự mở public. Cấu hình production và JWT trước khi cho người khác truy cập. Dữ liệu nguồn mount read-only, storage là named volume.

## Viết báo cáo từ phần code này

Đọc `docs/ARCHITECTURE.md`, `docs/INTEGRATION.md`, `docs/TEST_REPORT.md` và kết quả JSON. Trình bày các quyết định kỹ thuật, thực nghiệm baseline/hybrid, giới hạn corpus, lỗi đã sửa và giới hạn an toàn. Không chép các kết quả chưa chạy hoặc đổi “mock” thành “OpenAI thật”.

Tài liệu OpenAI chính thức đã đối chiếu:

- [Responses / Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Embedding API](https://developers.openai.com/api/docs/guides/embeddings)
- [GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
- [Data controls](https://developers.openai.com/api/docs/guides/your-data): store=False không đồng nghĩa không có abuse-monitoring logs; không gửi dữ liệu bệnh nhân thật.
