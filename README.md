# NutriMenu / NutriGuide — bản tích hợp để kiểm thử chung

Nhánh `integration/testda` chứa frontend, chatbot RAG, gateway và ba service Java đã ghép chung. Mỗi thành viên clone về thư mục riêng, cấu hình môi trường rồi chạy cùng phiên bản. Đây là bản phát triển/kiểm thử; chưa nghiệm thu toàn luồng trên máy mới và chưa phải cấu hình production.

## Thành phần

| Thư mục | Công nghệ | Cổng | Trách nhiệm |
|---|---|---|---|
| `frontend/` | React 19, TypeScript, Vite | 5173 | Giao diện dùng chung |
| `gateway/` | Python, FastAPI | 8080 | Auth, điều phối API, ánh xạ dữ liệu |
| `Userservice/` | Java 21, Spring Boot | 8083 | Tài khoản, hồ sơ, dị ứng |
| `foodcatalogservice/` | Java 21, Spring Boot | 8081 | Danh mục món ăn và dinh dưỡng |
| `mealoptimizerservice/` | Java 21, OR-Tools CP-SAT | 8082 | Sinh và kiểm tra thay đổi thực đơn |
| `chatbot/` | Python, FastAPI, ChromaDB | 8000 | Hỏi đáp RAG, đọc thực đơn, mở bảng đổi món |

Frontend gọi `/api` và `/api/chatbot` qua gateway. Hồ sơ nằm ở User Service; thực đơn nằm ở Meal Optimizer. Chatbot dùng PostgreSQL cho lịch sử và ChromaDB cho corpus/vector, không lưu hộ hồ sơ hoặc sinh thực đơn thay backend.

## Lấy mã nguồn

```powershell
git clone --branch integration/testda --single-branch https://github.com/Duclv623/NutriMenu.git NutriMenu-integration
cd NutriMenu-integration
```

## Chuẩn bị môi trường lần đầu

Cần Git, JDK 21 (`JAVA_HOME` đúng máy), Node.js 22.12 trở lên, Python 3.12 và PostgreSQL. Maven Wrapper nằm trong từng service; lần đầu cần mạng để tải dependency. Các script không yêu cầu thư mục clone phải tên `testda` hoặc nằm ở ổ C.

### 1. Database

Chạy trong `psql` với tài khoản có quyền tạo database:

```sql
CREATE DATABASE menufood_users;
CREATE DATABASE diabetes_food_catalog_db;
CREATE DATABASE diabetes_meal_optimizer_db;
CREATE DATABASE nutriguide;
```

Trong các terminal chạy Java, cấu hình tài khoản PostgreSQL của máy bạn:

```powershell
$env:DB_USERNAME = 'postgres'
$env:DB_PASSWORD = '<mat-khau-PostgreSQL-cua-ban>'
$env:SPRING_DATASOURCE_USERNAME = $env:DB_USERNAME
$env:SPRING_DATASOURCE_PASSWORD = $env:DB_PASSWORD
```

User Service chạy Flyway. Catalog tự seed món ăn khi khởi động với database trống. Optimizer dùng Hibernate ở chế độ phát triển; hướng dẫn nâng cấp database đã có ở [gateway/README.md](gateway/README.md) và [schema](mealoptimizerservice/schema/20261121_checked_meal_changes.sql). Không dùng database của người khác hoặc xóa dữ liệu thật để thử.

### 2. Dependency

Chạy từ thư mục gốc repository:

```powershell
py -3.12 -m venv chatbot/.venv
.\chatbot\.venv\Scripts\python.exe -m pip install -r chatbot/requirements.lock.txt
py -3.12 -m venv gateway/.venv
.\gateway\.venv\Scripts\python.exe -m pip install -r gateway/requirements.txt
Push-Location frontend
npm ci
Pop-Location
```

### 3. Cấu hình riêng

Chỉ copy các file chưa tồn tại; giữ cấu hình riêng nếu đã thiết lập:

```powershell
Copy-Item chatbot/.env.example chatbot/.env
Copy-Item gateway/.env.example gateway/.env
Copy-Item frontend/.env.example frontend/.env.local
```

Sửa `POSTGRES_DSN` trong hai file `.env` Python thành kết nối tới database `nutriguide`, dạng `postgresql://<user>:<password>@127.0.0.1:5432/nutriguide`. Mật khẩu có ký tự đặc biệt cần URL-encode. Giữ `POSTGRES_SCHEMA=chatbot` và `POSTGRES_SCHEMA=gateway` tương ứng; tài khoản cần quyền khởi tạo schema/bảng.

