# Hợp đồng tích hợp frontend — bản đề xuất

Các endpoint ở phần Gateway dưới đây là đề xuất cho backend nhóm, **chưa được triển khai trong repo này**. Các endpoint RAG ở cuối đã có trong chatbot. Không coi việc có adapter frontend là bằng chứng backend đã hoàn thành.

## Quy ước

- Gateway mặc định `http://127.0.0.1:8080/api`, proxy dev `/api`.
- JSON UTF-8, camelCase; enum theo `src/types.ts`.
- Xác thực qua cookie HttpOnly hoặc bearer JWT do backend cấp. Không dùng danh tính demo để xác thực server.
- Đơn vị dinh dưỡng: `energy` kcal, `carbs/protein/fat/fiber` g, `sodium` mg. `Food.nutrition` cho **một khẩu phần công thức**. Không trộn số liệu trên 100g với số liệu mỗi phần.
- `Food.ingredients[].grams` là gram cho một khẩu phần. `PlanItem.servings` là hệ số phần; gram và dinh dưỡng nhân cùng hệ số này. Phải chuẩn hóa trạng thái sống/chín trên backend. Schema UI hiện chỉ dùng dữ liệu đã đủ, không thay giá trị thiếu bằng 0.
- Lỗi `{ "message": "..." }`, hoặc `{ "detail": "..." }` / `{ "detail": { "code": "...", "message": "..." } }`.
- 401 hết phiên; 403 không có quyền; 409 xung đột phiên bản; 422 không hợp lệ; 429 quá hạn mức; 503 dịch vụ chưa sẵn sàng.
- Frontend timeout thông thường 30 giây, chat 90 giây. Hợp đồng hiện chờ solver đồng bộ. Nếu giải lâu, backend/frontend cần bổ sung job API, polling và hủy job; chưa triển khai luồng này.

## Gateway

| Method | Path | Dữ liệu / kết quả |
|---|---|---|
| POST | `/auth/login` | `{email,password}` → `{user,accessToken?}` |
| POST | `/auth/register` | `{name,email,password}` → `{user,accessToken?}` |
| POST | `/auth/logout` | Hủy phiên server, 204 |
| GET | `/workspace` | `Workspace` từ `src/types.ts`; chỉ dữ liệu của user hiện tại |
| PUT | `/me/profile` | `Profile` → `Profile` có version mới; kiểm tra version hiện tại |
| POST | `/meal-plans/generate` | `{date,target,snacks,maxMinutes,excludeRepeat,profileVersion}` → `Plan` |
| POST | `/meal-plans/:id/swap` | `{baseVersion,itemId,foodId,servings,profileVersion}` → `Plan` đã kiểm tra/giải lại |
| PUT | `/meal-plans/:id` | `Plan` với version mới → `Plan`; chỉ cập nhật thuộc tính được cho phép, không tin dinh dưỡng từ client |
| DELETE | `/meal-plans/:id` | 204 |
| PUT/DELETE | `/me/favorites/:foodId` | 204 |
| PUT | `/me/meal-logs` | `{key,completed}`; key UI là `planId:itemId` |
| PUT | `/me/shopping-list` | `{checkedIds:string[]}`; key là `planId:ingredientId` |
| POST | `/me/check-ins` | `CheckIn` → `CheckIn` |
| DELETE | `/me/check-ins/:id` | 204 |

`Workspace` gồm profile, foods, plans, favorites, checkedShopping, checkIns, conversations, completedMeals. Với dữ liệu lớn cần bổ sung API tìm kiếm và phân trang phía server; phiên bản này tải danh mục qua workspace và lọc trên trình duyệt.

Backend chịu trách nhiệm tính mục tiêu hợp lệ, xử lý mọi dị ứng/hạn chế và xác nhận phạm vi. `target` frontend gửi là mong muốn, không phải chỉ định được chấp nhận mặc định. Giữ món phải được gửi hoặc đọc từ plan hiện tại theo ngày; backend không bỏ ràng buộc bắt buộc khi vô nghiệm. API swap nhận ID món + số phần như một yêu cầu; server quyết định có chấp nhận hay giải lại, không lưu trực tiếp số client tự tính.

## Kết quả CP-SAT

```json
{
  "id": "plan-123",
  "date": "2026-11-10",
  "profileVersion": 3,
  "version": 1,
  "dataMode": "api",
  "solverStatus": "FEASIBLE",
  "target": 1800,
  "createdAt": "2026-11-10T12:00:00Z",
  "notes": [],
  "items": [{ "id": "item-1", "foodId": "food-1", "meal": "breakfast", "servings": 1, "locked": false }]
}
```

Ví dụ chỉ minh họa cấu trúc; target không phải khuyến nghị. `INFEASIBLE`, `UNKNOWN`, `MODEL_INVALID` có thể trả `items: []` và lý do trong `notes`. UI không hiển thị chúng như thực đơn dùng được. `NOT_RUN` dành cho fixture. `OPTIMAL`/`FEASIBLE` chỉ được dùng khi backend thật trả về sau kiểm tra. Mọi foodId trong plan phải có trong workspace; thiếu món phải báo lỗi thay vì coi dinh dưỡng bằng 0.

Schema hiện có của chatbot dùng `MealSnapshot` khác schema UI này: `energyKcal`, `carbohydrateG`, `mealType=BREAKFAST`, `amount`, `unit`, phiên bản catalog và nguồn. Backend/adapter phải ánh xạ rõ đơn vị, trường và ID; **không gán nguyên JSON MealSnapshot vào Plan của UI**. Hợp đồng chatbot gốc: `../chatbot/contracts/meal-service.schema.json`.

## RAG đã có

Proxy dev `/rag/api` tới FastAPI `http://127.0.0.1:8000/api`.

| Method | Path | Mục đích |
|---|---|---|
| GET | `/status` | Kiểm tra chỉ mục, provider và kết nối thực đơn |
| GET | `/meal-context` | Hồ sơ/thực đơn theo danh tính backend |
| POST | `/chat` | `{message,session_id?,save_history,meal_context?:{plan_id}}` |
| POST | `/feedback` | `{message_id,rating:"helpful"\|"not_helpful"}` |
| DELETE | `/sessions/:id` | Xóa hội thoại theo owner |
| GET | `/documents/:id/...` | Xem tài liệu qua URL trả trong citation |

Response chat giữ snake_case như chatbot hiện tại: `session_id,message_id,answer,citations,warnings`. Adapter ánh xạ về kiểu UI, giữ session để hỏi tiếp. Chỉ gửi plan_id từ backend thật; không gửi id fixture. Citation được render bằng text React, không chèn HTML tùy ý; chỉ mở URL http/https. Khi lưu chat bật, server còn áp dụng retention và owner của riêng chatbot.

Không triển khai refresh-token hoặc thay đổi mật khẩu trong frontend này vì nhóm chưa thống nhất hợp đồng tương ứng. Khi backend trả 401, UI đưa người dùng về đăng nhập. Backend production vẫn phải xác minh JWT và phân quyền độc lập.
