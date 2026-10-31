import logging
import re
import threading
import time
from collections import OrderedDict
from uuid import uuid4

from rag_app.config import Settings
from rag_app.conversation import is_contextual_followup, is_portion_description, topic_for_turn
from rag_app.domain import ChatRequest, ChatResponse, Citation, GeneratedAnswer, Hit
from rag_app.food_data import food_hits, get_catalog
from rag_app.provider import Provider, ProviderFailure, redact
from rag_app.retrieval import Retriever, fold
from rag_app.routing import constrain_plan, direct_text_is_allowed
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
    return "\n\n".join(blocks), [available[i] for i in dict.fromkeys(used)]


class ChatService:
    def __init__(self, settings: Settings, store: Store, provider: Provider | None = None):
        self.settings = settings
        self.store = store
        self.provider = provider
        self.foods = get_catalog()
        self.supplements = SupplementCatalog()
        self._retriever = None
        self._retriever_lock = threading.Lock()
        self._transient = {}
        self._session_lock = threading.Lock()
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
                                              'clarification_question': response.clarification_question,
                                              'scope_restriction': response.scope_restriction}}
        trimmed = []
        for previous in history[-5:]:
            old = previous.get('response', {}).get('food_result')
            trimmed.append({'question': previous['question'], 'topic': previous.get('topic', previous['question'])[:1000], 'response': {
                'scope_restriction': previous.get('response', {}).get('scope_restriction'),
                'answer': previous.get('response', {}).get('answer', '')[:3000],
                'response_strategy': previous.get('response', {}).get('response_strategy'),
                'clarification_question': previous.get('response', {}).get('clarification_question'),
                'reference_result':previous.get('response',{}).get('reference_result'),'food_result': None if old is None else {
                'request': old.get('request'), 'unresolved': old.get('unresolved', []),
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
                self._retriever = Retriever(self.store)
            return self._retriever

    def chat(self, request: ChatRequest, owner: str) -> ChatResponse:
        started = time.perf_counter()
        session = request.session_id or uuid4()
        history = []
        if request.session_id:
            history = self.transient_history(owner, session)
            if history is None and not self.store.session_exists(owner, str(session)):
                raise PermissionError("Session không tồn tại hoặc không thuộc người dùng")
            if history is None:
                history = self.store.history(owner, str(session), limit=6)
        provider_client = getattr(self.provider, 'client', None)
        if hasattr(provider_client, 'start_trace'):
            provider_client.start_trace()
        query = re.sub(r'\bko\b', 'không', redact(request.message), flags=re.IGNORECASE)
        raw_query = query
        selected_plan = self.foods.resolve_selection(query, history)
        contextual = bool(history) and is_contextual_followup(query, history)
        # A short new subject (e.g. brown rice after bread) is independent.
        # Short follow-ups within an explicit safety condition remain guarded.
        safety_contextual = contextual or bool(history) and len(query.split()) < 9
        # Carry a safety condition through a chain of elliptical follow-ups.
        # A standalone question ends that chain; only user questions count.
        context_intent = None
        if safety_contextual:
            for previous in reversed(history):
                previous_query = previous["question"]
                previous_intent = classify(previous_query)
                if previous_intent in {"special_population", "medication", "emergency"}:
                    context_intent = previous_intent
                    break
                if len(previous_query.split()) >= 9 and not re.search(r"\b(?:con|do|nay|ay|vay)\b", fold(previous_query)):
                    break
        intent = classify(request.message)
        restricted = intent == 'special_population' or any(
            turn.get('response', {}).get('scope_restriction') == 'special_population'
            or classify(turn['question']) == 'special_population' for turn in history
        )
        # A declared special population is a session restriction, not a short
        # linguistic follow-up. It survives greetings and long independent questions.
        if restricted and intent in {'knowledge', 'food_lookup', 'menu_request'}:
            intent = 'special_population'
        if context_intent in {"special_population", "medication", "emergency"} and intent in {"knowledge", "food_lookup"}:
            intent = context_intent
        if intent=='knowledge' and not is_intake_advice(query) and (selected_plan is not None or self.foods.looks_like_lookup(query) or contextual and history[-1].get('response',{}).get('food_result')):
            intent='food_lookup'
        reference_domain=self.supplements.detect(query)
        reference_selection=self.supplements.resolve_selection(query,history)
        if reference_selection:
            reference_domain=reference_selection[0]
        elif not reference_domain and contextual and history[-1].get('response',{}).get('reference_result'):
            reference_domain=history[-1]['response']['reference_result']['domain']
        if reference_domain and intent in {'knowledge','food_lookup'}:
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
        )
        if intent in {"medication", "emergency", "special_population"}:
            response.response_strategy = 'safety'
            response.status = "safety"
            if intent == 'emergency':
                response.answer = emergency_answer(request.message)
            # Reviewed fixed boundaries must work without network/key/quota.
            # They are explicitly marked static, never presented as an AI answer.
            response.timings_ms['safety_routing'] = int((time.perf_counter() - started) * 1000)
            return self.finish_response(response, request, owner, history, query, started)
        if self.provider is None:
            raise ProviderFailure("Chưa cấu hình key API ở backend. Câu trả lời kiến thức cần API thật.")
        requested_version = re.search(r'\bada\s+(20\d{2})\b', fold(query))
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
                plan,meta,usage=self.provider.plan_food(query,reference_history)
                self.record_generation(response,meta,usage)
            result=self.supplements.execute(reference_domain,plan,query)
            response.reference_result=result
            hits=self.supplements.hits(result)
            response.timings_ms['reference_lookup']=int((time.perf_counter()-stage)*1000)
            stage=time.perf_counter()
            generated,usage=self.provider.generate_food(query,hits,history)
            self.record_generation(response,generated,usage)
            response.timings_ms['answer_and_review']=int((time.perf_counter()-stage)*1000)
            validated=validate_answer(generated,make_citations(hits))
            if not validated:
                raise ProviderFailure('AI chưa đối chiếu được kết quả tra cứu bổ sung; hãy thử lại.')
            response.status='answered'
            response.answer,response.citations=validated
            if generated.uncertainty.strip():
                response.warnings.append(generated.uncertainty)
        elif intent == 'food_lookup':
            response.response_strategy = 'structured_lookup'
            if not self.foods.records:
                raise ProviderFailure('Chưa nạp dữ liệu thực phẩm; kiểm tra data/structured.')
            stage = time.perf_counter()
            if selected_plan is not None:
                plan = selected_plan
            elif (simple_plan := self.foods.simple_lookup(query)) is not None:
                plan = simple_plan
            else:
                plan, meta, usage = self.provider.plan_food(query,history)
                self.record_generation(response,meta,usage)
            response.timings_ms['food_plan'] = int((time.perf_counter()-stage)*1000)
            plan=self.foods.bind_explicit_ids(plan,query)
            result=self.foods.execute(plan)
            result['request']=plan.model_dump()
            response.food_result=result
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
            if result['unresolved'] and not result['items']:
                with_choices = [p['query'] for p in result['unresolved'] if p['candidates']]
                missing = [p['query'] for p in result['unresolved'] if not p['candidates']]
                messages = []
                if with_choices:
                    messages.append('Bạn hãy chọn loại phù hợp cho ' + ', '.join(with_choices) + ' trong các lựa chọn bên dưới.')
                if missing:
                    messages.append('Kho dữ liệu hiện chưa có bản ghi phù hợp cho ' + ', '.join(missing)
                                    + '. Mình chưa thể tính đúng phần này; không thay bằng thực phẩm hoặc trạng thái khác.')
                response.answer = ' '.join(messages)
                response.answer_origin = 'static'
                return self.finish_response(response, request, owner, history, query, started)
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
            stage = time.perf_counter()
            generated,usage=self.provider.generate_food(query,hits,history)
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
                raise ProviderFailure('AI chưa đối chiếu được câu trả lời với dữ liệu thực phẩm; hãy thử lại.')
        elif intent == 'menu_request':
            response.status = "integration_required"
        elif intent == "greeting":
            response.status = "greeting"
            response.answer = social_answer(request.message)
        elif any(term in fold(query) for term in ("api key", "apikey", "system prompt", "khoa bi mat", "mat khau may chu")):
            response.answer = "Mình không cung cấp khóa API, mật khẩu hoặc chỉ dẫn nội bộ. Bạn có thể hỏi về kiến thức dinh dưỡng và các nguồn tài liệu được hiển thị."
        elif re.search(r"\bbia\b.*\b(?:so lieu|nguon|trich dan|trang)\b", re.sub(r"\b(?:dung|khong|tranh) bia\b", "", fold(query))):
            response.answer = "Mình không bịa số liệu hoặc trích dẫn. Chỉ tài liệu đã được duyệt và dữ liệu thực sự có trong hệ thống mới được dùng làm bằng chứng; nguồn chưa nạp không thể làm căn cứ trả lời."
        elif outside_nutrition_scope(query):
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
            response_plan, metadata, usage = self.provider.plan_response(query, history if contextual else [])
            response_plan = constrain_plan(response_plan, query)
            self.record_generation(response, metadata, usage)
            response.response_strategy = response_plan.strategy
            response.clarification_question = response_plan.clarification_question or None
            response.timings_ms['response_planning'] = int((time.perf_counter() - stage) * 1000)
            if response_plan.goal == 'schedule' and response.clarification_question:
                # The useful next step is collecting the missing schedule,
                # not filling the screen with generic meal/snack paragraphs.
                response.status = 'needs_clarification'
                response.answer = 'Để sắp xếp các bữa theo ca làm, mình cần biết lịch làm và giờ ngủ của bạn.'
                if hasattr(provider_client, 'trace'):
                    response.timings_ms.update(provider_client.trace())
                return self.finish_response(response, request, owner, history, raw_query, started)
            if response_plan.strategy == 'direct_llm':
                stage = time.perf_counter()
                generated, usage = self.provider.generate_direct(query, response_plan, history if contextual else [])
                self.record_generation(response, generated, usage)
                response.timings_ms['direct_answer_and_review'] = int((time.perf_counter() - stage) * 1000)
                if direct_text_is_allowed(generated):
                    response.status = 'answered'
                    response.answer = '\n\n'.join(b.text.strip() for b in generated.blocks)
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
                identity = retriever.metadata.get("embedding_identity", retriever.metadata.get("embedding_model"))
                if identity != self.settings.embedding_identity:
                    raise ProviderFailure(
                        "EMBEDDING_MODEL đã đổi; cần chạy ingest --mode hybrid lại"
                    )
                vector, cache_hit = self.query_vector(query)
                response.timings_ms['embedding_cache_hit'] = int(cache_hit)
            response.timings_ms['embedding'] = int((time.perf_counter()-stage)*1000)
            stage = time.perf_counter()
            hits = retriever.search(
                query, self.settings.top_k, vector, self.settings.min_dense_score
            )
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
                    generated, usage = self.provider.generate_practical(query, hits, history if contextual else [], response_plan)
                else:
                    generated, usage = self.provider.generate(query, hits, history if contextual else [])
                response.timings_ms['answer_and_review'] = int((time.perf_counter()-stage)*1000)
                validated = validate_answer(generated, citations)
                self.record_generation(response, generated, usage)
                if validated:
                    response.status = "answered"
                    response.answer, response.citations = validated
                    if generated.uncertainty.strip():
                        response.warnings.append(generated.uncertainty)
                if response.citations:
                    cited_chunks = {c.chunk_id for c in response.citations}
                    response.warnings.extend(
                        dict.fromkeys(w for h in hits if h.chunk.id in cited_chunks for w in h.chunk.warnings)
                    )
        if response.status != "answered":
            # Routing remains deterministic, but the visible response is generated
            # and checked by the real provider against the approved boundary.
            stage = time.perf_counter()
            generated, usage = self.provider.generate_policy(query, response.answer, history)
            response.timings_ms['policy_and_review'] = int((time.perf_counter()-stage)*1000)
            if not generated.supported or not generated.blocks:
                raise ProviderFailure("AI chưa tạo được phản hồi hợp lệ; hãy thử lại.")
            response.answer = "\n\n".join(block.text for block in generated.blocks)
            self.record_generation(response, generated, usage)
        if hasattr(provider_client, 'trace'):
            response.timings_ms.update(provider_client.trace())
        return self.finish_response(response, request, owner, history, raw_query, started)

    def finish_response(self, response, request, owner, history, query, started):
        # Asking about the observed portion is dialogue control, not a sourced
        # nutrition claim. Keep it separate from the model's reviewed answer.
        if (history and response.intent == 'knowledge' and is_elliptical_intake_followup(query)
                and is_intake_quantity_request(query) and '?' not in response.answer
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
            self.store.save_message(
                owner,
                str(response.session_id),
                str(response.message_id),
                redact(request.message),
                {**response.model_dump(mode="json"), 'context_topic': topic_for_turn(query, history)},
            )
        self.remember_turn(owner, response.session_id, history, query, response)
        return response

    @staticmethod
    def record_generation(response, generated, usage):
        response.answer_origin = generated._provider_name if generated._provider_name in {"gemini", "openai"} else "custom_provider"
        response.model = generated._provider_model
        response.grounding_model = generated._grounding_model
        response.provider_response_ids.extend(generated._provider_response_ids)
        for key, value in usage.items():
            response.usage[key] = response.usage.get(key, 0) + value
