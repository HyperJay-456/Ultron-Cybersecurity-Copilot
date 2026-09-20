"""VAPT Knowledge RAG Subsystem (Milestone M3).

Provides epistemically isolated, offline, cryptographically verifiable
security methodology and testing guidance.
"""

from src.knowledge.models import (
    EpistemicTier,
    EvidenceGapType,
    KnowledgeChunk,
    KnowledgeDocumentFrontmatter,
    KnowledgeRetrievalItem,
    KnowledgeSourceType,
    KnowledgeType,
    QueryRendererId,
    VaptKnowledgePack,
)
from src.knowledge.serializer import ProductionP4Serializer
from src.knowledge.grounding_validator import (
    KnowledgeGroundingResult,
    KnowledgeGroundingValidator,
)
from src.knowledge.poisoning_defense import KnowledgePoisoningDefense
from src.knowledge.pipeline import VaptReasoningPipeline

__all__ = [
    "KnowledgeSourceType",
    "KnowledgeType",
    "EpistemicTier",
    "EvidenceGapType",
    "QueryRendererId",
    "KnowledgeChunk",
    "KnowledgeRetrievalItem",
    "VaptKnowledgePack",
    "KnowledgeDocumentFrontmatter",
    "ProductionP4Serializer",
    "KnowledgeGroundingValidator",
    "KnowledgeGroundingResult",
    "KnowledgePoisoningDefense",
    "VaptReasoningPipeline",
]
