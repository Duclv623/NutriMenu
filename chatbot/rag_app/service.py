import logging
import re
import threading
import time
from collections import OrderedDict
from uuid import uuid4

from rag_app.chroma_index import ChromaIndexError
from rag_app.config import Settings
from rag_app.conversation import (
    active_topic_history,
    switches_to_self,
    describes_relative_condition,
    is_contextual_followup,
    is_portion_description,
    starts_new_topic,
    topic_for_turn,
)
from rag_app.cooking_reference import (
    COOKING_SOURCE_IDS,
    GROUND_MEAT_TEMPERATURE,
    USDA_GROUND_MEAT,
    cooking_reference_reply,
    direct_cooking_revision,
    uses_ground_meat,
)
from rag_app.dialogue import context_response
from rag_app.domain import ChatRequest, ChatResponse, Citation, GeneratedAnswer, Hit
from rag_app.energy_reference import is_daily_energy_question, reference_reply
from rag_app.food_data import food_hits, format_energy_comparison, get_catalog
from rag_app.history_store import HistoryStoreError
from rag_app.meal_chat import handle_meal_chat, meal_action, saved_day_nutrition
from rag_app.meal_gateway import MealServiceError, create_meal_gateway
from rag_app.meal_models import MealContext
from rag_app.nutrition_reference import (
    label_calculation,
    published_portion_energy,
    nutrition_reference_reply,
    nutrition_reference_topic,
)
from rag_app.provider import BackendProfileQuestion, Provider, ProviderFailure, redact
from rag_app.retrieval import Retriever, fold
from rag_app.routing import (
    constrain_plan,
    culinary_request,
    direct_text_is_allowed,
    label_reading_request,
)
from rag_app.safety import (
    DISCLAIMER,
    classify,
    emergency_answer,
    is_diagnosis_request,
    is_elliptical_intake_followup,
    is_intake_advice,
    is_intake_quantity_request,
    outside_nutrition_scope,
    social_answer,
    static_answer,
)
from rag_app.store import Store
from rag_app.supplements import SupplementCatalog

logger = logging.getLogger(__name__)


def make_citations(hits: list[Hit]) -> list[Citation]:
    return [
        Citation(
            id=f"C{i}",
            chunk_id=h.chunk.id,
            source_id=h.chunk.source_id,
            title=h.chunk.title,
            section=h.chunk.section,
            pdf_pages=h.chunk.pages,
            printed_pages=h.chunk.printed_pages,
            quote=h.chunk.text,
            source_url=h.chunk.source_url,
            document_url=(f"/api/documents/{h.chunk.source_id}/pdf#page={h.chunk.pages[0]}"
                          if h.chunk.document_format == "pdf" and h.chunk.pages else
                          '/api/supplements' if h.chunk.id == 'supp-lookup-context' else
                          f'/api/supplements/{h.chunk.id}/preview' if h.chunk.id.startswith('supp-') else
                          '/api/foods' if h.chunk.id == 'lookup-context' else
                          f"/api/foods/{h.chunk.id}/preview" if h.chunk.document_format == 'structured' else
                          f"/api/documents/{h.chunk.source_id}/preview#chunk-{h.chunk.id}"),
            year=h.chunk.year,
            version=h.chunk.version,
            document_format=h.chunk.document_format,
            locators=h.chunk.locators,
        )
        for i, h in enumerate(hits, 1)
    ]


def validate_answer(generated: GeneratedAnswer, citations: list[Citation]):
    """Final atomic guard; semantic partial acceptance belongs to the provider review.

    Dropping arbitrary blocks here could remove a qualification that makes another
    block safe. The provider already retains individually reviewed partial answers.
    """
    available = {c.id: c for c in citations}
    if not generated.supported or not generated.blocks:
        return None
    used = []
    blocks = []
    for block in generated.blocks:
        ids = list(dict.fromkeys(block.citation_ids))
        if not block.text.strip() or not ids or any(i not in available for i in ids):
            logger.warning('answer_rejected reason=invalid_citation_or_empty_block')
            return None
        # The model is not allowed to fabricate source links or apparent additional citations.
        if re.search(r"https?://|\[C\d+\]", block.text):
            logger.warning('answer_rejected reason=unapproved_link_or_marker')
            return None
        if classify(block.text) == "medication":
            logger.warning('answer_rejected reason=medication_instruction')
            return None
        blocks.append(block.text.strip() + " " + " ".join(f"[{i}]" for i in ids))
        used.extend(ids)
    # This is a system statement about the checked answer's limits, not an
    # evidence block or a new medical conclusion. It intentionally has no citation.
    if 'intake_suitability_decision' in (generated._grounding_review or {}).get('unresolved_goals', []):
        blocks.insert(0, 'Mình chưa đủ căn cứ từ các đoạn trích đã kiểm tra để kết luận món này phù hợp riêng cho bạn.')
    return "\n\n".join(blocks), [available[i] for i in dict.fromkeys(used)]


