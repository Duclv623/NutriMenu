from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

Intent = Literal[
    "knowledge",
    "food_lookup",
    "menu_request",
    "medication",
    "emergency",
    "special_population",
    "greeting",
]


class Chunk(BaseModel):
    id: str
    source_id: str
    title: str
    text: str
    section: str
    pages: list[int]
    printed_pages: list[int]
    filename: str
    source_url: str = ""
    year: int
    version: str
    sha256: str
    token_count: int
    warnings: list[str] = Field(default_factory=list)
    language: Literal['vi', 'en'] = 'vi'
    related_sections: list[str] = Field(default_factory=list)
    document_format: Literal["pdf", "docx", "structured", "curated"] = "pdf"
    locators: list[str] = Field(default_factory=list)


class Hit(BaseModel):
    chunk: Chunk
    score: float
    lexical_score: float = 0
    dense_score: float | None = None


class Citation(BaseModel):
    id: str
    chunk_id: str
    source_id: str
    title: str
    section: str
    pdf_pages: list[int]
    printed_pages: list[int]
    quote: str
    source_url: str
    document_url: str
    year: int
    version: str
    document_format: Literal["pdf", "docx", "structured", "curated"] = "pdf"
    locators: list[str] = Field(default_factory=list)


class AnswerBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    citation_ids: list[str]


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported: bool
    blocks: list[AnswerBlock]
    uncertainty: str
    _provider_model: str | None = PrivateAttr(default=None)
    _provider_name: str | None = PrivateAttr(default=None)
    _grounding_model: str | None = PrivateAttr(default=None)
    _provider_response_ids: list[str] = PrivateAttr(default_factory=list)
    _grounding_review: dict | None = PrivateAttr(default=None)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
    session_id: UUID | None = None
    save_history: bool = False
    # Deprecated compatibility field. Chat always uses the configured real API;
    # the UI discloses this behavior and does not offer a cloud/offline switch.
    cloud_consent: bool | None = None

    @field_validator("message")
    @classmethod
    def nonblank(cls, value):
        value = value.strip()
        if not value or "\x00" in value:
            raise ValueError("Câu hỏi không được trống hoặc chứa ký tự NUL")
        return value


class ChatResponse(BaseModel):
    session_id: UUID
    message_id: UUID
    intent: Intent
    status: Literal[
        "answered",
        "insufficient_evidence",
        "safety",
        "integration_required",
        "greeting",
    ]
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    mode: str
    answer_origin: Literal["static", "openai", "gemini", "custom_provider"] = "static"
    model: str | None = None
    grounding_model: str | None = None
    provider_response_ids: list[str] = Field(default_factory=list)
    history_saved: bool = False
    latency_ms: int = 0
    timings_ms: dict[str, int] = Field(default_factory=dict)
    usage: dict[str, int] = Field(default_factory=dict)
    food_result: dict | None = None
    reference_result: dict | None = None
    clarification_question: str | None = None
    scope_restriction: Literal["special_population"] | None = None


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: UUID
    rating: Literal["helpful", "not_helpful"]
