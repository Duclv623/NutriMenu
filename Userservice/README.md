# MenuFood User Service

Java 21, Spring Boot 4.1.1, PostgreSQL. Cấu trúc Controller → Service → Repository; DTO riêng cho request/response.

## Chạy ứng dụng

Tạo database PostgreSQL riêng cho service, ví dụ `menufood_users`, rồi đặt biến môi trường trong PowerShell:

```powershell
$env:DB_URL = 'jdbc:postgresql://localhost:5432/menufood_users'
$env:DB_USERNAME = '<postgres-user>'
$env:DB_PASSWORD = '<postgres-password>'
.\mvnw.cmd spring-boot:run
```

Service chạy tại `http://localhost:8081`. Có thể đổi bằng biến `PORT`. Không lưu mật khẩu thật vào source.

Flyway chạy migration `src/main/resources/db/migration/V1__create_users_and_profiles.sql` trên database rỗng. Hibernate chỉ kiểm tra schema (`validate`), không tự sửa bảng. Migration tạo bảng `users`, `user_profiles` và ba bảng danh sách ăn uống. Không sửa migration đã chạy; các thay đổi sau cần migration mới.

## API hiện có

| Method | Endpoint | Chức năng |
|---|---|---|
| GET | `/api/auth/csrf` | Lấy token CSRF và cookie phiên |
| POST | `/api/auth/register` | Đăng ký tài khoản, trả HTTP 201 |
| GET | `/api/users/me` | Xem tài khoản đang xác thực |
| GET | `/api/users/me/profile` | Xem hồ sơ; trả 404 nếu chưa tạo |
| PUT | `/api/users/me/profile` | Tạo hoặc thay thế toàn bộ hồ sơ |

Bản đầu dùng HTTP Basic: chọn Basic Auth trong Postman, username là email và password là mật khẩu đã đăng ký. Không có endpoint login/JWT hoặc cơ chế thu hồi token ở giai đoạn này. Khi triển khai ra ngoài máy phát triển phải dùng HTTPS.

CSRF được bật. Trước POST/PUT, gọi `GET /api/auth/csrf`, giữ cookie `JSESSIONID`, rồi gửi token trong header được chỉ ra bởi `headerName` (mặc định `X-CSRF-TOKEN`). Postman tự giữ cookie; sau khi đăng nhập hoặc đổi phiên nên lấy lại token.

Ví dụ đăng ký:

```json
{
  "email": "user@example.com",
  "password": "ExamplePassword123!",
  "fullName": "Nguyễn Văn An"
}
```

Email được chuẩn hóa thành chữ thường. Mật khẩu dài 8–64 ký tự và tối đa 72 byte UTF-8 do giới hạn BCrypt. API không trả mật khẩu hoặc giá trị băm. Người đăng ký luôn có vai trò `USER`.

Ví dụ PUT hồ sơ:

```json
{
  "dateOfBirth": "1995-04-12",
  "gender": "MALE",
  "height": 170,
  "weight": 75,
  "activityLevel": "MODERATE",
  "goal": "LOSE_WEIGHT",
  "targetWeight": 68,
  "allergies": ["tôm", "đậu phộng"],
  "restrictedIngredients": ["đường"],
  "preferences": ["cá", "rau xanh"]
}
```

- `dateOfBirth`: bắt buộc, người từ đủ 18 tuổi. `age` được tính khi trả hồ sơ, không lưu riêng.
- `height`: cm; `weight`, `targetWeight`: kg. Số dương, tối đa 3 chữ số nguyên và 2 chữ số thập phân.
- `gender`: `MALE`, `FEMALE`, `OTHER`.
- `activityLevel`: `SEDENTARY`, `LIGHT`, `MODERATE`, `HIGH`, `VERY_HIGH`.
- `goal`: `LOSE_WEIGHT`, `MAINTAIN_WEIGHT`, `GAIN_WEIGHT`.
- `targetWeight`: tùy chọn, chưa kiểm tra tương quan với `goal`.
- Ba danh sách: tối đa 100 mục/danh sách, mỗi mục tối đa 100 ký tự và không được rỗng. Tạm lưu tên tự do; loại trùng sau khi bỏ khoảng trắng đầu/cuối, phân biệt hoa/thường. Chưa liên kết ID danh mục của Food Service.
- PUT thay thế hồ sơ, không phải cập nhật từng trường. Bỏ qua danh sách sẽ thay bằng danh sách rỗng; truyền `null` bị từ chối. Các trường cốt lõi phải đầy đủ, chưa hỗ trợ lưu hồ sơ nháp.
- API lấy chủ hồ sơ từ thông tin xác thực. Không nhận `userId` từ client hoặc tin cậy header `X-User-ID`.

Phản hồi thành công có `success`, `data`, `message`. Các lỗi nghiệp vụ có `timestamp`, `status`, `message`, `path`, `errors`: 400 cho dữ liệu không hợp lệ, 401 cho xác thực, 403 cho quyền/CSRF, 404 khi chưa có hồ sơ, 409 cho dữ liệu trùng.

## Kiểm thử và build

```powershell
.\mvnw.cmd test
.\mvnw.cmd package -DskipTests
```

Test dùng H2 ở chế độ PostgreSQL và chạy cùng migration Flyway; không cần thông tin database thật. Đây chưa phải kiểm chứng tương thích trên PostgreSQL thực tế.

## Phần chưa triển khai

JWT, đăng xuất/thu hồi token, xác minh email, đổi/quên mật khẩu, quản trị tài khoản, sửa họ tên, lịch sử cân nặng, lưu hồ sơ nháp, liên kết danh mục Food Service và API dành riêng cho giao tiếp giữa các service.

User Service chưa tính nhu cầu dinh dưỡng, gợi ý thực đơn hoặc chatbot. Trường `OTHER` hiện chỉ lưu lựa chọn giới tính; service tính mục tiêu dinh dưỡng cần thống nhất cách xử lý dữ liệu này.
