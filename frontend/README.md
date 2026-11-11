# NutriGuide frontend

React 19, TypeScript, Vite và React Router. Giao diện tiếng Việt, tối ưu desktop và điện thoại, tông trắng/xanh trầm. Không phụ thuộc ảnh AI hay ảnh từ mạng; hình món dùng ký hiệu trung tính để không gán ảnh sai món.

## Chạy nhanh

Yêu cầu Node.js 22.12+ hoặc Node.js 24 LTS và npm. Tại thư mục này:

```powershell
npm ci
npm run dev
```

Mở http://127.0.0.1:5173 và chọn **Trải nghiệm bản demo**. Đăng ký/đăng nhập demo chỉ có hiệu lực trên trình duyệt này. Mật khẩu demo được băm PBKDF2 với salt, nhưng đây không phải cơ chế xác thực production. Dùng thông tin giả lập.

```powershell
npm test
npm run build
npm run preview
```

`dist/` là kết quả build. Máy chủ triển khai phải trả `index.html` cho các route giao diện, nhưng không rewrite route API thành HTML.

## Các chức năng đã làm

| Màn hình | Thao tác |
|---|---|
| Đăng nhập / đăng ký | Validation, hiện/ẩn mật khẩu, phiên đăng nhập, route bảo vệ, demo riêng |
| Tổng quan | Tổng dinh dưỡng, tiến độ ghi nhận từng bữa, thông tin hồ sơ và kế hoạch |
| Hồ sơ | Tuổi, giới tính, chiều cao/cân nặng, vận động, mục tiêu, dị ứng, món loại trừ, kiểm tra phạm vi |
| Kho món | Tìm tiếng Việt có/không dấu, lọc bữa/nhóm/dị ứng, sắp xếp, phân trang |
| Chi tiết món | Nguyên liệu và gram, tổng dinh dưỡng, bước chuẩn bị, dị ứng, yêu thích |
| Thực đơn | Chọn ngày, tạo mẫu, thêm bữa phụ, giữ món, xem trước đổi món/khẩu phần, ghi nhận đã ăn |
| Kết quả solver | Hiển thị OPTIMAL / FEASIBLE / INFEASIBLE / UNKNOWN / MODEL_INVALID / NOT_RUN |
| Mua sắm | Cộng dồn gram nguyên liệu theo khẩu phần, chọn thực đơn, đánh dấu đã có, tải TXT |
| Lịch sử | Tìm, lọc, mở đúng thực đơn theo ID, xóa có xác nhận |
| Theo dõi | Thêm/xóa cân nặng và đường huyết tự nhập, đồ thị theo ngày, chọn khoảng thời gian |
| Chatbot | Nối API FastAPI sẵn có, câu hỏi gợi ý, trích dẫn, phản hồi, hội thoại, lưu có lựa chọn, xóa |
| Cài đặt | Kiểm tra trạng thái RAG, nguồn dữ liệu, sao lưu và đặt lại demo |

Demo lưu dữ liệu theo tài khoản trong localStorage; phiên tài khoản và access token ở sessionStorage. Hội thoại mới chỉ được lưu khi bật **Lưu hội thoại**. Khi tắt lại, các hội thoại đã lưu trước đó vẫn còn; dùng nút xóa để xóa chúng. Dữ liệu tạm của phiên chưa lưu bị bỏ khi rời trang.

Hồ sơ tăng phiên bản sau khi lưu. Thực đơn cũ vẫn được giữ trong lịch sử và bị đánh dấu cần tạo lại. Bộ lọc demo giữ dị ứng và món loại trừ ngay cả khi không tìm thấy món. Đối tượng dưới 18 tuổi, thai kỳ/cho con bú hoặc chế độ đặc biệt bị chặn tạo thực đơn.

## Demo và CP-SAT thật

Danh mục `src/data/seed.ts` là **fixture phục vụ UI**, không phải bản sao dữ liệu dinh dưỡng chuẩn hóa của nhóm. Thực đơn demo chọn ngẫu nhiên món phù hợp bộ lọc; mục tiêu kcal chỉ minh họa UI. Nó không tối ưu dinh dưỡng và luôn có `solverStatus=NOT_RUN`. Số tổng và danh sách mua sắm là phép cộng từ fixture theo khẩu phần.