Tạo `GATEWAY_SERVICE_KEY` ngẫu nhiên ít nhất 32 ký tự rồi điền **cùng giá trị** vào `gateway/.env` và `chatbot/.env`:

```powershell
.\chatbot\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Điền `GEMINI_API_KEY` của bạn trong `chatbot/.env`; giữ `MEAL_SERVICE_MODE=http` và URL localhost trong mẫu khi các service chạy trên cùng máy. Các tài liệu nguồn và dữ liệu cấu trúc được đưa kèm; Chroma index được tạo lại khi chatbot khởi chạy lần đầu. Ingest hybrid có thể gọi API embedding tính phí. Không đưa khóa, `.env`, database, phiên đăng nhập hoặc lịch sử chat lên Git.

Frontend dùng:

```dotenv
VITE_API_MODE=api
VITE_API_BASE_URL=/api
VITE_RAG_BASE_URL=/api/chatbot
VITE_RAG_ENABLED=true
```

## Khởi chạy

Từ terminal đã cấu hình Java/PostgreSQL:

```powershell
.\run-all.ps1
```

Chọn `A` để mở sáu service; hoặc mở các terminal riêng chạy lần lượt:

```powershell
.\run-user-service.ps1
.\run-food-catalog.ps1
.\run-meal-optimizer.ps1
.\run-gateway.ps1
.\run-chatbot.ps1
.\run-frontend.ps1
```

Các lệnh service chạy liên tục, cần terminal riêng. Chờ Java/DB sẵn sàng rồi mở **http://127.0.0.1:5173**. Gateway hiện dùng một worker với session trong RAM; restart gateway cần đăng nhập lại.

## Luồng kiểm thử chung

1. Đăng ký, đăng nhập và lưu hồ sơ gồm xác nhận, bệnh nền, dị ứng.
2. F5, kiểm tra hồ sơ vẫn giữ đủ thông tin.
3. Tạo thực đơn bốn bữa ở ngày chưa có thực đơn. Đối chiếu trạng thái solver và món thực tế.
4. Mở chi tiết món, kiểm tra nguồn hướng dẫn chuẩn bị. Dữ liệu chưa có thời gian nấu không được tự điền.
5. Ở Trợ lý dinh dưỡng, chọn đúng thực đơn, hỏi “Bữa trưa của tôi có những món gì?”.
6. Yêu cầu “Đổi <tên món trong bữa trưa> sang <món/loại món muốn thay>”. Khi chưa rõ món, bot yêu cầu chọn/xác nhận. Chọn phương án → Xem trước → Áp dụng thay đổi; quay lại Thực đơn và F5 để đối chiếu.
7. Đăng xuất, thử tài khoản khác để kiểm tra dữ liệu theo người dùng.

Trong chế độ API, dùng **Khám phá món ăn**, **Sở thích món ăn**, **Thực đơn của tôi**, **Danh sách mua sắm** và **Lịch sử thực đơn** để thao tác với Food Catalog và Meal Optimizer. Tài khoản có vai trò `ADMIN` trong User Service có thêm trang **Quản trị món ăn & thực đơn**. [Hợp đồng tích hợp](gateway/README.md#chuc-nang-catalog-va-optimizer-tren-frontend).

## Kiểm thử và giới hạn

Frontend: `npm test`, `npm run build` trong `frontend/`. Test Python: cài thêm `chatbot/requirements-dev.txt`, đặt `PYTHONPATH` gồm `gateway` và `chatbot` rồi chạy test phù hợp. Test API/DB cần PostgreSQL/schema thử nghiệm riêng. CP-SAT: `.\test-meal-optimizer.ps1`.

Bản hiện tại đã qua các kiểm thử logic/hợp đồng và frontend; chưa thay thế kiểm thử toàn luồng với Java, PostgreSQL, Chroma và nhà cung cấp AI thật trên máy mới.

Chưa hỗ trợ thêm/bỏ cả bữa qua chat, tùy chọn thời gian nấu, hay sinh đè ngày đã có thực đơn. Catalog còn QA/ước tính và thiếu phiên bản công thức; hướng dẫn chế biến theo phương pháp không phải công thức đã thẩm định. Thông tin và thực đơn phục vụ đồ án, chưa được xác nhận lâm sàng.

Chi tiết: [gateway](gateway/README.md), [chatbot](chatbot/README.md), [tích hợp RAG](chatbot/docs/TEAM_INTEGRATION.md), [hợp đồng frontend](frontend/API_CONTRACT.md).

Mỗi thành viên tiếp tục làm ở nhánh cá nhân rồi đưa thay đổi vào nhánh tích hợp để kiểm thử chung. Không push đè nhánh của thành viên khác.
