# NutriGuide Gateway — cổng 8080

Cập nhật 21/11/2026. Tầng điều phối đã được tách khỏi chatbot. `server.js` chỉ là entry point tương thích để khởi chạy gateway Python/FastAPI độc lập; không còn HTTP handler giả lập, userId=1, token cố định hay ghi hồ sơ vào `state.json`.

## Đường đi hiện tại

Frontend → `/api` trên Gateway 8080 → User Service 8083 / Food Catalog 8081 / Meal Optimizer 8082.

Frontend → `/api/chatbot/*` trên Gateway 8080 → `/api/*` của RAG 8000. Chatbot xác minh phiên qua API nội bộ gateway, đọc MealSnapshot qua HTTP rồi trả lời. Chatbot không còn nhận đăng ký, lưu hồ sơ hoặc sinh thực đơn của frontend.

`gateway_app` không import `rag_app`. Gateway có requirements, cấu hình, schema PostgreSQL và Dockerfile riêng. Trong môi trường phát triển có thể dùng chung Python executable/package đã cài; khi deploy phải dùng image/venv độc lập.

## Sửa lỗi ô xác nhận mất sau F5

Trước đây cờ xác nhận nằm trong metadata của chatbot và chỉ được chấp nhận khi fingerprint toàn response giống hệt lần lưu. Timestamp từ Java, số thập phân và thứ tự Set có thể đổi biểu diễn sau database round trip, làm fingerprint khác dù nội dung sức khỏe không đổi. Test hồi quy đã tái hiện trường hợp này trước khi sửa.

Hiện nguồn dữ liệu duy nhất là User Service:

- Flyway V2 thêm `confirmed`, `pregnant`, `special_diet` và `version` vào `user_profiles`.
- Request/response và service Java lưu/đọc đủ cờ; `@Version` kiểm tra cập nhật đồng thời.
- Request Java dùng `expectedVersion` theo version DB bắt đầu từ 0. UI dùng version DB + 1, dành 0 cho chưa có hồ sơ. Không so hash timestamp để xác nhận hoặc lưu profile nữa.
- BFF không đọc/ghi `profileMeta` cho sức khỏe. Dị ứng, loại trừ và sở thích vẫn ở các bảng User Service hiện có.
- Hồ sơ cũ trước V2 có `confirmed=false` an toàn mặc định; cần kiểm tra và xác nhận một lần sau nâng cấp. Không tự suy cờ sức khỏe cũ là đúng. Từ lần lưu sau, cả checkbox và dị ứng phải còn khi GET/F5/restart.
- Nếu User Service chưa nâng cấp, gateway trả lỗi cấu hình rõ; không trả thành công giả.

## Chạy trên máy

1. Khởi động lại **User Service** bằng `run-user-service.ps1` để Flyway chạy V2 và nạp DTO mới. Không xóa hoặc tạo lại database.
2. Khởi động lại `run-chatbot.ps1`, `run-gateway.ps1`, `run-frontend.ps1` trong các terminal riêng. Đăng nhập lại: phiên RAM cũ không chuyển sang tiến trình gateway mới.
3. Mở `http://127.0.0.1:5173`, lưu hồ sơ rồi F5. Kiểm tra riêng checkbox xác nhận, các cờ phạm vi và dị ứng.

Frontend `.env.local`:

```dotenv
VITE_API_MODE=api
VITE_API_BASE_URL=/api
VITE_RAG_BASE_URL=/api/chatbot
VITE_RAG_ENABLED=true
```

Gateway `.env`: dùng `.env.example`. `POSTGRES_DSN` là PostgreSQL, schema mặc định `gateway`. `GATEWAY_SERVICE_KEY` cần chuỗi ngẫu nhiên tối thiểu 32 ký tự, trùng giá trị phía chatbot; không đưa key vào VITE_* hoặc Git.

Chatbot `.env` giữ API key/index/PostgreSQL lịch sử riêng:

```dotenv
MEAL_SERVICE_MODE=http
MEAL_API_BASE_URL=http://127.0.0.1:8080/api/internal/
GATEWAY_AUTH_URL=http://127.0.0.1:8080/api/internal/identity
GATEWAY_SERVICE_KEY=<cùng key riêng với gateway>
```

