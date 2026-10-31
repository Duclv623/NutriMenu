# Kiểm tra chất lượng sau sửa — 31/10/2026

Trong phiên sửa này, GPT-6.1 Sol High xử lý mã ứng dụng; GPT-6.1 Terra Medium phụ trách kiểm thử và rà soát câu trả lời. Model đánh giá qua API được ghi riêng bên dưới.

Đã kiểm lại 32 câu chưa đạt hoặc chưa đủ căn cứ trong đợt Q026–Q100, cùng ba lượt Q071, Q072 và Q075 để tạo đúng ngữ cảnh hội thoại. Các lượt chạy nối tiếp, giới hạn một yêu cầu mỗi 15 giây, burst 1. Model sinh và kiểm chứng của ứng dụng (khi cần) cùng model đánh giá độc lập đều là `gemini-3.1-flash-lite`. Các câu trả lời tĩnh không được tính là lượt sinh của model. Dữ liệu, phản hồi, ID và nhận xét judge gốc được lưu tại [quality-fixes-live.json](quality-fixes-live.json); audit ban đầu không bị ghi đè.

Đợt đầu có 35 lượt, judge chấm 29 đạt và 6 cần cải thiện, bao gồm một lượt dựng ngữ cảnh. Sau đó kiểm lại Q032, Q033, Q047, Q073 và Q100 trên mã sửa mới (kèm Q071–Q072 để dựng lại phiên); kiểm riêng Q093 sau sửa kiểm chứng nguồn và kiểm tiếp Q032 sau khi bổ sung ví dụ hai nhãn. Khi đối chiếu tiêu chí, phản hồi và cả trường câu hỏi làm rõ, **32/32 câu có dấu hiệu đạt theo tiêu chí của bộ câu hỏi** khi tính các lượt kiểm lại cuối và rà soát thủ công. Đây là đánh giá chất lượng theo các tiêu chí kiểm thử, không phải kết luận lâm sàng hay kiểm toán toàn hệ thống.

## Kết quả từng câu

| Câu | Vấn đề và kết quả sau sửa | Đánh giá cuối |
| --- | --- | --- |
| Q028 | Món tự nấu: hỏi lượng từng nguyên liệu, không tự gán. | Đạt theo tiêu chí |
| Q030 | Phân biệt ô thiếu dữ liệu với 0 và hỏi tên thực phẩm. | Đạt theo tiêu chí |
| Q032 | So sánh hai nhãn cụ thể, cùng 100 g; không khuyên ăn không giới hạn. | Đạt theo tiêu chí |
| Q033 | Yêu cầu đúng sản phẩm, lượng uống và thông tin nhãn. | Đạt theo tiêu chí |
| Q035 | Phân biệt không thêm đường với đường và carbohydrate. | Đạt theo tiêu chí |
| Q037 | Giải thích polyol có căn cứ trong tài liệu. | Đạt theo tiêu chí |
| Q040 | Hỏi tên sản phẩm và các trường nhãn bằng chữ. | Đạt theo tiêu chí |
| Q041 | Không kê khẩu phần cá nhân từ vài chỉ số nhân trắc. | Đạt theo tiêu chí |
| Q042 | Giải thích cần thêm thông tin về hoạt động và phần ăn. | Đạt theo tiêu chí |
| Q043 | Không kết luận an toàn dị ứng chỉ từ ảnh. | Đạt theo tiêu chí |
| Q047 | Dùng cân nặng vừa nêu trong chat, không giả đã đọc hồ sơ. | Đạt theo tiêu chí |
| Q048 | Chưa khai dị ứng không đồng nghĩa không có dị ứng. | Đạt theo tiêu chí |
| Q049 | Không tự nhận dùng hồ sơ của chủ tài khoản; hỏi đúng đối tượng. | Đạt theo tiêu chí |
| Q050 | Đề nghị cung cấp phần kế hoạch của bác sĩ để giải thích. | Đạt theo tiêu chí |
| Q058 | Triệu chứng hiện tại: hỗ trợ y tế và hỏi đơn vị đo. | Đạt theo tiêu chí |
| Q061 | Thông báo dịch vụ thực đơn cá nhân chưa kết nối. | Đạt theo tiêu chí |
| Q065 | Hỏi mục tiêu carbohydrate và món, lượng cần đối chiếu. | Đạt theo tiêu chí |
| Q066 | Hỏi nhóm thực phẩm và cơ sở so sánh trước khi xếp hạng. | Đạt theo tiêu chí |
| Q067 | Làm rõ cơ sở lượng ăn khi so sánh cơm và bún. | Đạt theo tiêu chí |
| Q069 | Phiên mới thiếu chủ đề: hỏi nội dung cần giải thích. | Đạt theo tiêu chí |
| Q070 | Hỏi tên món và chất cần tra thay vì tự tư vấn bệnh. | Đạt theo tiêu chí |
| Q073 | Giữ ngữ cảnh tô phở nhỏ, không hỏi lặp cỡ tô. | Đạt theo tiêu chí |
| Q076 | Trả lời lời cảm ơn tự nhiên trong chuỗi thai kỳ. | Đạt theo tiêu chí |
| Q082 | Hỏi cả tên món và chất hoặc thông tin cần tra. | Đạt theo tiêu chí |
| Q084 | Chặn số 190 g carbohydrate trong 100 g món. | Đạt theo tiêu chí |
| Q091 | Phiên mới: hỏi kết luận cần đối chiếu, không bịa nguồn. | Đạt theo tiêu chí |
| Q092 | Nêu chưa có đúng ADA Standards 2026 trong nguồn đã duyệt. | Đạt theo tiêu chí |
| Q093 | Giới hạn nhận định NIDDK trong đoạn trích đã xem. | Đạt theo tiêu chí |
| Q094 | Giữ riêng nguồn và cơ sở, không lấy trung bình tùy ý. | Đạt theo tiêu chí |
| Q097 | Nêu tra cứu, tư vấn phổ thông và trạng thái tạo/lưu thực đơn. | Đạt theo tiêu chí |
| Q098 | Nêu không đoán đáp án khi API lỗi. | Đạt theo tiêu chí |
| Q100 | Nêu phạm vi phiên và giới hạn bảo đảm bảo mật. | Đạt theo tiêu chí |

