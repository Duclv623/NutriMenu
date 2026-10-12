"""Gemini REST adapter. Credentials are headers to one fixed official host only."""
import hashlib
import re
import threading
import time
from types import SimpleNamespace

import httpx
import numpy as np

from rag_app.config import Settings
from rag_app.provider import OpenAIProvider, ProviderFailure, redact


class GeminiClient:
    _pace_lock = threading.Lock()
    _buckets = {}

    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.http = httpx.Client(base_url='https://generativelanguage.googleapis.com/v1beta/',
            headers={'x-goog-api-key':settings.gemini_api_key.get_secret_value()},
            timeout=settings.gemini_timeout,follow_redirects=False,transport=transport)
        self.responses = SimpleNamespace(parse=self.parse)
        self._project_id = hashlib.sha256(settings.gemini_api_key.get_secret_value().encode()).hexdigest()
        self._trace = threading.local()

    def start_trace(self):
        self._trace.values = {'api_wait_ms': 0, 'api_http_ms': 0}

    def trace(self):
        return dict(getattr(self._trace, 'values', {}))

    def add_time(self, name, started):
        if hasattr(self._trace, 'values'):
            self._trace.values[name] += int((time.perf_counter() - started) * 1000)

    def close(self):
        self.http.close()

    def post(self, model, method, body):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+',model):
            raise ProviderFailure('Tên model Gemini không hợp lệ.')
        # Only retry transient service errors once. Never loop on free quota/key errors.
        for attempt in range(2):
            if method == 'generateContent' and self.settings.gemini_request_interval:
                wait_started = time.perf_counter()
                # Permit a small answer/check burst, refill at the sustained
                # rate. Shared across clients with the same key and model.
                interval = self.settings.gemini_request_interval
                capacity = self.settings.gemini_burst_requests
                key = (self._project_id, model)
                while True:
                    with self._pace_lock:
                        now = time.monotonic()
                        credits, updated = self._buckets.get(key, (capacity, now))
                        credits = min(capacity, credits + max(0, now - updated) / interval)
                        if credits >= 1 - 1e-9:
                            self._buckets[key] = (max(0, credits - 1), now)
                            break
                        self._buckets[key] = (credits, now)
                        delay = (1 - credits) * interval
                    time.sleep(delay)
                self.add_time('api_wait_ms', wait_started)
            try:
                http_started = time.perf_counter()
                response = self.http.post(f'models/{model}:{method}',json=body)
                self.add_time('api_http_ms', http_started)
            except httpx.HTTPError as error:
                raise ProviderFailure('Không kết nối được Gemini; kiểm tra mạng hoặc thử lại.') from error
            if response.status_code in {500,502,503,504} and attempt == 0:
                time.sleep(1)
                continue
            if response.status_code != 200:
                if response.status_code == 429:
                    message = 'Gemini đã chạm quota/hạn mức API (HTTP 429). Kiểm tra Usage/Rate limits trong Google AI Studio trước khi thử lại.'
                elif response.status_code in {401,403}:
                    message = 'Gemini từ chối key hoặc quyền truy cập. Kiểm tra key/project trong Google AI Studio.'
                elif response.status_code == 404:
                    message = 'Model Gemini đang cấu hình không truy cập được (HTTP 404); kiểm tra model trong project.'
                else:
                    message = f'Gemini chưa xử lý được yêu cầu (HTTP {response.status_code}); kiểm tra cấu hình API.'
                raise ProviderFailure(message)
            try:
                return response.json()
            except ValueError as error:
                raise ProviderFailure('Gemini trả dữ liệu không hợp lệ.') from error
        raise ProviderFailure('Gemini tạm thời không khả dụng.')

    def parse(self, *, model, input, text_format, max_output_tokens, **kwargs):
        system = '\n'.join(m['content'] for m in input if m['role'] == 'system')
        content = '\n'.join(m['content'] for m in input if m['role'] != 'system')
        config = {'temperature':0,'maxOutputTokens':max_output_tokens,
                  'responseMimeType':'application/json','responseJsonSchema':text_format.model_json_schema()}
        if model.startswith('gemini-3'):
            config['thinkingConfig'] = {'thinkingLevel':'minimal'}
        elif model.startswith('gemini-2.5'):
            config['thinkingConfig'] = {'thinkingBudget':0}
        data = self.post(model,'generateContent',{
            'systemInstruction':{'parts':[{'text':system}]},
            'contents':[{'role':'user','parts':[{'text':content}]}],
            'generationConfig':config,'store':False})
        candidates = data.get('candidates',[])
        if not candidates or candidates[0].get('finishReason') != 'STOP':
            raise ProviderFailure('Gemini chưa hoàn thành câu trả lời hoặc đã chặn nội dung; không trả bản nháp.')
        text = ''.join(p.get('text','') for p in candidates[0].get('content',{}).get('parts',[]) if not p.get('thought'))
        try:
            parsed = text_format.model_validate_json(text)
        except ValueError as error:
            raise ProviderFailure('Cấu trúc phản hồi Gemini không hợp lệ; không trả bản nháp.') from error
        response_id = data.get('responseId')
        if not response_id:
            raise ProviderFailure('Gemini thiếu ID phản hồi để kiểm chứng lượt gọi thật.')
        usage = data.get('usageMetadata',{})
        return SimpleNamespace(id=response_id,status='completed',output_parsed=parsed,
            usage=SimpleNamespace(input_tokens=usage.get('promptTokenCount',0),
                output_tokens=usage.get('candidatesTokenCount',0)+usage.get('thoughtsTokenCount',0)))


