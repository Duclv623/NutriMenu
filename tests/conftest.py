from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from rag_app.config import Settings
from rag_app.domain import AnswerBlock, GeneratedAnswer
from rag_app.ingestion import build_chunks
from rag_app.main import create_app
from rag_app.store import Store


class FakeProvider:
    """Deterministic test double, NEVER used as real application output."""

    def __init__(self):
        self.generate_calls = []
        self.policy_calls = []
        self.embed_calls = []
        self.answer = None
        self.error = None

    def embed(self, texts):
        self.embed_calls.append(texts)
        return [[1.0, 0.5, 0.1] for _ in texts]

    def generate(self, question, hits, history):
        self.generate_calls.append((question, hits, history))
        if self.error:
            raise self.error
        generated = self.answer or GeneratedAnswer(
            supported=True,
            blocks=[
                AnswerBlock(text="Nội dung giả lập chỉ dùng cho kiểm thử.", citation_ids=["C1"])
            ],
            uncertainty="Đây là mock, không phải câu trả lời y khoa.",
        )
        return generated, {"input_tokens": 12, "output_tokens": 8}

    def generate_policy(self, question, approved_message, history):
        self.policy_calls.append((question, approved_message, history))
        if self.error:
            raise self.error
        return GeneratedAnswer(supported=True, blocks=[AnswerBlock(text=approved_message, citation_ids=["P1"])], uncertainty=""), {"input_tokens": 12, "output_tokens": 8}

    def plan_food(self, question, history):
        from rag_app.food_data import FoodPlan
        if self.error:
            raise self.error
        plan = getattr(self,'food_plan',FoodPlan(operation='lookup',items=[],clarification='Cần chọn thực phẩm.'))
        return plan,GeneratedAnswer(supported=False,blocks=[],uncertainty=''),{'input_tokens':5,'output_tokens':5}

    def generate_food(self, question, hits, history):
        return self.generate(question,hits,history)


@pytest.fixture(scope="session")
def corpus():
    return build_chunks(Settings(_env_file=None))[0]


@pytest.fixture
def system(tmp_path, corpus):
    cfg = Settings(storage_dir=tmp_path, _env_file=None, openai_api_key="", answer_mode="openai", embedding_mode="openai")
    store = Store(tmp_path / "rag.sqlite3")
    store.replace_index(corpus, {"mode": "lexical"})
    provider = FakeProvider()
    app = create_app(cfg, provider)
    with TestClient(app) as client:
        yield SimpleNamespace(cfg=cfg, store=store, provider=provider, app=app, client=client)
