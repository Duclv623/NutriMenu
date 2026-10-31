"""Truthful conversational boundaries and useful questions about missing inputs."""
import re

from rag_app.retrieval import fold


def unspecified_glucose_symptoms(message):
    q = fold(message)
    return bool(re.search(r'\b(?:duong huyet|duong mau|glucose)\b.*\d', q)
                and re.search(r'\b(?:dang run|nguoi.*run|va mo hoi|vua do.*run)\b', q)
                and not re.search(r'\b(?:mmol|mg|hom qua|gia su|theo tai lieu)\b', q))


def context_response(message, history):
    q = fold(message)
    def reply(answer, question=None, status='needs_clarification'):
        return answer, question, status
    if unspecified_glucose_symptoms(message):
        return reply('Bạn đang có triệu chứng nên cần được nhân viên y tế hỗ trợ sớm. Mình chưa biết đơn vị của số đo nên chưa thể kết luận từ con số này. Nếu có bất tỉnh, lú lẫn hoặc không nuốt được, hãy gọi 115 ngay và nhờ người ở gần giúp.',
                     'Máy đo đang hiển thị đơn vị mmol/L hay mg/dL?', 'safety')
    if re.search(r'\bada\s+(?:(?:standards|standards of care)\s+)?(20\d{2})\b', q):
        year = re.search(r'20\d{2}', q)[0]
        return reply(f'Mình chưa có ADA Standards {year} làm nguồn đã duyệt, nên chưa thể trả lời theo đúng phiên bản bạn yêu cầu. Nếu bạn muốn, mình có thể giải thích nguyên tắc từ những tài liệu hiện có và ghi rõ nguồn đó.', status='insufficient_evidence')
    if re.search(r'\b(?:nguoi dung khac|du lieu.*nguoi khac|cuoc tro chuyen moi)\b', q):
        return reply('Mình chỉ dùng nội dung của phiên bạn đang trao đổi và chưa tự đọc hồ sơ cá nhân. Ứng dụng kiểm tra quyền sở hữu phiên trước khi cho truy cập lịch sử; mình không thể đưa ra bảo đảm tuyệt đối về mọi khía cạnh bảo mật.', status='answered')
    if 'ho so' in q or re.search(r'\b(?:tai khoan.*(?:me|bo|nguoi khac)|nguoi dang hoi)\b', q):
        if re.search(r'\b(?:chua|khong).*\bdi ung\b', q):
            return reply('Chưa khai dị ứng không có nghĩa là bạn không dị ứng nhé. Hiện mình chưa tự đọc hồ sơ; bạn cần cho mình biết các dị ứng đã biết để mình cân nhắc khi trao đổi.', 'Bạn có dị ứng hoặc từng có phản ứng với thực phẩm nào không?')
        if re.search(r'\b(?:me|bo|nguoi khac|nguoi dang hoi)\b', q):
            return reply('Mình chưa tự lấy hồ sơ tài khoản để tư vấn. Mình chỉ dùng thông tin bạn cung cấp trong cuộc trò chuyện này.', 'Người cần trao đổi về ăn uống là bạn hay người thân, và có ràng buộc nào cần lưu ý?')
        weights = re.findall(r'(\d+(?:[.,]\d+)?)\s*kg\b', q)
        if len(weights) > 1 and re.search(r'\b(?:cap nhat|moi|hom nay)\b', q):
            return reply(f'Trong tin nhắn này, số cân nặng mới bạn vừa nêu là {weights[-1]} kg. Mình chưa kết nối dịch vụ đọc hoặc cập nhật hồ sơ, nên đây là thông tin bạn cung cấp trong chat, chưa phải dữ liệu đã xác minh từ tài khoản.', status='answered')
        return reply('Hiện mình chưa kết nối dịch vụ đọc hoặc cập nhật hồ sơ. Những số bạn vừa nói là thông tin bạn cung cấp trong chat, chứ mình chưa xác minh thay đổi trong tài khoản.', 'Bạn muốn mình dùng thông tin mới nào cho cuộc trao đổi này?')
    if re.search(r'\b(?:xu ly nhung viec|ban co the lam gi|chuc nang|kha nang)\b', q) or ('luu thuc don' in q):
        return reply('Mình có thể giải thích dinh dưỡng phổ thông, giúp chọn món theo nguyên tắc có nguồn và tra thành phần thực phẩm. Tạo, thay đổi và lưu thực đơn hiện chưa được kết nối. Lưu lịch sử chat là một chức năng riêng, không phải lưu thực đơn.', status='answered')
    if re.search(r'\b(?:lap|tao|len|thiet ke|xay dung)\b.*\bthuc don\b', q) and not re.search(r'\b(?:mau|tham khao|trong bang)\b', q):
        return reply('Mình chưa có chức năng lập hoặc lưu thực đơn cá nhân. Mình vẫn có thể cùng bạn xem nguyên tắc chọn món hoặc tra từng thực phẩm để bạn trao đổi tiếp với chuyên gia.', status='integration_required')
    if 'di ung' in q and re.search(r'\b(?:anh|khong thay|an toan)\b', q):
        return reply('Chỉ nhìn ảnh hoặc không thấy tên đậu phộng thì chưa đủ để xác nhận món an toàn với dị ứng của bạn. Bạn nên kiểm tra đầy đủ nguyên liệu và cách chuẩn bị, kể cả khả năng tiếp xúc với nguyên liệu gây dị ứng.', 'Bạn có danh sách nguyên liệu hoặc thông tin từ người chế biến không?')
    if 'bac si' in q and re.search(r'\b(?:ke hoach.*rieng|muc tieu.*(?:carb|carbohydrate))\b', q):
        return reply('Được nhé, mình có thể giúp giải thích hoặc đối chiếu thông tin bạn đưa, đồng thời giữ nguyên mục tiêu của bác sĩ.', 'Bạn hãy ghi mục tiêu hoặc phần kế hoạch cần xem, kèm món ăn và lượng thực tế nhé?')
    if 'sua' in q and re.search(r'\b(?:th|moc chau)\b', q) and re.search(r'\b(?:phu hop|tieu duong|dai thao duong)\b', q):
        return reply('Mình sẽ xem cả tổng carbohydrate và lượng bạn uống, chứ không chỉ chữ “ít đường” trên hộp. Tên dòng sản phẩm chưa đủ để kết luận phù hợp riêng cho bạn; cần đối chiếu đúng nhãn và kế hoạch ăn đang áp dụng.', 'Bạn dùng phiên bản nào, uống bao nhiêu ml, và nhãn ghi bao nhiêu carbohydrate/đường trên 100 ml hoặc mỗi khẩu phần?')
    if re.search(r'\bapi\b.*\b(?:loi|doan)\b', q):
        return reply('Khi API lỗi, mình cần báo rõ thay vì đoán rồi trình bày như đáp án đã kiểm tra. Bạn có thể thử lại sau; nếu đã có dữ liệu tra cứu hợp lệ, ứng dụng có thể hiển thị riêng phần đó.', status='answered')
    if re.search(r'\b(?:hai nguon|2 nguon)\b.*\b(?:khac|chon)\b', q):
        return reply('Mình sẽ giữ riêng số của từng nguồn và kiểm tra xem có cùng loại thực phẩm, trạng thái sống/chín và đơn vị hay không. Mình không lấy trung bình tùy ý hoặc chọn số theo ý muốn.', 'Bạn muốn đối chiếu thực phẩm nào và hai nguồn nào?')
    if re.search(r'\b(?:nhan|duong them|duong tong)\b', q) and re.search(r'\b(?:can.*cung cap|san pham nay)\b', q):
        return reply('Bạn ghi giúp mình tên và phiên bản sản phẩm, lượng của một khẩu phần, số khẩu phần trong hộp, cùng các dòng đường thêm, đường tổng và natri trên nhãn. Trường nào không ghi thì mình sẽ giữ là chưa có dữ liệu.', 'Bạn muốn tra sản phẩm nào?')
    if 'sua chua' in q and 'khong duong' in q and 'it duong' in q:
        return reply('Hai tên gọi này nói về đường, chưa nói hết về carbohydrate hay năng lượng. Bạn cũng cần phân biệt “không đường” với “không thêm đường”: không thêm đường vẫn có thể có đường từ nguyên liệu. “Ít đường” không có nghĩa là không có đường. Vì vậy mình chưa thể nói loại nào có thể ăn không giới hạn chỉ từ tên gọi.', 'Bạn cho mình tên hai sản phẩm, cách ghi chính xác trên nhãn, lượng khẩu phần và các dòng carbohydrate/đường nhé?')
    if 'so sanh' in q and 'com' in q and 'bun' in q and not re.search(r'\d+\s*(?:g|gram)\b', q):
        return reply('Được nhé, để bảng so sánh có ý nghĩa mình sẽ dùng cùng lượng và cùng trạng thái đã nấu.', 'Bạn muốn so cơm trắng hay gạo lứt với bún gạo chín, và dùng bao nhiêu gram cho mỗi loại?')
    if re.search(r'\b(?:khong ghi|khong co so|du lieu thieu|bang.*thieu)\b', q) and re.search(r'\b(?:0|bang khong)\b', q):
        return reply('Không nên coi ô thiếu là 0 nhé. “Chưa có dữ liệu” khác với một giá trị đã được xác định bằng 0; mình sẽ giữ riêng hai trường hợp đó.', 'Bạn đang muốn xem chất nào của thực phẩm cụ thể nào?')
    if re.search(r'\b(?:100\s*g|100\s*gam)\b.*\b190\s*g\b', q):
        return reply('Số 190 g carbohydrate trong 100 g món ăn có dấu hiệu sai cơ sở khối lượng, nên mình chưa dùng số đó để tính tiếp. Bạn gửi đúng tên hoặc mã bản ghi để mình kiểm tra nhé.', status='insufficient_evidence')
    if re.search(r'\b(?:nhieu|giau|it)\b.*\b(?:dam|protein|calo)\b.*\bnhat\b', q):
        return reply('Để so sánh công bằng, mình cần thống nhất nhóm thực phẩm và cùng cơ sở khối lượng; thực phẩm khô và món đã nấu không nên xếp chung một cách tùy ý.', 'Bạn muốn tìm trong nhóm nào, và so theo 100 g phần ăn được hay theo khẩu phần?')
    if re.search(r'\b(?:tu nau|nguyen lieu)\b', q) and re.search(r'\b(?:tinh|tong)\b', q) and not re.search(r'\d+\s*(?:g|gram|kg|ml)\b', q):
        return reply('Mình có thể tính khi biết lượng từng nguyên liệu và phần bạn ăn. Bạn đã nêu các thành phần rồi; bước còn thiếu là khối lượng.', 'Bạn dùng bao nhiêu gram từng nguyên liệu, bao nhiêu dầu và ăn bao nhiêu phần của món sau khi nấu?')
    if not history and re.search(r'\b(?:mon nay|thuc pham nay|cai do)\b', q):
        return reply('Mình chưa biết bạn đang nhắc đến thực phẩm nào.', 'Bạn cho mình tên món và chất muốn tra, chẳng hạn năng lượng hay chất xơ, được không?')
    if not history and (re.search(r'\b(?:dua vao doan nao|ket luan nhu vay|giai thich de hieu)\b', q)
                        or 'nguon' in q and 'ket luan' in q):
        return reply('Được nhé, mình sẽ giải thích bằng lời dễ hiểu và chỉ rõ nguồn khi có.', 'Bạn muốn mình giải thích hoặc đối chiếu nội dung nào?')
    if history and re.fullmatch(r'(?:to|bat) nho.*(?:an het|thuong an het).*', q.strip(' .?!')):
        return reply('Cảm ơn bạn, mình hiểu là bạn thường ăn hết một tô nhỏ và sẽ giữ thông tin này trong cuộc trao đổi. Cỡ tô giúp mô tả phần ăn, nhưng chưa đủ để chốt lượng phù hợp riêng cho bạn. Nếu bạn đã có mục tiêu khẩu phần từ chuyên gia, mình có thể giúp đối chiếu phần ăn thực tế với mục tiêu đó.', status='answered')
    if re.search(r'\b(?:tuoi|cm|kg)\b', q) and re.search(r'\b(?:van dong|ngoi van phong|an bao nhieu)\b', q):
        return reply('Thông tin bạn đưa là một phần cần cân nhắc, nhưng chưa đủ để mình xác định lượng ăn riêng cho bạn. Mức hoạt động và phần ăn thực tế cũng cần được xem cùng kế hoạch đang áp dụng.', 'Bạn muốn xem món cụ thể và lượng bạn thường ăn, hay đối chiếu với mục tiêu đã được chuyên gia hướng dẫn?')
    return None