Không còn TEAM_INTEGRATION_ENABLED/MEAL_SERVICE_MODE=team trong runtime chatbot. Dev launcher gateway ưu tiên `.venv` riêng, sau đó dùng venv hiện có của chatbot như một Python runtime dự phòng; có thể đặt `GATEWAY_PYTHON` rõ ràng. Deploy dùng `gateway/Dockerfile`, không dùng fallback này.

## Giữ dữ liệu khi tách service

Gateway có `team_identities` (UUID User Service → Long của Java) và `team_ui_state` cho dữ liệu phụ UI. Không giữ bản sao plan có thể sửa độc lập hoặc cờ sức khỏe ở đây.

Với database cũ dùng chung kết nối, `IMPORT_LEGACY_STATE=true`, `LEGACY_SCHEMA=chatbot` sẽ sao chép idempotent mapping, check-in, checkbox mua sắm và liên kết plan sang schema gateway. Không sao chép profileMeta. Dữ liệu nguồn được giữ nguyên; xung đột ID làm dừng thay vì gán lại chủ tài khoản. ID Long từ 1.000.000.000 là vùng phải dành riêng cho mapping; không map tài khoản mới vào user 1 của dữ liệu demo.

Nếu chuyển sang database/server khác, phải sao lưu và di chuyển bảng mapping/UI trước khi chạy. Sao lưu cả User Service, Catalog, Optimizer, gateway và lịch sử RAG. Không nhập `state.json` chung làm dữ liệu của một user thật.

## Giới hạn backend còn phải sửa

1. Catalog/Optimizer chưa có bảo vệ đầy đủ khi gọi trực tiếp; phải để trong mạng riêng sau gateway. Gateway không sửa được đường gọi trực tiếp vào các port này.
2. Template ba bữa chưa được seed; thời gian nấu và tùy chọn không lặp chưa có hợp đồng đầy đủ. Danh sách không ăn đã được ánh xạ tên món/nguyên liệu trong recipeBreakdown sang excludedDishIds, rồi Optimizer gộp vào danh sách loại trước khi Catalog chọn ứng viên. Tên chưa nhận diện được sẽ yêu cầu làm rõ; món thiếu recipe bị loại khi có hạn chế. Dị ứng vẫn có mã và điều kiện kiểm tra riêng.
3. Chỉ sinh mới bốn bữa cho ngày trống. Sinh lại vẫn bị từ chối trước khi gọi nhánh Java chưa bảo toàn plan khi UNKNOWN/MODEL_INVALID. Khóa advisory PostgreSQL chỉ điều phối các request đi qua gateway.
4. Đổi món/khẩu phần có preview/apply riêng đã được bổ sung trong lần sửa bên dưới. API manual-replace/rebalance cũ không được gateway dùng cho luồng này. Catalog còn thiếu API bỏ favorite.
5. Dữ liệu catalog vẫn có QA/ước tính; provenance, raw/cooked và phiên bản recipe phải được hoàn thiện. Chạy CP-SAT thật không chứng minh kết quả đã được thẩm định hoặc phải đạt đúng 2.200 kcal.
6. Auth hiện dùng Basic/CSRF giữa gateway và User Service, cookie opaque cho browser; phiên giữ trong RAM, một worker. Restart yêu cầu đăng nhập lại nhưng không làm mất profile. Trước khi chạy nhiều replica cần chuyển sang JWT thống nhất hoặc session store dùng chung, không bật nhiều worker với session RAM.

<a id="chuc-nang-catalog-va-optimizer-tren-frontend"></a>

## Chức năng Catalog và Optimizer trên frontend

