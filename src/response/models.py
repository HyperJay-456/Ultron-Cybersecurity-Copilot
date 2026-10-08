"""Typed models and domain concepts for M11.5 Long Response Subsystem."""

from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ResponseStatus(str, Enum):
    """Lifecycle status of a response generation session."""
    GENERATING = "GENERATING"
    CONTINUING = "CONTINUING"
    COMPLETED = "COMPLETED"
    USER_STOPPED = "USER_STOPPED"
    MODEL_STOPPED = "MODEL_STOPPED"
    TOKEN_LIMIT = "TOKEN_LIMIT"
    CONTEXT_LIMIT = "CONTEXT_LIMIT"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


class GenerationTermination(str, Enum):
    """Underlying reason why model generation or continuation halted."""
    NATURAL_STOP = "NATURAL_STOP"
    LENGTH_CEILING = "LENGTH_CEILING"
    CONTEXT_EXHAUSTION = "CONTEXT_EXHAUSTION"
    TIMEOUT_ABORT = "TIMEOUT_ABORT"
    CLIENT_ABORT = "CLIENT_ABORT"
    ENGINE_ERROR = "ENGINE_ERROR"
    MAX_CHUNKS_REACHED = "MAX_CHUNKS_REACHED"
    SAFETY_BOUND_EXCEEDED = "SAFETY_BOUND_EXCEEDED"


class CompletenessState(str, Enum):
    """Heuristic assessment of whether generated text represents a finished thought."""
    COMPLETE = "COMPLETE"
    LIKELY_COMPLETE = "LIKELY_COMPLETE"
    LIKELY_INCOMPLETE = "LIKELY_INCOMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN = "UNKNOWN"


def compute_content_hash(text: str) -> str:
    """Compute deterministic SHA-256 hash of chunk content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ResponseChunk(BaseModel):
    """Individual chunk produced in a multi-turn continuation generation."""
    chunk_id: str
    sequence_number: int
    content: str
    raw_content: str
    content_hash: str = ""
    token_count: int = 0
    generation_time: float = 0.0
    stop_reason: str = "stop"  # e.g., 'stop', 'length', 'timeout', 'abort'
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash and self.content is not None:
            self.content_hash = compute_content_hash(self.content)

    def verify_hash(self) -> bool:
        """Verify that content matches content_hash."""
        return self.content_hash == compute_content_hash(self.content)


class ContinuationState(BaseModel):
    """State tracking for automated or manual continuation."""
    chunk_count: int = 0
    cumulative_tokens: int = 0
    repacking_attempts: int = 0
    status: ResponseStatus = ResponseStatus.GENERATING
    termination_reason: Optional[GenerationTermination] = None
    can_continue: bool = True
    last_error: Optional[str] = None


class ResponseVersion(BaseModel):
    """Historical version of an assistant response across regenerations."""
    version_id: str
    response_id: str
    version_number: int
    content: str
    model: str
    status: ResponseStatus = ResponseStatus.COMPLETED
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ResponseSession(BaseModel):
    """
    First-class response session aggregating multi-chunk long responses,
    preserving exact chunk provenance and unified user-facing delivery.
    """
    response_id: str
    investigation_id: str
    parent_message_id: Optional[str] = None
    model: str = "qwen2.5-coder:7b"
    chunks: List[ResponseChunk] = Field(default_factory=list)
    cumulative_tokens: int = 0
    status: ResponseStatus = ResponseStatus.GENERATING
    termination_reason: Optional[GenerationTermination] = None
    final_content: str = ""
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    active_version: int = 1

    def add_chunk(self, chunk: ResponseChunk) -> None:
        """Append chunk and update cumulative metadata."""
        self.chunks.append(chunk)
        self.cumulative_tokens += chunk.token_count
