"""Audited BYT 2020 reference arithmetic, never a prescribed calorie target."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import re

from rag_app.config import ROOT
from rag_app.domain import Hit
from rag_app.ingestion import load_manifest
from rag_app.retrieval import fold

# Technical input limits for this illustration, not diagnostic height thresholds.
MIN_HEIGHT_CM = Decimal('120')
MAX_HEIGHT_CM = Decimal('220')
SOURCE_ID = 'byt5481-nutrition'
PDF_SHA = '305fc9c51d54418f5798e7691d59f94d24545e0dd728945e2225794730694486'
RULE_CHUNKS = (
    ('0c7184e5937a175db113a8e2', 'a5b71a8ca9d5db690dd516a6617f61e0e20390f0959f1cce2be27ec7605124b4', [30, 31], [28, 29]),
    ('4ae5210f8b40a693facd02fc', '4aceef19c0ee87b1b40a8d638482659cee3e041c8ad51e64e09968818741a629', [31], [29]),
)


def is_daily_energy_question(message):
    text = fold(message)
    if re.search(r'\b(?:bmr|tdee|chuyen hoa co ban|tieu hao|dot|tap luyen|chay bo|thuc don|thuc pham)\b|\d+\s*(?:g|gram|gam|ml)\b', text):
        return False
    return bool(re.search(r'\b(?:calo|kcal|calorie|nang luong)\b', text)
                and re.search(r'\b(?:ngay|daily)\b', text)
                and re.search(r'\b(?:bao nhieu|nhu cau|nen|can|an|nap|tieu thu)\b', text))


def verified_rule_hits(settings, chunks):
    """A withdrawn source, changed file/chunk/unit or metadata cannot authorize arithmetic."""
    try:
        manifest = load_manifest(settings.source_manifest)
        sources = [s for s in manifest['sources'] if s['id'] == SOURCE_ID]
        if len(sources) != 1:
            return []
        source = sources[0]
        if (source.get('enabled') is not True or source.get('role') != 'knowledge'
                or source.get('filename') != 'dinh-kem-16.pdf' or source.get('sha256') != PDF_SHA
                or source.get('year') != 2020):
            return []
        path = ROOT / 'data' / 'dinh-kem-16.pdf'
        if hashlib.sha256(path.read_bytes()).hexdigest() != PDF_SHA:
            return []
        hits = []
        for chunk_id, text_sha, pages, printed_pages in RULE_CHUNKS:
            matches = [c for c in chunks if c.id == chunk_id]
            if len(matches) != 1:
                return []
            chunk = matches[0]
            if (chunk.source_id != SOURCE_ID or chunk.sha256 != PDF_SHA
                    or hashlib.sha256(chunk.text.encode('utf-8')).hexdigest() != text_sha
                    or chunk.filename != source['filename'] or chunk.title != source['title']
                    or chunk.source_url != source['url'] or chunk.year != 2020
                    or chunk.version != source['version'] or chunk.document_format != 'pdf'
                    or chunk.section != '5.2.2. Kiểm soát cân nặng:'
                    or chunk.pages != pages or chunk.printed_pages != printed_pages):
                return []
            hits.append(Hit(chunk=chunk, score=1))
        # Text fingerprints also pin m, kcal/kg ideal weight/day and both constants.
        return hits
    except (OSError, ValueError, KeyError, TypeError):
        return []


@dataclass(frozen=True)
class ReferenceRange:
    height_m: Decimal
    ideal_weight_kg: Decimal
    minimum_kcal: Decimal
    maximum_kcal: Decimal


def calculate_reference_range(height_cm):
    cm = Decimal(str(height_cm))
    if not cm.is_finite() or not MIN_HEIGHT_CM <= cm <= MAX_HEIGHT_CM:
        raise ValueError('Height outside technical illustration limits (120-220 cm)')
    height = cm / Decimal('100')
    ideal = height * height * Decimal('22')
    return ReferenceRange(height, ideal, ideal * Decimal('20'), ideal * Decimal('30'))


def display_decimal(value):
    return format(value.normalize(), 'f').replace('.', ',')


@dataclass
class EnergyReferenceReply:
    answer: str
    status: str
    hits: list[Hit]
    question: str | None = None


def reference_reply(settings, chunks, profile, *, mock=False):
    if profile is None:
        return EnergyReferenceReply('Mình chưa đọc được hồ sơ backend để biết tuổi, chiều cao và phạm vi hỗ trợ. '
                                    'Khung tham khảo này cần chiều cao và hồ sơ đã xác nhận là người trưởng thành mắc đái tháo đường type 2; '
                                    'chỉ cân nặng chưa đủ để tính theo công thức của nguồn.', 'needs_clarification', [],
                                    'Bạn hãy cập nhật tuổi, chiều cao (cm) và phạm vi hỗ trợ trong hồ sơ nhé.')
    version = profile.profile_version
    if profile.scope_status == 'out_of_scope' or profile.age is not None and profile.age < 18:
        return EnergyReferenceReply('Hồ sơ hiện tại nằm ngoài phạm vi người trưởng thành mắc đái tháo đường type 2; '
                                    'mình chưa áp khung năng lượng này cho bạn. Bạn cần trao đổi với chuyên gia để có hướng dẫn phù hợp.', 'safety', [])
    missing = []
    if profile.age is None:
        missing.append('tuổi')
    if profile.height is None:
        missing.append('chiều cao (cm)')
    if profile.scope_status != 'eligible':
        missing.append('xác nhận phạm vi người trưởng thành mắc đái tháo đường type 2')
    if missing:
        known = f"Hồ sơ backend phiên bản {version}"
        if profile.weight is not None:
            known += f" đã ghi cân nặng {display_decimal(Decimal(str(profile.weight)))} kg"
        return EnergyReferenceReply(known + ' nhưng còn thiếu ' + ', '.join(missing) + '. '
                                    'Nguồn dùng cân nặng lý tưởng tính từ chiều cao, nên mình chưa thể tính chỉ từ cân nặng hiện tại.',
                                    'needs_clarification', [], 'Bạn hãy cập nhật ' + ', '.join(missing) + ' trong hồ sơ nhé.')
    if not MIN_HEIGHT_CM <= Decimal(str(profile.height)) <= MAX_HEIGHT_CM:
        return EnergyReferenceReply(f'Hồ sơ backend phiên bản {version} đang ghi chiều cao {profile.height:g} cm. '
                                    'Phép minh họa này chỉ hỗ trợ đầu vào 120–220 cm để hạn chế nhầm đơn vị; đây không phải ngưỡng chẩn đoán. '
                                    'Mình chưa tính calo hoặc tự đổi số đo của bạn.', 'needs_clarification', [],
                                    'Bạn hãy kiểm tra và cập nhật chiều cao theo cm; nếu số đo đúng nhưng ngoài phạm vi minh họa, cần hướng dẫn riêng từ chuyên gia.')
    hits = verified_rule_hits(settings, chunks)
    if not hits:
        return EnergyReferenceReply(f'Mình đã đọc hồ sơ backend phiên bản {version}, nhưng chưa xác minh được đầy đủ hai đoạn nguồn BYT 2020 cho phép tính này. '
                                    'Mình chưa tính khoảng calo hoặc thay mục tiêu thực đơn khi nguồn chưa hợp lệ.', 'insufficient_evidence', [])
    result = calculate_reference_range(profile.height)
    low, high = [value.quantize(Decimal('1E1'), rounding=ROUND_HALF_UP) for value in (result.minimum_kcal, result.maximum_kcal)]
    label = 'hồ sơ giả lập' if mock else 'hồ sơ backend'
    answer = (f'Khoảng tham khảo khởi đầu theo công thức BYT 2020 là {low:.0f}–{high:.0f} kcal/ngày (làm tròn khoảng 10 kcal), '
              f'minh họa theo {label} phiên bản {version}. [C1][C2]\n\n'
              f'Chiều cao đang lưu: {display_decimal(result.height_m)} m. Công thức BYT 2020: cân nặng lý tưởng = '
              f'{display_decimal(result.height_m)} × {display_decimal(result.height_m)} × 22 = {display_decimal(result.ideal_weight_kg)} kg. [C1] '
              f'Lấy cân nặng lý tưởng này × 20–30 kcal/kg/ngày, được {display_decimal(result.minimum_kcal)}–{display_decimal(result.maximum_kcal)} kcal/ngày trước làm tròn. [C2]\n\n'
              'Công thức dựa trên chiều cao, không nhân trực tiếp cân nặng hiện tại; đổi cân nặng mà giữ chiều cao sẽ không đổi khoảng này. '
              'Khung này chưa hiệu chỉnh theo vận động, mục tiêu hay điều trị; cần bác sĩ/chuyên gia cá nhân hóa trước khi chọn mức ăn cố định, '
              'và không thay mục tiêu thực đơn đang lưu. [C1][C2]')
    return EnergyReferenceReply(answer, 'answered', hits)
