# NutriGuide — triển khai sửa và thu dữ liệu 30/10/2026

## Thay đổi đã triển khai

- Khóa phép tính toàn bộ 1.250 món NIN vì cơ sở 100 g của bản xuất cũ chưa được chứng minh theo từng bản ghi. Giữ số liệu nguồn để đối chiếu; không đưa số chờ xác minh vào evidence hoặc tổng bữa. 484 món có thêm cờ bất thường; 766 món còn lại chưa đủ bằng chứng cơ sở, không tự coi là đã đúng.
- Sửa nhận diện mang bầu, bệnh thận, típ một, yêu cầu liều/tần suất thuốc, lơ mơ/lú lẫn và phủ định một cụm triệu chứng.
- Tách ý tư vấn sản phẩm khỏi tra nhãn: ghép nguyên tắc ăn uống với kết quả nhãn khi phù hợp. Giữ cảnh báo thiếu bằng chứng trên các nhánh tra cứu.
- Chuẩn hóa đường thêm, giữ riêng folate DFE; nhãn thiếu chất được hỏi phải ghi không công bố.
- Giữ câu gốc và chủ thể riêng để truy vấn không tăng theo cả lịch sử. Câu so sánh giữ một vị trí cho mỗi nguồn được hỏi; tài liệu ADA phiên bản chưa bật được báo rõ.
- Bổ sung nguồn ADA về ngắt thời gian ngồi. Năm thu không được trình bày là năm xuất bản hoặc Standards 2026.
- Cập nhật năng lượng `nin_foods:1045` từ 1 lên 351,8 kcal bằng override có kiểm tra checksum và giá trị nguồn API mới; giữ bản gốc và bằng chứng. Không sửa các số khác bằng suy đoán.

## Dữ liệu đã thu

Nguồn và trạng thái từng lượt nằm trong `data/collected/review_2026-10-30/collection_manifest.json`. Đã thu lại đầy đủ 853 thực phẩm NIN và hơn 100 tài liệu/trang nguồn công khai. API món ăn hiện trả 1.024 dòng, có ID trùng; đã giữ các trang tải được, không thay bộ cũ bằng bộ không vượt kiểm tra. Một số URL trả 403, được ghi rõ trong manifest.

Nguồn mới về ngồi lâu: https://diabetes.org/health-wellness/fitness/break-sitting-streak . Chỉ đưa vào kho đoạn đã đối chiếu, không tự tạo hướng dẫn tập cá nhân.

`data/staging/review_2026-10-30/` có catalog chuẩn hóa, báo cáo lỗi, nhật ký thay đổi, so sánh nguồn và 1.250 bản ghi đang chờ xác minh. Các tài liệu mới thu không tự động được nạp toàn văn hoặc được coi là đã chuyên gia duyệt.

## Phần còn cần bằng chứng ngoài khả năng suy ra từ nguồn hiện có

1. Cơ sở khối lượng/khẩu phần và đơn vị đúng cho từng nhóm/mã món NIN; đặc biệt các món gắn cờ. Không thể mở tính bằng cách chia số hoặc đổi toàn bộ sang một suất.
2. Trường xơ/natri/đường không được nguồn công bố; cần đúng bản ghi/nhãn hoặc nguồn riêng có căn cứ, không lấy thực phẩm gần giống.
3. 12 nhãn đang chặn: giữ chặn nếu bản thu mới vẫn không đủ bằng chứng cho bảng dinh dưỡng. Việc tải thành công một trang không tự xác minh các số trên nhãn.
4. Cân phần ăn và khối lượng thành phẩm khi tài liệu không ghi. Không có phép đo thì không suy GI hoặc gram cả tô phở từ tên món hay gram một thành phần.
5. Các liên kết khẩu phần/yield/retention vẫn là công cụ riêng; chưa tự ghép để tính món khi không có cùng mã, trạng thái và cơ sở đã xác minh. Không tạo liên kết theo tên gần giống.

Chi tiết theo mã và trường thiếu: `data/staging/review_2026-10-30/pending_verification.json`. Đây là phần chưa hoàn tất xác minh, không phải dữ liệu đã sửa sạch.

## Chạy và phục hồi

Chạy `run.ps1` sau khi khởi động lại backend để dùng code mới. Index hybrid đã được cập nhật, tái sử dụng vector cũ; đoạn mới dùng API embedding thật.

Gói `releases/NutriGuide-2026-10-30.zip` chứa code, test, cấu hình và phụ thuộc dữ liệu công khai, có `PACKAGE_SHA256.json`. Gói không chứa `.env`, API key, database hoặc lịch sử chat. Giải nén vào thư mục mới, cài môi trường theo README, tạo `.env` riêng và ingest hybrid trước khi chạy. Không giải nén đè lên thư mục làm việc đang dùng.

Bản sao trước sửa ở `tmp/release-2026-10-30/backup/`: code, cấu hình và SQLite backup nhất quán. Muốn phục hồi phải dừng backend, khôi phục code/cấu hình phù hợp; không tự chép đè SQLite đang mở hoặc bỏ sót WAL. Các dữ liệu raw lịch sử được giữ nguyên, override mới là tệp riêng có thể bỏ khi phục hồi bản cũ.

Kết quả test và mẫu API thật được lưu tại `docs/release-2026-10-30/`; cần đọc kết quả thực tế, không suy độ chính xác y khoa từ số test đạt.

## Kết quả xác nhận

284 test đạt trong lượt toàn bộ; sau sửa cuối, 110 test của các nhóm bị ảnh hưởng đạt. Kiểm tra 12 tình huống, tổng 20 lượt chat, không gọi AI judge. Câu phở và so sánh nguồn đã được sửa sau các lượt đầu chưa đạt; giữ kết quả trước/sau trong báo cáo. Ruff và cú pháp JavaScript đạt. Gói bàn giao đã giải nén và kiểm tra từ bản sao sạch bằng môi trường Python hiện có.

Bộ test và ba DOCX runtime đã được đưa vào phần thay đổi Git để bàn giao; chưa tạo commit hoặc đẩy lên mạng.