class ChatService:
    def __init__(self, settings: Settings, store: Store, provider: Provider | None = None, meal_gateway=None):
        self.settings = settings
        self.store = store
        self.provider = provider
        self.meals = meal_gateway if meal_gateway is not None else create_meal_gateway(settings)
        self.foods = get_catalog()
        self.supplements = SupplementCatalog()
        self._retriever = None
        self._retriever_lock = threading.Lock()
        self._profile_epochs = {}
        self._session_profile_epochs = {}
        self._transient = {}
        self._session_lock = threading.Lock()
        self._meal_edit_lock = threading.RLock()
        self._revoked_meal_proposals = {}
        self._meal_profile_blocks = {}
        # Only vectors are reused; knowledge answers use the real API.
        # Volatile bounded cache avoids persisting user questions without consent.
        self._query_vectors = OrderedDict()
        self._query_vector_lock = threading.Lock()

    def query_vector(self, query):
        import hashlib
        key = hashlib.sha256((self.settings.embedding_identity + '\0' + query).encode()).hexdigest()
        now = time.monotonic()
        with self._query_vector_lock:
            cached = self._query_vectors.get(key)
            if cached and now - cached[0] < 600:
                self._query_vectors.move_to_end(key)
                return cached[1], True
        vector = self.provider.embed([query])[0]
        with self._query_vector_lock:
            self._query_vectors[key] = (time.monotonic(), vector)
            self._query_vectors.move_to_end(key)
            while len(self._query_vectors) > 128:
                self._query_vectors.popitem(last=False)
        return vector, False

    def transient_history(self, owner, session):
        with self._session_lock:
            now = time.monotonic()
            self._transient = {sid: value for sid, value in self._transient.items() if now - value[1] < 1800}
            value = self._transient.get(str(session))
            if value is not None:
                if value[0] != owner:
                    raise PermissionError('Session không tồn tại hoặc không thuộc người dùng')
                return list(value[2])
        return None

    def remember_turn(self, owner, session, history, query, response):
        # Volatile context is separate from opt-in disk history. Keep only the
        # fields used to resolve follow-ups, not full nutrition/source tables.
        result = response.food_result
        context = None if result is None else {
            'request': result.get('request'), 'unresolved': result.get('unresolved', []),
            'comparison_question': result.get('comparison_question'),
            'items': [{'id': i['id'], 'name': i['name']} for i in result.get('items', [])],
        }
        reference=response.reference_result
        ref_context=None if reference is None else {
            'domain':reference['domain'],'request':reference['request'],'unresolved':reference['unresolved'],
            'items':[{'id':i['id'],'name':i['name']} for i in reference['items']]}
        topic = topic_for_turn(query, history)
        turn = {'question': query, 'topic': topic[:1000], 'response': {'food_result': context,'reference_result':ref_context,
                                              'answer': redact(response.answer)[:3000],
                                              'response_strategy': response.response_strategy,
                                              'cooking_suggestion': response.status == 'answered' and (
                                                  getattr(response, '_cooking_suggestion', False)
                                                  or any(c.source_id in COOKING_SOURCE_IDS for c in response.citations)
                                              ),
                                              'clarification_question': response.clarification_question,
                                              'meal_context': response.meal_result.get('context') if response.meal_result else None,
                                              'meal_view': response.meal_result.get('view') if response.meal_result else None,
                                              'meal_pending': self.meal_pending(response.meal_result),
                                              'meal_choices': response.meal_result.get('choices') if response.meal_result else None,
                                              'meal_choice_instruction': response.meal_result.get('choiceInstruction') if response.meal_result else None,
                                              'meal_edit_cancelled': response.meal_edit_cancelled,
                                              'scope_restriction': response.scope_restriction,
                                              'restriction_for_relative': response.restriction_for_relative}}
        trimmed = []
        for previous in history[-5:]:
            old = previous.get('response', {}).get('food_result')
            trimmed.append({'question': previous['question'], 'topic': previous.get('topic', previous['question'])[:1000], 'response': {
                'scope_restriction': previous.get('response', {}).get('scope_restriction'),
                'restriction_for_relative': previous.get('response', {}).get('restriction_for_relative', False),
                'answer': previous.get('response', {}).get('answer', '')[:3000],
                'response_strategy': previous.get('response', {}).get('response_strategy'),
                'cooking_suggestion': previous.get('response', {}).get('cooking_suggestion') or any(
                    c.get('source_id') in COOKING_SOURCE_IDS for c in previous.get('response', {}).get('citations', [])
                ),
                'clarification_question': previous.get('response', {}).get('clarification_question'),
                'meal_context': previous.get('response', {}).get('meal_context') or (previous.get('response', {}).get('meal_result') or {}).get('context'),
                'meal_view': previous.get('response', {}).get('meal_view') or (previous.get('response', {}).get('meal_result') or {}).get('view'),
                'meal_pending': previous.get('response', {}).get('meal_pending') or self.meal_pending(previous.get('response', {}).get('meal_result')),
                'meal_choices': previous.get('response', {}).get('meal_choices') or (previous.get('response', {}).get('meal_result') or {}).get('choices'),
                'meal_choice_instruction': previous.get('response', {}).get('meal_choice_instruction') or (previous.get('response', {}).get('meal_result') or {}).get('choiceInstruction'),
                'meal_edit_cancelled': previous.get('response', {}).get('meal_edit_cancelled', False),
                'reference_result':previous.get('response',{}).get('reference_result'),'food_result': None if old is None else {
                'request': old.get('request'), 'unresolved': old.get('unresolved', []),
                'comparison_question': old.get('comparison_question'),
                'items': [{'id': i['id'], 'name': i['name']} for i in old.get('items', [])],
            }}})
        with self._session_lock:
            self._transient[str(session)] = (owner, time.monotonic(), trimmed + [turn])
            if len(self._transient) > 200:
                oldest = min(self._transient, key=lambda sid: self._transient[sid][1])
                del self._transient[oldest]

    def forget_session(self, owner, session):
        with self._session_lock:
            value = self._transient.get(str(session))
            if value is not None and value[0] == owner:
                del self._transient[str(session)]

    def retriever(self):
        revision = self.store.index_revision()
        with self._retriever_lock:
            if self._retriever is None or self._retriever.metadata.get('revision') != revision:
                chroma_path = self.store.path
                try:
                    self._retriever = Retriever(self.store, chroma_path=chroma_path)
                except ChromaIndexError as error:
                    raise ProviderFailure(str(error)) from error
            return self._retriever

    def profile_changed(self, owner):
        with self._session_lock:
            self._profile_epochs[owner] = self._profile_epochs.get(owner, 0) + 1
        with self._meal_edit_lock:
            self._meal_profile_blocks.pop(owner, None)

    def chat(self, request: ChatRequest, owner: str, authorization: str | None = None) -> ChatResponse:
        started = time.perf_counter()
        session = request.session_id or uuid4()
        stated_intent = classify(request.message)
        history = []
        if request.session_id:
            history = self.transient_history(owner, session)
            if history is None:
                try:
                    history = self.store.history(owner, str(session), limit=6)
                except HistoryStoreError:
                    if stated_intent != 'emergency':
                        raise
                    # An unavailable store cannot attest ownership. Start a fresh session.
                    session, history = uuid4(), []
        with self._session_lock:
            epoch = self._profile_epochs.get(owner, 0)
            key = (owner, str(session))
            if self._session_profile_epochs.get(key, 0) != epoch:
                history = []
            self._session_profile_epochs[key] = epoch
            if len(self._session_profile_epochs) > 1000:
                self._session_profile_epochs.pop(next(iter(self._session_profile_epochs)))
        provider_client = getattr(self.provider, 'client', None)
        if hasattr(provider_client, 'start_trace'):
            provider_client.start_trace()
        query = re.sub(r'\bko\b', 'không', redact(request.message), flags=re.IGNORECASE)
        raw_query = query
        previous_response = history[-1].get('response', {}) if history else {}
        returning_to_self = previous_response.get('restriction_for_relative') and switches_to_self(query)
        if returning_to_self:
            history, previous_response = [], {}
        topic_reset = returning_to_self or starts_new_topic(query)
        selected_plan = self.foods.resolve_selection(query, history) if not topic_reset else None
        contextual = bool(history) and is_contextual_followup(query, history)
        context_history = active_topic_history(history) if contextual else []
        # A short new subject (e.g. brown rice after bread) is independent.
        # Short follow-ups within an explicit safety condition remain guarded.
        safety_contextual = not topic_reset and (contextual or bool(history) and len(query.split()) < 9)
        # Carry a safety condition through a chain of elliptical follow-ups.
        # A standalone question ends that chain; only user questions count.
        context_intent = None
        emergency_trigger = request.message
        if safety_contextual:
            for previous in reversed(history):
                previous_query = previous["question"]
                if switches_to_self(previous_query) and not previous.get('response', {}).get('scope_restriction'):
                    break
                previous_intent = classify(previous_query)
                if previous_intent in {"special_population", "medication", "emergency"}:
                    context_intent = previous_intent
                    if previous_intent == "emergency" and stated_intent != "emergency":
                        emergency_trigger = previous_query
                    break
                if len(previous_query.split()) >= 9 and not re.search(r"\b(?:con|do|nay|ay|vay)\b", fold(previous_query)):
                    break
        intent = stated_intent
        # A question about comparing cooking states asks about the basis of
        # data, rather than requesting two nutrient lookups for assumed foods.
        conceptual_cooking = bool(
            intent in {'knowledge', 'food_lookup'}
            and re.search(r'\bsong\b', fold(query)) and re.search(r'\bchin\b', fold(query))
            and re.search(r'\b(?:giong nhau|nhu nhau|bang nhau|khac nhau)\b', fold(query)))
        if conceptual_cooking:
            intent = 'knowledge'
        prior_restriction = previous_response.get('scope_restriction') == 'special_population'
        restricted = intent == 'special_population' or prior_restriction
        relative = (not prior_restriction or previous_response.get('restriction_for_relative', False)) and (
            describes_relative_condition(query) if intent == 'special_population' else prior_restriction
        )
        # A declared special population is a session restriction, not a short
        # linguistic follow-up. It survives greetings and long independent questions.
        if restricted and intent in {'knowledge', 'food_lookup', 'menu_request'}:
            intent = 'special_population'
        if context_intent in {"special_population", "medication", "emergency"} and intent in {"knowledge", "food_lookup"}:
            intent = context_intent
        qualitative_request = label_reading_request(query) or culinary_request(query)
        if intent=='knowledge' and not conceptual_cooking and not qualitative_request and not is_intake_advice(query) and (selected_plan is not None or self.foods.looks_like_lookup(query) or contextual and history[-1].get('response',{}).get('food_result')):
            intent='food_lookup'
        reference_domain=self.supplements.detect(query)
        reference_selection=self.supplements.resolve_selection(query,history) if not topic_reset else None
        if reference_selection:
            reference_domain=reference_selection[0]
        elif not reference_domain and contextual and history[-1].get('response',{}).get('reference_result'):
            reference_domain=history[-1]['response']['reference_result']['domain']
        if reference_domain and not conceptual_cooking and not qualitative_request and intent in {'knowledge','food_lookup'}:
            intent='food_lookup'
        response = ChatResponse(
            session_id=session,
            message_id=uuid4(),
            intent=intent,
            status="insufficient_evidence",
            answer=static_answer(intent),
            mode=self.settings.answer_mode,
            warnings=[DISCLAIMER],
            scope_restriction='special_population' if restricted else None,
            restriction_for_relative=bool(relative),
        )
        authoritative = None
        if intent not in {'emergency', 'medication', 'special_population'} and self.meals.mode != 'disabled':
            try:
                authoritative = self.meals.snapshot(owner, authorization).profile
            except MealServiceError:
                pass
        if authoritative is not None:
            object.__setattr__(response, '_backend_profile_version', authoritative.profile_version)
            object.__setattr__(response, '_profile_epoch', epoch)
            object.__setattr__(response, '_profile_authorization', authorization)
        fact_query = fold(request.message)
        weight_fact = re.search(
            r'\b(?:toi|minh|em) (?:hien tai |dang )?(?:nang (?:bao nhieu|may)|bao nhieu kg(?=[.!? ]*$))\b'
            r'|\bcan nang (?:hien tai )?cua (?:toi|minh|em) (?:la )?(?:bao nhieu|may)\b', fact_query)
        other_profile_fact = re.search(
            r'\b(?:toi|minh|em) (?:hien tai |dang )?(?:cao bao nhieu|bao nhieu tuoi|di ung gi)\b'
            r'|\b(?:dang dung ho so|ho so (?:nao|cua toi|hien tai))\b', fact_query)
        if intent not in {'emergency', 'medication', 'special_population'} and (weight_fact or other_profile_fact):
            if authoritative is None:
                response.status = 'integration_required'
                response.response_strategy = 'policy'
                response.answer = "Mình chưa đọc được hồ sơ của bạn để trả lời theo thông tin đã lưu."
                return self.finish_response(response, request, owner, history, query, started)
            p = authoritative
            labels = {'FEMALE': 'nữ', 'MALE': 'nam', 'OTHER': 'khác', 'SEDENTARY': 'ít vận động', 'LIGHT': 'vận động nhẹ', 'MODERATE': 'vận động vừa', 'ACTIVE': 'vận động nhiều', 'MAINTAIN': 'duy trì cân nặng', 'LOSE': 'giảm cân (khai báo)', 'GAIN': 'tăng cân (khai báo)'}
            activity = labels.get(p.activity_level, p.activity_level) or 'chưa khai'
            goal = labels.get(p.goal, p.goal) or 'chưa khai'
            gender = labels.get(p.gender, p.gender) or 'chưa khai'
            response.intent = 'knowledge'
            response.status = 'answered'
            response.response_strategy = 'structured_lookup'
            response.answer = (f"Hồ sơ backend đang dùng: phiên bản {p.profile_version}; tuổi: {p.age if p.age is not None else 'chưa khai'}; "
                               f"giới tính: {gender}; chiều cao: {p.height if p.height is not None else 'chưa khai'} cm; cân nặng: {p.weight if p.weight is not None else 'chưa khai'} kg; "
                               f"vận động: {activity}; mục tiêu: {goal}; "
                               f"dị ứng: {', '.join(p.allergies) if p.allergies else 'chưa khai' if p.allergies is None else 'đã khai không có'}; "
                               f"ưu tiên: {', '.join(p.preferences) or 'chưa khai'}. "
                               + ('Đây là dữ liệu giả lập, không phải hồ sơ tài khoản thật.' if self.meals.mode == 'mock' else 'Đây là dữ kiện hồ sơ, không phải bằng chứng y khoa.'))
            if weight_fact and 'ho so' not in fact_query:
                response.answer = (f"Hồ sơ backend phiên bản {p.profile_version} ghi cân nặng của bạn là {p.weight:g} kg." if p.weight is not None else f"Hồ sơ backend phiên bản {p.profile_version} chưa khai cân nặng.") + (' Đây là dữ liệu giả lập.' if self.meals.mode == 'mock' else '')
            if re.search(r'\b(?:toi|minh) di ung gi\b', fact_query) and 'ho so' not in fact_query:
                allergy_fact = 'chưa khai thông tin dị ứng' if p.allergies is None else ('đã khai không có dị ứng đã biết' if not p.allergies else 'ghi nhận dị ứng: ' + ', '.join(p.allergies))
                response.answer = f"Hồ sơ {'giả lập ' if self.meals.mode == 'mock' else 'backend '}phiên bản {p.profile_version} {allergy_fact}."
            return self.finish_response(response, request, owner, history, query, started)
        personal_advice = bool(re.search(r'\b(?:toi|minh|cua toi|cho toi|cho minh)\b', fact_query)) or is_intake_advice(raw_query)
        if contextual and history:
            personal_advice = personal_advice or is_intake_advice(topic_for_turn(raw_query, history))
        if authoritative is not None and personal_advice and (authoritative.scope_status == 'out_of_scope' or authoritative.age is not None and authoritative.age < 18):
            intent = response.intent = 'special_population'
            response.answer = static_answer(intent)
            response.scope_restriction = 'special_population'
            response.restriction_for_relative = False
        if intent in {"medication", "emergency", "special_population"}:
            response.response_strategy = 'safety'
            response.status = "safety"
            if intent == 'emergency':
                response.answer = emergency_answer(emergency_trigger)
            # Reviewed fixed boundaries must work without network/key/quota.
            # They are explicitly marked static, never presented as an AI answer.
            response.timings_ms['safety_routing'] = int((time.perf_counter() - started) * 1000)
            return self.finish_response(response, request, owner, history, query, started)
        if request.meal_action is None and re.fullmatch(
            r'(?:(?:theo ban|cho hoi)[, ]+)?(?:toi|minh|em) (?:nen|can|phai) (?:giam|tang) '
            r'(?:bao nhieu|may) (?:kg|ky|can|kilogram)(?: (?:thi vua|la du|thi hop ly))?[?!. ]*', fact_query
        ):
            response.intent = 'knowledge'
            response.response_strategy = 'policy'
            response.answer = ("Mình chưa có căn cứ để đưa ra số kg mục tiêu riêng cho bạn. "
                               "Bạn có thể trao đổi với bác sĩ hoặc chuyên gia dinh dưỡng về mục tiêu cân nặng phù hợp.")
            return self.finish_response(response, request, owner, history, query, started)
        if request.meal_action is None and re.search(
            r'\b(?:mua|chuan bi) (?:bao nhieu|may) (?:kg|ky|can|kilogram) gao\b', fact_query
        ) and not re.search(r'\b\d+\s*(?:nguoi|bua|ngay|gam|gram)\b', fact_query):
            response.intent = 'knowledge'
            response.status = 'needs_clarification'
            response.response_strategy = 'policy'
            response.answer = "Để tính lượng gạo cần mua, mình cần biết nhà bạn có mấy người và sẽ nấu mấy bữa."
            response.clarification_question = "Bạn nấu cho bao nhiêu người, bao nhiêu bữa và thường dùng bao nhiêu gạo khô mỗi bữa?"
            return self.finish_response(response, request, owner, history, query, started)
        stored_day = self.meals.mode != 'disabled' and saved_day_nutrition(request.message)
        if request.meal_action is None and not stored_day and is_daily_energy_question(request.message):
            energy = reference_reply(self.settings, self.retriever().chunks, authoritative, mock=self.meals.mode == 'mock')
            response.intent = 'knowledge'
            response.answer = energy.answer
            response.status = energy.status
            response.response_strategy = 'safety' if energy.status == 'safety' else 'structured_lookup'
            response.clarification_question = energy.question
            response.citations = make_citations(energy.hits)
            return self.finish_response(response, request, owner, history, query, started)
        if request.meal_action is None and intent in {"knowledge", "food_lookup"}:
            if label := label_calculation(raw_query, context_history, previous_turn=history[-1] if history and not topic_reset else None):
                response.answer, response.clarification_question = label
                response.intent = 'knowledge'
                response.response_strategy = 'structured_lookup'
                response.status = 'needs_clarification' if response.clarification_question else 'answered'
                return self.finish_response(response, request, owner, history, raw_query, started)
            portion = published_portion_energy(raw_query)
            if portion:
                response.answer, response.citations = portion
                response.intent = 'food_lookup'
                response.response_strategy = 'structured_lookup'
                response.status = 'answered'
                return self.finish_response(response, request, owner, history, raw_query, started)
            cooking = cooking_reference_reply(raw_query, authoritative, followup=contextual)
            if cooking:
                response.answer, response.citations = cooking
                object.__setattr__(response, '_cooking_suggestion', True)
                response.intent = 'knowledge'
                response.response_strategy = 'structured_lookup' if response.citations else 'policy'
                response.status = 'answered'
                return self.finish_response(response, request, owner, history, raw_query, started)
            reference_query = raw_query
            if returning_to_self:
                reference_query = re.split(r'[.;!?]\s*', raw_query.rstrip('?.! '))[-1]
            topic = nutrition_reference_topic(reference_query)
            if topic:
                answer, hits = nutrition_reference_reply(topic, self.settings.source_manifest, self.store, self.foods)
                response.intent = 'knowledge'
                response.response_strategy = 'structured_lookup'
                response.status = 'answered' if hits else 'insufficient_evidence'
                response.answer = answer
                response.citations = make_citations(hits)
                return self.finish_response(response, request, owner, history, raw_query, started)
            if comparison := self.foods.simple_energy_comparison(raw_query):
                response.answer, response.food_result = comparison
                response.citations = make_citations(food_hits(response.food_result))
                response.intent = 'food_lookup'
                response.response_strategy = 'structured_lookup'
                response.status = 'answered'
                return self.finish_response(response, request, owner, history, raw_query, started)
        meal_context = request.meal_context
        if meal_context is None and history and not topic_reset:
            last = history[-1].get('response', {})
            previous_meal = last.get('meal_context') or (last.get('meal_result') or {}).get('context')
            if previous_meal is None and meal_action(request.message, MealContext()) in {'keep', 'accept', 'change_status'}:
                for turn in reversed(history[:-1]):
                    previous = turn.get('response', {})
                    previous_meal = previous.get('meal_context') or (previous.get('meal_result') or {}).get('context')
                    if previous_meal:
                        break
            if previous_meal:
                meal_context = MealContext.model_validate(previous_meal)
        with self._meal_edit_lock:
            meal_reply = handle_meal_chat(self.meals, owner, request.message, meal_context,
                                         request.meal_action, authorization, history=history,
                                         blocked_profile_version=self._meal_profile_blocks.get(owner))
            if meal_reply and meal_reply.cancel_pending:
                self.cancel_meal_proposals(owner, history)
            if meal_reply and meal_reply.profile_recheck_version is not None:
                self._meal_profile_blocks[owner] = meal_reply.profile_recheck_version
        if meal_reply is not None:
            response.intent = 'menu_request'
            response.response_strategy = 'structured_lookup'
            response.answer = meal_reply.answer
            response.status = meal_reply.status
            response.clarification_question = meal_reply.question
            response.meal_result = meal_reply.payload
            if meal_reply.payload and (meal_reply.payload.get('plan') or {}).get('catalogVersion') == 'java-catalog-unversioned':
                response.warnings.extend((meal_reply.payload.get('plan') or {}).get('limitations', []))
                response.warnings.append('Carb của thực đơn này là carbohydrate khả dụng (net carb), không phải đường tổng.')
            if meal_reply.cancel_pending:
                response.meal_edit_cancelled = True
            response.timings_ms['meal_service'] = int((time.perf_counter() - started) * 1000)
            if meal_reply.status == 'safety':
                response.response_strategy = 'safety'
            return self.finish_response(response, request, owner, history, query, started)
        boundary = context_response(raw_query, history)
        if boundary:
            response.answer, response.clarification_question, response.status = boundary
            response.response_strategy = 'safety' if response.status == 'safety' else 'policy'
            if all(term in fold(raw_query) for term in ('sua chua', 'khong duong', 'it duong')):
                example = self.supplements.yogurt_comparison_example()
                if example:
                    response.reference_result = example
                    response.citations = make_citations(self.supplements.hits(example))
                    lines = []
                    for item, citation in zip(example['items'], response.citations, strict=True):
                        n = item['payload']['nutrients']
                        energy = f"{n['energy_kcal']:g}".replace('.', ',')
                        carb = f"{n['carbohydrate_g']:g}".replace('.', ',')
                        lines.append(f"{item['name']}: {energy} kcal và {carb} g carbohydrate trên 100 g. [{citation.id}]")
                    first, second = [item['payload']['nutrients'] for item in example['items']]
                    comparison = ('Ở cặp nhãn này, loại không đường có ít carbohydrate và năng lượng hơn. '
                                  if all(first[key] < second[key] for key in ('carbohydrate_g', 'energy_kcal')) else '')
                    response.answer = (
                        'Mình không thể khuyên ăn không giới hạn chỉ vì tên gọi “không đường” hay “ít đường” nhé. '
                        'Cần xem cả tổng carbohydrate và lượng bạn ăn.\n\n'
                        'Để dễ hình dung, đây là hai nhãn Mộc Châu đã có trong dữ liệu, cùng cơ sở 100 g:\n\n'
                        + '\n\n'.join(lines)
                        + '\n\n' + comparison
                        + 'Tên gọi chưa đủ để kết luận không có carbohydrate. Đây chỉ là ví dụ của đúng hai sản phẩm, không áp cho mọi hãng. '
                        'Với đường tổng, mình không coi ô thiếu số liệu là 0 '
                        'và không tự đồng nhất “không đường” với “không thêm đường”.'
                    )
                    response.clarification_question = 'Bạn đang dùng sản phẩm nào và thường ăn bao nhiêu gram hoặc bao nhiêu hộp mỗi lần?'
                    response.status = 'answered'
                    response.response_strategy = 'structured_lookup'
            return self.finish_response(response, request, owner, history, raw_query, started)
        def with_profile(text):
            if authoritative is None or not personal_advice:
                return text
            dietary_only = culinary_request(text) and not is_intake_advice(text)
            return BackendProfileQuestion(text, authoritative, dietary_only=dietary_only)
        provider_query = with_profile(query)
        local_food_plan = None
        if intent == 'food_lookup' and not reference_domain:
            local_food_plan = selected_plan or self.foods.simple_lookup(query)
        outside_scope = intent == 'knowledge' and outside_nutrition_scope(query)
        if self.provider is None and local_food_plan is None and not outside_scope:
            raise ProviderFailure("Chưa cấu hình key API ở backend. Câu trả lời kiến thức cần API thật.")
        requested_version = re.search(r'\bada\s+(?:standards\s+)?(20\d{2})\b', fold(query))
        if intent == 'knowledge' and requested_version:
            response.answer = ('Tài liệu ADA Standards ' + requested_version[1]
                               + ' chưa được bật làm nguồn trả lời trong hệ thống. Mình chưa thể trả lời theo đúng phiên bản bạn yêu cầu.')
            return self.finish_response(response, request, owner, history, raw_query, started)
        if intent == 'food_lookup' and reference_domain:
            response.response_strategy = 'structured_lookup'
            stage=time.perf_counter()
            if reference_selection:
                plan=reference_selection[1]
            else:
                reference_history=[{'question':turn['question'],'response':{
                    'food_result':turn.get('response',{}).get('reference_result') or turn.get('response',{}).get('food_result')}} for turn in history]
                plan,meta,usage=self.provider.plan_food(provider_query,reference_history)
                self.record_generation(response,meta,usage)
            result=self.supplements.execute(reference_domain,plan,query)
            response.reference_result=result
            if not result['items']:
                response.status = 'needs_clarification'
                response.answer = 'Mình chưa chọn được đúng sản phẩm trong kho dữ liệu. Bạn cho mình tên đầy đủ và loại sản phẩm để tra cho chính xác nhé.'
                response.clarification_question = 'Bạn đang dùng sản phẩm và phiên bản nào?'
                return self.finish_response(response, request, owner, history, raw_query, started)
            hits=self.supplements.hits(result)
            response.timings_ms['reference_lookup']=int((time.perf_counter()-stage)*1000)
            stage=time.perf_counter()
            generated,usage=self.provider.generate_food(provider_query,hits,history)
            self.record_generation(response,generated,usage)
            response.timings_ms['answer_and_review']=int((time.perf_counter()-stage)*1000)
            validated=validate_answer(generated,make_citations(hits))
            if not validated:
                response.status = 'needs_clarification'
                response.answer = 'Mình chưa đối chiếu được đầy đủ phần thông tin này nên chưa thể kết luận chắc chắn.'
                response.clarification_question = 'Bạn cho mình tên đầy đủ của sản phẩm và thông tin cần xem nhé?'
                return self.finish_response(response, request, owner, history, raw_query, started)
            response.status='answered'
            response.answer,response.citations=validated
            if generated.uncertainty.strip():
                response.warnings.append(generated.uncertainty)
        elif intent == 'food_lookup':
            response.response_strategy = 'structured_lookup'
            if not self.foods.records:
                raise ProviderFailure('Chưa nạp dữ liệu thực phẩm; kiểm tra data/structured.')
            stage = time.perf_counter()
            if local_food_plan is not None:
                plan = local_food_plan
            else:
                plan, meta, usage = self.provider.plan_food(provider_query,history)
                self.record_generation(response,meta,usage)
            response.timings_ms['food_plan'] = int((time.perf_counter()-stage)*1000)
            plan=self.foods.bind_explicit_ids(plan,query)
            result=self.foods.execute(plan)
            result['request']=plan.model_dump()
            if plan.operation == 'compare':
                result['comparison_question'] = raw_query
                if selected_plan is not None:
                    previous = history[-1]
                    result['comparison_question'] = (
                        previous['response']['food_result'].get('comparison_question') or previous['question']
                    )
            response.food_result=result
            if not plan.items:
                response.status = 'needs_clarification'
                response.answer = 'Mình cần thêm chút thông tin để tra đúng món và tính đúng lượng.'
                response.clarification_question = 'Bạn cho biết tên thực phẩm, lượng thực tế và chất muốn xem nhé?'
                return self.finish_response(response, request, owner, history, raw_query, started)
            milk_choices = self.supplements.milk_volume_choices(plan)
            if milk_choices:
                result['display_suppressed'] = True
                response.reference_result = milk_choices
                response.status = 'needs_clarification'
                response.answer = (
                    f"Mình có dữ liệu nhãn sữa theo 100 ml. Để tính cho {plan.items[0].amount:g} ml, "
                    "hãy chọn đúng sản phẩm bạn đang uống trong các lựa chọn bên dưới. "
                    "Nếu sản phẩm của bạn chưa có trong danh sách, hãy cho biết tên và thông tin năng lượng trên nhãn."
                )
                response.answer_origin = 'static'
                return self.finish_response(response, request, owner, history, query, started)
            hits=food_hits(result)
            if result['unresolved'] and (not result['items'] or plan.operation == 'compare'):
                with_choices = [p['query'] for p in result['unresolved'] if p['candidates']]
                missing = [p['query'] for p in result['unresolved'] if not p['candidates']]
                messages = []
                if with_choices:
                    messages.append('Bạn hãy chọn loại phù hợp cho ' + ', '.join(with_choices) + ' trong các lựa chọn bên dưới.')
                    response.status = 'needs_clarification'
                if missing:
                    messages.append('Kho dữ liệu hiện chưa có bản ghi phù hợp cho ' + ', '.join(missing)
                                    + '. Mình chưa thể tính đúng phần này; không thay bằng thực phẩm hoặc trạng thái khác.')
                if len(missing) == 1 and not with_choices:
                    name = fold(missing[0])
                    if 'tra sua' in name:
                        response.clarification_question = ("Bạn có tên sản phẩm và số liệu trên nhãn, hoặc công thức "
                                                           "gồm lượng sữa, đường và trân châu của ly đó không?")
                    elif re.search(r'\b(?:com tam|banh mi thit)\b', name):
                        response.clarification_question = "Bạn có khối lượng phần cơm/bánh, phần nhân và các món kèm để tra từng thành phần không?"
                    if response.clarification_question:
                        response.status = 'needs_clarification'
                response.answer = ' '.join(messages)
                response.answer_origin = 'static'
                return self.finish_response(response, request, owner, history, query, started)
            if selected_plan is not None and plan.operation == 'compare':
                answer = format_energy_comparison(result, result['comparison_question'])
                if answer:
                    response.status = 'answered'
                    response.answer = answer
                    response.citations = make_citations(hits[:2])
                    return self.finish_response(response, request, owner, history, raw_query, started)
            if result['items'] and all(not item['calculation_available'] for item in result['items']):
                if any(item.get('review_status') in {'unreviewed', 'quarantined'} for item in result['items']):
                    response.answer = 'Số liệu món ăn đang chờ xác minh cơ sở khối lượng hoặc đơn vị nguồn, nên mình chưa thể tính theo lượng bạn hỏi. Không nên dùng số liệu này để tính khẩu phần.'
                    return self.finish_response(response, request, owner, history, raw_query, started)
                units = ', '.join(dict.fromkeys(i.unit for i in plan.items))
                response.answer = (
                    f"Nguồn hiện có ghi theo gram, chưa có quy đổi cho đơn vị {units} bạn đã dùng. "
                    "Nếu bạn biết khối lượng bằng gram, mình có thể tính theo khối lượng đó. "
                    "Bảng bên dưới là số liệu gốc, chưa phải giá trị cho lượng bạn hỏi."
                )
                response.answer_origin = 'static'
                return self.finish_response(response, request, owner, history, query, started)
            if (local_food_plan is not None and plan.operation == 'lookup' and len(result['items']) == 1
                    and plan.nutrients and len(result['items'][0]['display_nutrients']) == 1
                    and result['items'][0]['requested_amount'] is not None
                    and (self.provider is None or result['items'][0]['display_nutrients'][0]['key'] == 'energy')):
                item = result['items'][0]
                nutrient = item['display_nutrients'][0]
                response.citations = make_citations(hits[:1])
                response.warnings.extend(hits[0].chunk.warnings)
                if item.get('limitations'):
                    response.warnings.append(item['limitations'])
                if nutrient.get('quality_note'):
                    response.warnings.append(nutrient['quality_note'])
                if nutrient['amount_value'] is None:
                    response.answer = f"Bản ghi {item['name']} chưa có số liệu {plan.nutrients[0]}. [C1]"
                else:
                    amount = f"{nutrient['amount_value']:g}".replace('.', ',')
                    response.answer = (f"{item['amount_g']:g} g {item['name']} có {amount} "
                                       f"{nutrient['unit']} {nutrient['name'].lower()} theo bản ghi này. [C1]")
                    response.status = 'answered'
                if item.get('assumptions'):
                    response.answer += " " + " ".join(item['assumptions'])
                return self.finish_response(response, request, owner, history, raw_query, started)
            if self.provider is None:
                raise ProviderFailure("Lượt giải thích này cần kết nối dịch vụ AI.")
            stage = time.perf_counter()
            generated,usage=self.provider.generate_food(provider_query,hits,history)
            response.timings_ms['answer_and_review'] = int((time.perf_counter()-stage)*1000)
            self.record_generation(response,generated,usage)
            validated=validate_answer(generated,make_citations(hits))
            if validated:
                response.status='answered'
                response.answer,response.citations=validated
                if result.get('assumptions'):
                    response.answer = 'Ước tính: ' + response.answer + '\n\nGiả định tham khảo: ' + ' '.join(result['assumptions'])
                if generated.uncertainty.strip():
                    response.warnings.append(generated.uncertainty)
            else:
                response.status = 'needs_clarification'
                response.answer = 'Mình chưa đối chiếu được đầy đủ kết quả nên chưa muốn đưa một con số có thể làm bạn hiểu nhầm.'
                response.clarification_question = 'Bạn xác nhận giúp tên, cách chế biến và lượng thực phẩm cần tính nhé?'
        elif intent == 'menu_request':
            response.status = "integration_required"
        elif intent == "greeting":
            response.status = "greeting"
            response.answer = social_answer(request.message)
            return self.finish_response(response, request, owner, history, raw_query, started)
        elif any(term in fold(query) for term in ("api key", "apikey", "system prompt", "khoa bi mat", "mat khau may chu")):
            response.answer = "Mình không cung cấp khóa API, mật khẩu hoặc chỉ dẫn nội bộ. Bạn có thể hỏi về kiến thức dinh dưỡng và các nguồn tài liệu được hiển thị."
        elif re.search(r"\bbia\b.*\b(?:so lieu|nguon|trich dan|trang)\b", re.sub(r"\b(?:dung|khong|tranh) bia\b", "", fold(query))):
            response.answer = "Mình không bịa số liệu hoặc trích dẫn. Chỉ tài liệu đã được duyệt và dữ liệu thực sự có trong hệ thống mới được dùng làm bằng chứng; nguồn chưa nạp không thể làm căn cứ trả lời."
        elif outside_scope:
            response.answer = "Mình hỗ trợ giáo dục dinh dưỡng cho người trưởng thành mắc đái tháo đường típ 2 và tra cứu thành phần thực phẩm. Mình không tư vấn đầu tư hoặc viết mã lập trình. Bạn có thể hỏi về lựa chọn thực phẩm hoặc cách kiểm soát carbohydrate."
        elif is_diagnosis_request(query):
            response.answer = "Mình không chẩn đoán bệnh hoặc kết luận từ chỉ số xét nghiệm cá nhân. Bạn cần trao đổi với bác sĩ để được đánh giá phù hợp. Mình có thể giải thích kiến thức dinh dưỡng chung từ tài liệu đã duyệt."
        elif not history and (is_elliptical_intake_followup(query) or fold(query).strip(" ?!.") in {"co duoc khong", "duoc khong", "co on khong", "no thi sao", "the thi sao", "nen an gi", "bao nhieu", "co hop ly khong", "an the nao", "cai do co duoc khong", "mon do co duoc khong", "loai do co duoc khong"}):
            response.answer = "Bạn đang hỏi về thực phẩm hay tình huống nào? Hãy nói rõ nội dung để mình tìm đúng tài liệu; mình chưa đủ dữ kiện để kết luận."
        else:
            stage = time.perf_counter()
            # Resolve the user's topic before planning; an ordinary independent
            # question does not inherit the previous dish or medical claims.
            if contextual:
                query = topic_for_turn(raw_query, history) + "\nCâu hỏi tiếp: " + raw_query
            provider_query = with_profile(query)
            response_plan, metadata, usage = self.provider.plan_response(provider_query, context_history)
            response_plan = constrain_plan(response_plan, query)
            self.record_generation(response, metadata, usage)
            response.response_strategy = response_plan.strategy
            response.clarification_question = response_plan.clarification_question or None
            response.timings_ms['response_planning'] = int((time.perf_counter() - stage) * 1000)
            if response_plan.goal == 'schedule' and response.clarification_question:
                # The useful next step is collecting the missing schedule,
                # not filling the screen with generic meal/snack paragraphs.
                response.status = 'needs_clarification'
                response.answer = ('Để sắp xếp các bữa theo ca làm, mình cần biết lịch làm và giờ ngủ của bạn.'
                    if re.search(r'\b(?:ca|dem|shift)\b', fold(query)) else 'Mình cần thêm một chút thông tin để hướng dẫn sát với tình huống của bạn.')
                if hasattr(provider_client, 'trace'):
                    response.timings_ms.update(provider_client.trace())
                return self.finish_response(response, request, owner, history, raw_query, started)
            if response_plan.strategy == 'direct_llm':
                stage = time.perf_counter()
                generated, usage = self.provider.generate_direct(provider_query, response_plan, context_history)
                self.record_generation(response, generated, usage)
                response.timings_ms['direct_answer_and_review'] = int((time.perf_counter() - stage) * 1000)
                direct_answer = '\n\n'.join(b.text.strip() for b in generated.blocks)
                if direct_text_is_allowed(generated) and not direct_cooking_revision(
                    direct_answer, raw_query, context_history
                ):
                    response.status = 'answered'
                    response.answer = direct_answer
                    if uses_ground_meat(direct_answer):
                        response.answer += '\n\n' + GROUND_MEAT_TEMPERATURE
                        response.citations = [USDA_GROUND_MEAT]
                    if generated.uncertainty.strip():
                        response.warnings.append(generated.uncertainty)
                    if hasattr(provider_client, 'trace'):
                        response.timings_ms.update(provider_client.trace())
                    return self.finish_response(response, request, owner, history, raw_query, started)
                # A direct draft needing evidence is re-routed to sourced
                # answering. A failed retrieval never enables direct guessing.
                response.response_strategy = 'evidence_rag'
            stage = time.perf_counter()
            retriever = self.retriever()
            if not retriever.chunks:
                raise ProviderFailure(
                    "Chưa có index. Chạy python -m rag_app.cli ingest --mode lexical hoặc hybrid"
                )
            # Contextual follow-up retrieval is bounded and uses only prior questions, not hallucinated answers.
            vector = None
            response.timings_ms['index'] = int((time.perf_counter()-stage)*1000)
            stage = time.perf_counter()
            if retriever.metadata.get("mode") == "hybrid":
                if retriever.chroma is None and retriever.vectors is None:
                    raise ProviderFailure("Chỉ mục ChromaDB thiếu vector. Chạy ingest --mode hybrid để tạo lại.")
                identity = retriever.metadata.get("embedding_identity", retriever.metadata.get("embedding_model"))
                if identity != self.settings.embedding_identity:
                    raise ProviderFailure(
                        "EMBEDDING_MODEL đã đổi; cần chạy ingest --mode hybrid lại"
                    )
                vector, cache_hit = self.query_vector(query)
                response.timings_ms['embedding_cache_hit'] = int(cache_hit)
            response.timings_ms['embedding'] = int((time.perf_counter()-stage)*1000)
            stage = time.perf_counter()
            try:
                hits = retriever.search(query, self.settings.top_k, vector, self.settings.min_dense_score)
            except ChromaIndexError as error:
                raise ProviderFailure(str(error)) from error
            if is_intake_advice(raw_query) and re.search(r'\b(?:th|moc chau|mcc|topkid)\b', fold(raw_query)):
                plan, meta, usage = self.provider.plan_food(raw_query, history)
                self.record_generation(response, meta, usage)
                result = self.supplements.execute('label', plan, raw_query)
                response.reference_result = result
                hits = hits + self.supplements.hits(result)
            response.timings_ms['retrieval'] = int((time.perf_counter()-stage)*1000)
            if hits:
                citations = make_citations(hits)
                stage = time.perf_counter()
                if response.response_strategy == 'practical_rag':
                    generated, usage = self.provider.generate_practical(provider_query, hits, context_history, response_plan)
                else:
                    generated, usage = self.provider.generate(provider_query, hits, context_history)
                response.timings_ms['answer_and_review'] = int((time.perf_counter()-stage)*1000)
                validated = validate_answer(generated, citations)
                self.record_generation(response, generated, usage)
                if validated:
                    response.status = "answered"
                    response.answer, response.citations = validated
                    if generated.uncertainty.strip():
                        response.warnings.append(generated.uncertainty)
                elif ((generated._grounding_review or {}).get('server_rejections')
                      or (generated._grounding_review or {}).get('review', {}).get('needs_revision')):
                    response.answer = ('Mình đã tìm được tài liệu liên quan nhưng chưa kiểm chứng được một câu trả lời phù hợp từ các đoạn trích này. '
                                       'Mình chưa thể trả lời chắc chắn ở lượt này; đây không phải kết luận rằng kho không có tài liệu về chủ đề đó.')
                if response.citations:
                    cited_chunks = {c.chunk_id for c in response.citations}
                    response.warnings.extend(
                        dict.fromkeys(w for h in hits if h.chunk.id in cited_chunks for w in h.chunk.warnings)
                    )
        if response.status != "answered":
            # Routing remains deterministic, but the visible response is generated
            # and checked by the real provider against the approved boundary.
            stage = time.perf_counter()
            if outside_scope and self.provider is None:
                return self.finish_response(response, request, owner, history, raw_query, started)
            try:
                generated, usage = self.provider.generate_policy(provider_query, response.answer, history)
            except ProviderFailure:
                if not outside_scope:
                    raise
                # The authored scope notice is complete even during a provider outage.
                return self.finish_response(response, request, owner, history, raw_query, started)
            response.timings_ms['policy_and_review'] = int((time.perf_counter()-stage)*1000)
            if not generated.supported or not generated.blocks:
                raise ProviderFailure("AI chưa tạo được phản hồi hợp lệ; hãy thử lại.")
            response.answer = "\n\n".join(block.text for block in generated.blocks)
            self.record_generation(response, generated, usage)
        if hasattr(provider_client, 'trace'):
            response.timings_ms.update(provider_client.trace())
        return self.finish_response(response, request, owner, history, raw_query, started)

    def finish_response(self, response, request, owner, history, query, started):
        expected = getattr(response, '_backend_profile_version', None)
        if expected is not None:
            try:
                latest = self.meals.snapshot(owner, getattr(response, '_profile_authorization', None)).profile
                changed = latest.profile_version != expected or self._profile_epochs.get(owner, 0) != getattr(response, '_profile_epoch', 0)
            except MealServiceError:
                changed = True
            if changed:
                response.answer = 'Hồ sơ đã thay đổi trong khi xử lý câu hỏi. Hãy hỏi lại để mình dùng hồ sơ mới nhất.'
                response.status = 'needs_clarification'
                response.response_strategy = 'policy'
                response.citations = []
                response.meal_result = None
                response.food_result = None
                response.reference_result = None
                response.answer_origin = 'static'
                response.model = None
                response.grounding_model = None
                response.clarification_question = None
                response.scope_restriction = None
                response.restriction_for_relative = False
                history = []
        # Asking about the observed portion is dialogue control, not a sourced
        # nutrition claim. Keep it separate from the model's reviewed answer.
        if (history and response.intent == 'knowledge' and is_elliptical_intake_followup(query)
                and is_intake_quantity_request(query) and '?' not in response.answer
                and not re.search(r'\bzero(?: sugar)?\b|\bnuoc ngot\b.*\bkhong duong\b',
                                  fold(topic_for_turn(query, history)))
                and not any(is_portion_description(t['question']) or re.search(
                    r'\d+\s*(?:g|gram|gam|ml)\b|\b(?:to|bat)\s+(?:nho|lon|vua)\b', fold(t['question']))
                    for t in history[-3:])):
            topic = fold(topic_for_turn(query, history))
            response.clarification_question = (
                'Bạn thường ăn tô/bát nhỏ hay lớn, và ăn hết hay chỉ một phần?'
                if re.search(r'\b(?:pho|bun|chao|sup|mien|hu tieu)\b', topic) else
                'Bạn thường uống cỡ cốc/hộp bao nhiêu ml mỗi lần?' if 'uong' in fold(query) else
                'Bạn thường ăn một phần cỡ nào (cỡ bát/đĩa hoặc lượng bạn thường lấy)?')
        response.latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info('chat_completed intent=%s strategy=%s status=%s origin=%s citations=%d duration_ms=%d',
                    response.intent, response.response_strategy, response.status, response.answer_origin,
                    len(response.citations), response.latency_ms)
        if request.save_history:
            response.history_saved = True
            try:
                self.store.save_message(
                    owner, str(response.session_id), str(response.message_id), redact(request.message),
                    {**response.model_dump(mode="json"), 'context_topic': topic_for_turn(query, history),
                     'cooking_suggestion': response.status == 'answered' and getattr(response, '_cooking_suggestion', False)},
                )
            except HistoryStoreError:
                if response.intent != 'emergency':
                    raise
                response.history_saved = False
                response.warnings.append('Chưa lưu được lượt này vào lịch sử.')
        self.remember_turn(owner, response.session_id, history, query, response)
        return response

    @staticmethod
    def meal_pending(result):
        proposal = (result or {}).get('proposal') or (result or {}).get('pending')
        return None if not proposal else {key: proposal[key] for key in ('id', 'planId', 'baseVersion', 'expiresAt') if key in proposal}

    def cancel_meal_proposals(self, owner, history):
        # Session-local cancellation supplements backend version/expiry checks.
        # A production backend must also persist revocation across instances.
        with self._meal_edit_lock:
            now = time.time()
            self._revoked_meal_proposals = {key: expiry for key, expiry in self._revoked_meal_proposals.items() if expiry > now}
            for turn in history:
                previous = turn.get('response', {})
                pending = previous.get('meal_pending') or self.meal_pending(previous.get('meal_result'))
                if pending and pending.get('id') and pending.get('expiresAt'):
                    expiry = float(pending['expiresAt'])
                    if expiry > now:
                        self._revoked_meal_proposals[(owner, pending['id'])] = expiry

    def apply_meal_swap(self, owner, body, authorization=None):
        with self._meal_edit_lock:
            if self._revoked_meal_proposals.get((owner, str(body.proposal_id)), 0) > time.time():
                raise MealServiceError('PROPOSAL_CANCELLED')
            if owner in self._meal_profile_blocks:
                snapshot = self.meals.snapshot(owner, authorization, body.plan_id)
                if snapshot.profile.profile_version <= self._meal_profile_blocks[owner]:
                    raise MealServiceError('PROFILE_INCOMPLETE')
            return self.meals.apply(owner, body, authorization)

    @staticmethod
    def record_generation(response, generated, usage):
        response.answer_origin = generated._provider_name if generated._provider_name in {"gemini", "openai"} else "custom_provider"
        response.model = generated._provider_model
        response.grounding_model = generated._grounding_model
        response.provider_response_ids.extend(generated._provider_response_ids)
        for key, value in usage.items():
            response.usage[key] = response.usage.get(key, 0) + value