- Trong chế độ API, **Khám phá món ăn** có tạo món riêng, so sánh, tính khẩu phần, đối chiếu hồ sơ và món tương đương. **Sở thích món ăn** hiển thị món yêu thích và món không thích. **Thực đơn của tôi** có tạo theo ngày, theo hồ sơ, theo tuần, đổi món, đánh giá và cân bằng lại. **Danh sách mua sắm** dùng khoảng ngày của Optimizer. **Lịch sử thực đơn** hiển thị thống kê và món trong thực đơn gần đây. Tài khoản `ADMIN` mở các thao tác quản lý dữ liệu và chẩn đoán tại `/quan-tri`.
- Gateway chuyển tiếp đúng phương thức HTTP qua `/api/service-actions/catalog/…` hoặc `/api/service-actions/optimizer/…`. Mỗi route được khai báo theo phương thức và đường dẫn. Gateway lấy ID dịch vụ từ phiên đã xác thực, kể cả khi client gửi ID khác. Endpoint món gần đây dùng `internal/optimizer/users/me/recent-dishes` trên frontend.
- Gateway đọc lại tài khoản User Service khi xác thực mỗi request. Các thao tác `admin/` yêu cầu vai trò `ADMIN` trong bảng `users` của User Service. Tài khoản tự đăng ký nhận vai trò `USER`. Quản trị viên database có thể cấp quyền cho đúng tài khoản theo quy trình của môi trường triển khai.
- Sinh thực đơn đi theo hồ sơ đã xác nhận và phiên bản hồ sơ hiện tại. Luồng tính từ hồ sơ đọc giới tính, chiều cao, cân nặng và vận động từ User Service. Optimizer quy đổi `SEDENTARY` và `LIGHT` thành `LIGHT`, `MODERATE` thành `MODERATE`, `HIGH` và `VERY_HIGH` thành `HEAVY`. Người dùng chọn thêm các bệnh nền dành riêng cho lần tính này. Các ngày đã có thực đơn được giữ nguyên. Sinh tuần có thể trả về ngày khả thi và ngày chưa có nghiệm.
- Preview và apply dùng chữ ký phương án đã kiểm tra. Các thao tác thay theo lựa chọn, tự tìm món và cân bằng lại qua Gateway áp dụng cả bộ lọc của hồ sơ hiện tại lẫn bộ lọc đã lưu khi sinh. Với database Optimizer chạy schema quản lý riêng, chạy thêm [migration lưu bộ lọc](../mealoptimizerservice/schema/20261124_meal_plan_filters.sql) sau migration checked meal changes.
- Catalog và Optimizer mặc định lắng nghe trên loopback. Các môi trường tách máy có thể đặt `FOOD_CATALOG_BIND_ADDRESS` và `MEAL_OPTIMIZER_BIND_ADDRESS` cho địa chỉ mạng nội bộ dùng bởi Gateway.

## Trước khi deploy

- HTTPS trên public origin; reverse proxy phục vụ frontend và `/api` cùng origin. Chỉ publish edge/gateway; các service Java/RAG/DB ở mạng nội bộ.
- APP_ENV=production, PUBLIC_ORIGINS đúng HTTPS domain; key nội bộ qua secret manager. Cấu hình TLS giữa các upstream theo kiểm tra cấu hình hiện có, hoặc service mesh terminates TLS.
- Cấu hình service URLs bằng DNS container/service, không dùng 127.0.0.1 để gọi container khác.
- Dùng PostgreSQL persistent volume/backups, migration có kiểm thử; tài khoản runtime tối thiểu quyền, migration chạy riêng khi cần. Đồng nhất múi giờ ứng dụng, ví dụ Asia/Ho_Chi_Minh cho đồ án này.
- Nghiệm thu thật hai tài khoản: login → profile → F5 → restart → generate → lock/eaten → chat đúng plan/ngày → history → logout → tài khoản khác. Kiểm tra lỗi dependency và stale version.
- Không xem health liveness, build hoặc unit test qua là chứng nhận sẵn sàng production.

## Kiểm thử đã thực hiện

User Service: 22 test qua với MockMvc/H2 + Flyway, gồm lưu cờ rồi GET ở request mới và từ chối cập nhật stale. Test gateway/RAG dùng upstream HTTP có kiểm soát để kiểm tra hợp đồng, không tuyên bố database PostgreSQL/Java live đã qua E2E trong môi trường bị chặn socket.

## Bổ sung bộ lọc không ăn

Meal Optimizer bổ sung trường tùy chọn `excludedDishIds` trong GenerateDailyMealRequest, gộp cùng recent exclusions trước khi lấy candidates. Request cũ không gửi trường này vẫn dùng danh sách rỗng. Luồng weekly sao chép trường này từ dailyTargetTemplate. Không đổi schema database hoặc CpSatMealOptimizationEngine.

Gateway kiểm tra GET `/api/v1/internal/optimizer/capabilities` có `excludedDishIds=true` trước khi gửi yêu cầu có hạn chế, để tránh một tiến trình Java cũ im lặng bỏ qua trường mới. Sau cập nhật phải restart **Meal Optimizer và Gateway**, không chỉ refresh frontend.