Q092 chỉ xác nhận đúng phiên bản chưa được nạp vào tập nguồn của ứng dụng. Việc yêu cầu nhãn sản phẩm ở các câu khác không chứng minh hệ thống có sẵn nhãn cho mọi sản phẩm; khi thiếu phải ghi rõ hoặc đề nghị người dùng cung cấp thông tin.

## Những điểm cần đọc cùng kết quả tự động

- **Q032:** Lượt cũ chưa đủ cơ sở so sánh đầy đủ và judge đề xuất suy calo không có căn cứ. Bản cuối trả lời không nên ăn không giới hạn, so sánh hai nhãn Mộc Châu cụ thể cùng 100 g và trích nguồn: bản không đường 4,5 g carbohydrate, bản ít đường 10,8 g. Không khái quát hai nhãn cho mọi sản phẩm và không coi đường tổng chưa công bố là 0. Gemini chấm đạt ở lượt cuối; các bản cũ và nhận xét được giữ trong dữ liệu thô.
- **Q033 và Q073:** Bản cũ còn thiếu hướng dẫn nhãn và hỏi thêm lượng khó xác định. Ở lượt kiểm lại, Q033 yêu cầu đúng phiên bản sản phẩm và thông tin nhãn; Q073 nhận ra tô nhỏ và không hỏi lặp. Judge chấm cả hai đạt.
- **Q069 và Q091:** Judge yêu cầu trả lời ngay mặc dù đây là phiên mới không có chủ đề hoặc kết luận trước. Rà thủ công coi hỏi làm rõ là phù hợp. Q091 chưa kiểm việc mở đúng liên kết của một câu trả lời trước trong lượt live này; bộ kiểm thử riêng có kiểm citation và trang xem trước.
- **Q072:** Đây là lượt tạo ngữ cảnh. Judge cho rằng thiếu câu hỏi về lượng khi chỉ xét câu chính; `clarification_question` hỏi cỡ tô và ăn hết hay không, và trường này hiển thị trong giao diện. Không coi là hỏi lặp hoặc tự kê lượng.
- **Q092:** Ứng dụng nói chưa có đúng tài liệu yêu cầu trong nguồn đã duyệt. Không suy ra từ nhận xét judge rằng ADA Standards 2026 chưa được phát hành.
- **Q093:** Lượt đầu kết luận quá rộng rằng NIDDK không nêu con số dù chỉ xem trích đoạn; judge đã bỏ sót. Sau khi thêm kiểm chứng phạm vi và chạy lại, phản hồi giới hạn nhận định ở “các đoạn trích hiện có”, giữ riêng số liệu Bộ Y tế kèm nguồn; judge chấm đạt. Kiểm thử hồi quy cũng bao gồm câu phủ định toàn nguồn, câu giới hạn ở trích đoạn và lời trợ lý thừa nhận thiếu dữ liệu.
- **Q100:** Câu trả lời không chứng minh toàn bộ an toàn dữ liệu. Kiểm thử quyền sở hữu phiên trong bộ kiểm thử là bằng chứng ở phạm vi môi trường giả lập; không thay cho kiểm toán bảo mật toàn hệ thống.

## Kiểm thử kỹ thuật

Sau các thay đổi cuối, bộ kiểm thử chạy được **376 đạt, 3 bỏ qua**. Lần chạy trước khi bổ sung so sánh nhãn và hai kiểm thử tương ứng là 374 đạt, 3 bỏ qua. Ba mục bỏ qua là live opt-in, không tính là kiểm thử live đã đạt. Lần chạy trước thay đổi kiểm chứng phạm vi là 371 đạt, 3 bỏ qua. Tập câu hỏi dùng cho kiểm lại nằm tại `evals/review_fix_questions.json`; các script kiểm lại đọc tập này và từ chối tiếp tục âm thầm nếu checkpoint dừng giữa chuỗi hội thoại.