class GeminiProvider(OpenAIProvider):
    name = 'gemini'

    def __init__(self, settings: Settings, transport=None):
        if not settings.gemini_api_key.get_secret_value().strip():
            raise ProviderFailure('Chưa cấu hình GEMINI_API_KEY ở backend.')
        self.settings = settings.model_copy(update={'openai_model':settings.gemini_model,
            'grounding_model':settings.gemini_grounding_model})
        self.client = GeminiClient(settings,transport)
        self._embedder = None

    def _embed(self, texts, documents=False):
        if not texts:
            return []
        model = self.settings.gemini_embedding_model
        requests = []
        for text in texts:
            if model == 'gemini-embedding-2':
                value = ('title: Nutrition education | text: ' if documents else
                         'task: search result | query: ') + redact(text)
                request = {'model':'models/'+model,'content':{'parts':[{'text':value}]},
                           'outputDimensionality':self.settings.gemini_embedding_dimensions}
            else:
                request = {'model':'models/'+model,'content':{'parts':[{'text':redact(text)}]},
                    'taskType':'RETRIEVAL_DOCUMENT' if documents else 'RETRIEVAL_QUERY',
                    'outputDimensionality':self.settings.gemini_embedding_dimensions}
            requests.append(request)
        data = self.client.post(model,'batchEmbedContents',{'requests':requests})
        embeddings = data.get('embeddings',[])
        if len(embeddings) != len(texts):
            raise ProviderFailure('Gemini embedding trả không đủ phần tử; không thay index.')
        vectors = [e.get('values',[]) for e in embeddings]
        try:
            array = np.asarray(vectors,dtype=np.float32)
        except (ValueError, TypeError) as error:
            raise ProviderFailure('Gemini embedding không hợp lệ; không thay index.') from error
        if array.shape != (len(texts),self.settings.gemini_embedding_dimensions) or not np.isfinite(array).all() or (np.linalg.norm(array,axis=1)==0).any():
            raise ProviderFailure('Gemini embedding sai kích thước/giá trị; không thay index.')
        array /= np.linalg.norm(array,axis=1,keepdims=True)
        return array.tolist()

    def embed(self, texts):
        if self.settings.embedding_mode == 'openai':
            if self._embedder is None:
                self._embedder = OpenAIProvider(self.settings)
            return self._embedder.embed(texts)
        return self._embed(texts)

    def embed_documents(self, texts):
        if self.settings.embedding_mode == 'openai':
            return self.embed(texts)
        return self._embed(texts,documents=True)