Tên được so theo token, giữ dấu nếu người dùng nhập có dấu; chấp nhận không dấu theo cách loại trừ bảo thủ. Đây là matching tên danh mục, chưa phải hiểu mọi tên đồng nghĩa. Frontend thêm gợi ý từ tên món/nguyên liệu thực. Test gateway/xác thực hiện 45 ca; Java chọn chạy 4 ca (2 pipeline exclusions + 2 solver) đều qua. Chưa thay thế kiểm thử toàn luồng trên PostgreSQL thật.

## Sửa đổi món, cách chuẩn bị và ngữ cảnh chatbot (21/11/2026)

- Frontend từng kiểm tra `data_mode` nhưng FastAPI xuất `MealSnapshot.dataMode` theo alias camelCase. Đã sửa kiểu phản hồi và kiểm tra ở Chat; vẫn từ chối snapshot mock hoặc sai plan. Cấu hình chatbot hiện là HTTP qua API nội bộ gateway.
- `POST /api/meal-plans/{id}/swap-preview` gửi lựa chọn tới Optimizer `/change-preview`. Chỉ hiển thị nút xác nhận khi server trả `validationPassed=true` và `changeSignature`. Preview không ghi plan.
- `POST /api/meal-plans/{id}/swap` gửi lại chữ ký, phiên bản plan và hồ sơ. Optimizer khóa bản ghi thuộc user, kiểm tra phiên bản, lấy candidates theo bộ lọc hiện tại, rồi chạy CP-SAT với **mọi món và khẩu phần được cố định**. Chỉ thay item đã chọn khi hợp lệ. Món bị giữ, đã ăn, trùng, sai vai trò/khẩu phần hoặc vượt ràng buộc cứng sẽ bị từ chối. Thay đổi catalog giữa hai bước buộc xem trước lại.
- Java bổ sung `CheckedMealChangeRequest`, `CheckedMealChangeController`, `CheckedMealChangeService`, `MealPlan.@Version`, phiên bản DTO và khóa truy vấn repository. Solver nhận thêm `fixedServingsBySlot`; luồng sinh thực đơn cũ không gửi trường này vẫn hoạt động như trước. Generation chỉ lưu trạng thái OPTIMAL/FEASIBLE. Lock/eaten chạm parent và flush để trả version mới; frontend tải lại plans sau ghi nhận đã ăn.
- Plan lưu template và giới hạn gốc dùng để kiểm tra đổi món. **Plan cũ thiếu quy tắc gốc vẫn xem được nhưng phải tạo lại trước khi đổi**; không tự đoán quy tắc của chúng. Vì gateway vẫn chưa hỗ trợ sinh đè ngày có plan, hãy tạo ngày trống; nếu chủ động xóa plan cũ thì chỉ xóa sau khi đã xuất bản cần giữ.
- Schema additive được chuẩn bị tại `mealoptimizerservice/schema/20261121_checked_meal_changes.sql`. Chưa chạy script lên PostgreSQL thật trong phiên này. Dev hiện dùng Hibernate ddl-auto=update; deployment nên chạy migration riêng rồi validate schema, không dựa vào auto-update.
- Food Catalog bổ sung `preparationSteps`, `preparationGuideKind`, giới hạn khẩu phần vào response. `PreparationGuide` dựa trên nguyên liệu thực và enum phương pháp chế biến, không thêm bảng công thức. Đây là **gợi ý theo phương pháp**, chưa phải công thức hoàn chỉnh đã kiểm chứng. Chưa có dữ liệu thời gian nấu; UI tiếp tục nói rõ thay vì tự điền.
- Restart Food Catalog, Meal Optimizer, Gateway và Chatbot; reload frontend, đăng nhập lại khi gateway đổi tiến trình. Workspace chỉ bật swap khi capabilities có validatedSwap=true và planVersions=true. Refresh trình duyệt không cập nhật tiến trình Java cũ.

Kiểm thử có CP-SAT native và HTTP upstream kiểm soát; chưa nghiệm thu giao diện + Java + PostgreSQL thật sau restart trong môi trường hạn chế socket. Kết quả chi tiết cập nhật tại `integration-checks-20261121/RESULTS.md`.
