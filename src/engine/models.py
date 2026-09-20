"""Structured Pydantic schemas for LLM reasoning and hypothesis generation."""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


class HypothesisDecision(str, Enum):
    NO_RELEVANT_FUNCTIONALITY = "NO_RELEVANT_FUNCTIONALITY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    HYPOTHESIS = "HYPOTHESIS" # Note: CONFIRMED is NEVER a valid model output!


class ViolationRelation(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"


class AppModelDelta(BaseModel):
    """Model-proposed assumption regarding application workflow or state."""
    observation: str
    epistemic_status: Literal["MODEL_PROPOSED"] = "MODEL_PROPOSED" # Model assumptions are strictly MODEL_PROPOSED


class ViolationAssessment(BaseModel):
    """Assessment of whether evidence supports or contradicts an invariant violation."""
    relation: ViolationRelation
    evidence_ids: List[str] = Field(default_factory=list)


class HypothesisModelOutput(BaseModel):
    """
    Authoritative structured output schema for the Hypothesis Engine (v6 Final).
    Enforces autoregressive reasoning progression via structured fields:
    app_model_delta -> violation_assessment -> decision -> category -> missing_evidence -> experiment_proposal -> safety_check
    """
    app_model_delta: Optional[AppModelDelta] = Field(
        default=None,
        description="Model-proposed assumption or observation regarding application state."
    )
    violation_assessment: Optional[ViolationAssessment] = Field(
        default=None,
        description="Assessment of whether cited evidence supports or contradicts the invariant violation."
    )
    decision: HypothesisDecision = Field(
        description="One of NO_RELEVANT_FUNCTIONALITY, INSUFFICIENT_EVIDENCE, HYPOTHESIS (never CONFIRMED)."
    )
    category: str = Field(description="Taxonomy category identifier, e.g. API-BOLA-001")
    asset_id: str = Field(description="Canonical asset ID from evidence graph")
    parameter_ids: List[str] = Field(default_factory=list, description="Canonical parameter IDs referenced")
    actor_identity_id: Optional[str] = Field(default=None, description="Requesting identity for authorization testing")
    target_identity_id: Optional[str] = Field(default=None, description="Resource-owning identity for authorization testing")
    reasoning_summary: Optional[str] = Field(default=None, description="Concise human-readable summary of rationale")
    missing_evidence: List[str] = Field(default_factory=list, description="Identified missing evidence gaps")
    experiment_proposal: Optional[str] = Field(default=None, description="Proposed verification experiment")
    safety_check: Optional[str] = Field(default=None, description="Safety check evaluation")
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    contradicting_evidence_ids: List[str] = Field(default_factory=list)
    cited_methodology_chunk_ids: List[str] = Field(
        default_factory=list,
        description="Cited VAPT methodology chunk IDs (CHK-xxx) supporting testing rationale or invariants."
    )
    evidence_sufficiency: float = Field(default=0.5, ge=0.0, le=1.0)

    @classmethod
    def get_inference_schema(cls) -> Dict[str, Any]:
        """
        Return the strict JSON schema for LLM inference.
        Enforces that the model MUST populate reasoning_summary, missing_evidence,
        and experiment_proposal in the generated GBNF grammar, preventing empty outputs.
        """
        schema = cls.model_json_schema()
        schema["required"] = [
            "decision",
            "category",
            "asset_id",
            "reasoning_summary",
            "missing_evidence",
            "experiment_proposal",
            "supporting_evidence_ids",
        ]
        return schema


# Formal M3 Model Output Alias per M3 Plan v2.3.8 Section 17 & 21
ReasoningHypothesis = HypothesisModelOutput