Frontend không cài CP-SAT, không tạo quy tắc lâm sàng hoặc tự kê mục tiêu năng lượng. Khi tích hợp, Recommendation Service nhận yêu cầu, giải CP-SAT và trả kết quả đã kiểm tra. Lớp gọi API, phiên bản và các trạng thái giao diện đã chuẩn bị; các endpoint nghiệp vụ ngoài RAG là hợp đồng đề xuất, cần thống nhất với backend.

## Kết nối chatbot hiện có

Mã chatbot nằm trong `chatbot/` trên nhánh `chatbot-service`. Nếu đang chạy riêng nhánh `frontend`, hãy mở một checkout riêng của `chatbot-service` và chạy backend tại cổng 8000. Trong workspace có cả hai thư mục, có thể chạy từ thư mục gốc:

```powershell
.\run-chatbot.ps1
```

Xem [README của dịch vụ chatbot](https://github.com/Duclv623/NutriMenu/blob/chatbot-service/chatbot/README.md) để cài thư viện, chuẩn bị dữ liệu và chạy backend.

Để bật RAG thật với các trang khác vẫn ở demo, tạo `.env.local`:

```dotenv
VITE_API_MODE=demo
VITE_RAG_ENABLED=true
VITE_RAG_BASE_URL=/rag/api
```

Khởi động lại Vite. Proxy `/rag/api/*` chuyển tới `http://127.0.0.1:8000/api/*`. Proxy chỉ dịch Origin của chính giao diện dev `127.0.0.1:5173` hoặc `localhost:5173`; không tắt kiểm tra Origin của chatbot. Nếu đổi cổng frontend, cần cập nhật danh sách Origin dev trong `vite.config.ts`.

Trong chế độ kết hợp này, hồ sơ/thực đơn demo frontend **không đồng bộ** với `/api/meal-context` của chatbot. Trang chat hiện thông báo riêng về ngữ cảnh backend. Không truyền ID thực đơn demo thành ID thật cho RAG. Khi API_MODE=api, chat mới gửi plan_id từ thực đơn API.

Khóa Gemini và mọi secret chỉ ở `chatbot/.env`. Không dùng biến VITE_ cho secret. Kiến thức trả lời qua AI có thể sử dụng quota/chi phí và gửi câu hỏi đến nhà cung cấp cấu hình ở backend.

## Nối toàn bộ backend nhóm

```dotenv
VITE_API_MODE=api
VITE_API_BASE_URL=/api
VITE_RAG_BASE_URL=/rag/api
```

Vite dev proxy mặc định `/api` tới cổng 8080 và `/rag` tới cổng 8000. Đổi upstream bằng biến môi trường `API_PROXY_TARGET`, `RAG_PROXY_TARGET` trước khi chạy Vite, hoặc dùng địa chỉ đầy đủ VITE_* nếu backend đã cấu hình CORS và cookie phù hợp.

Production không có proxy của Vite: cấu hình reverse proxy `/api/` và `/rag/`, HTTPS, authentication, cookie và Origin ở Gateway. Chế độ API không tự fallback sang fixture nếu lỗi. Frontend không phân quyền thay backend. Backend phải kiểm tra chủ sở hữu của mọi plan/session và tính lại các ràng buộc.

Hiện adapter kỳ vọng một response `/workspace` tổng hợp để khởi tạo màn hình. Nếu backend dùng nhiều endpoint, chỉ thay `src/services/api.ts` để gom dữ liệu tương ứng. Xem [API_CONTRACT.md](API_CONTRACT.md) và kiểu TypeScript trong `src/types.ts`.

## Cấu trúc

```text
src/
  components/       Thành phần dùng chung, modal, nutrition, chi tiết món
  data/seed.ts      Fixture riêng của frontend
  pages/            Các màn hình
  services/         HTTP client, auth và adapter API/RAG
  state.tsx         Trạng thái, lưu demo theo tài khoản
  types.ts          Kiểu dữ liệu trao đổi
  utils.ts          Phép cộng dinh dưỡng, bộ lọc, ngày tháng, xuất file
  test/             Kiểm tra nghiệp vụ và luồng giao diện
references/         PDF/video do người dùng cung cấp; preview và video không commit
```

18 kiểm tra frontend bao phủ phép cộng/khẩu phần, gom nguyên liệu, dị ứng, phạm vi, khóa món, trạng thái demo, ngày tháng, URL nguồn, lỗi HTTP, phiên đăng nhập, hồ sơ đổi phiên bản, đổi món và lưu chat có lựa chọn. Kiểm tra này không xác nhận tính phù hợp y khoa hoặc chất lượng CP-SAT thật.
