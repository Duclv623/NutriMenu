# Sửa tra sữa theo ml và tổng cơm/ức gà chín — 31/10/2026

## Hành vi

- `200 ml sữa bò tươi có bao nhiêu calo?`: hiển thị các nhãn sữa bò tươi có dữ liệu theo 100 ml, yêu cầu chọn đúng sản phẩm. Không tự gán nhãn hiệu và không quy đổi ml thành gram. Lượng 200 ml và chất cần xem được giữ khi chọn ID, tên sản phẩm hoặc một mô tả rõ thương hiệu như `TH nguyên chất`. Bảng chỉ hiển thị chất đã hỏi.
- Sau khi chọn TH nguyên chất: tính 200 ml thành 126,4 kcal theo nhãn 63,2 kcal/100 ml. Giá trị này thuộc sản phẩm đã chọn, không được gán cho mọi loại sữa bò.
- `Tổng 150 g cơm chín và 100 g ức gà chín có bao nhiêu calo và đạm?`: tính được bằng code, trả kết quả có nhãn ước tính và công khai giả định cơm trắng gạo hạt dài / thịt ức gà bỏ da, cách chế biến chưa xác định theo bản ghi tham khảo.
- Ví dụ trên cho 339 kcal và 32,035 g đạm. 150 g cơm trắng: 195 kcal và 4,035 g đạm; 100 g ức gà theo bản ghi FNDDS: 144 kcal và 28 g đạm. Không dùng bản ghi ức gà nướng (165 kcal/100 g) thay cho bản ghi chưa xác định cách chế biến.
- Không yêu cầu người dùng chọn một danh sách rỗng; phân biệt bản ghi còn mơ hồ và bản ghi chưa có. Không hỏi lại trạng thái sống/chín hoặc khối lượng người dùng đã cung cấp. Nếu chỉ tính được một phần, không gọi đó là tổng bữa.

## Nguồn và giới hạn

Giữ nguyên kho NIN/FCT và các rào chắn với món chưa xác minh. Bổ sung riêng ba snapshot USDA, kiểm SHA256, mã, tên, kiểu dữ liệu và đơn vị trước khi nạp:

| FDC ID | Bản ghi |
| --- | --- |
| [168878](https://fdc.nal.usda.gov/food-details/168878/nutrients) | Rice, white, long-grain, regular, enriched, cooked — SR Legacy |
| [2705954](https://fdc.nal.usda.gov/food-details/2705954/nutrients) | Chicken breast, NS as to cooking method, skin not eaten — FNDDS |
| [171477](https://fdc.nal.usda.gov/food-details/171477/nutrients) | Chicken, broilers or fryers, breast, meat only, cooked, roasted — SR Legacy |

Dữ liệu và bản gốc nằm ở `data/structured/common_food_references`. Không yêu cầu gọi USDA trong lúc chat. Collector dùng API công khai có DEMO_KEY theo tài liệu USDA để thu đúng các ID đã chọn; không chứa khóa riêng của người dùng.

Giá trị là số tham khảo của bản ghi, không phải kết quả phân tích phần ăn thực tế. Nếu người dùng nêu rõ cơm gạo lứt, gà chiên, còn da hoặc cách chế biến khác chưa có bản ghi phù hợp, hệ thống không áp dụng mặc định cơm trắng/ức gà bỏ da. Dầu, sốt hoặc gia vị bổ sung chưa khai báo không được tự thêm vào phép tính.

Tên gọi ức/lườn được nối với bản ghi đúng trạng thái; ví dụ `ức gà sống` nối với bản ghi lườn sống NIN, không nối với thịt chín.

## Kiểm tra

`tests/test_common_food_lookup.py` kiểm phép cộng, giả định hiển thị, chọn nhãn giữ lượng/chất, trạng thái thịt, bản ghi thiếu, tổng chưa đủ thành phần và chống sửa snapshot nguồn. Bộ kiểm tra toàn dự án: `tests-common-food.xml`. Kết quả mô hình thật của hai câu báo lỗi và bước chọn sữa: `common-food-live.json`.

Kết quả: 363 bài tự động qua, 3 bài API thật được loại khỏi lượt này; sau thay đổi trình bày, 55 bài liên quan tiếp tục qua (`tests-common-food-targeted.xml`). Máy chủ đang chạy đã được khởi động lại và kiểm tra lại chuỗi sữa/chọn nhãn/tổng cơm với ức gà (`common-food-server-smoke.json`).
