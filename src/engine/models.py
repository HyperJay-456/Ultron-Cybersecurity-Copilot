"""Structured Pydantic schemas for LLM reasoning and hypothesis generation.

Milestone M4: Canonical Base Schema (S0) and Deterministic Primary Failure Taxonomy.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


class HypothesisDecision(str, Enum):
    NO_RELEVANT_FUNCTIONALITY = "NO_RELEVANT_FUNCTIONALITY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    HYPOTHESIS = "HYPOTHESIS"  # Note: CONFIRMED is NEVER a valid model output!


class ViolationRelation(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"


class PrimaryFailureCategory(str, Enum):
    """
    Authoritative M4 Primary Failure Taxonomy (Mutually Exclusive).
    Precedence:
    RUNTIME_TRANSPORT_FAILURE > MAX_TOKEN_TRUNCATION > PARSER_FAILURE > SCHEMA_VALIDITY_FAILURE > SEMANTIC_GROUNDING_FAILURE > VALID
    """
    VALID = "VALID"
    RUNTIME_TRANSPORT_FAILURE = "RUNTIME_TRANSPORT_FAILURE"
    MAX_TOKEN_TRUNCATION = "MAX_TOKEN_TRUNCATION"
    PARSER_FAILURE = "PARSER_FAILURE"
    SCHEMA_VALIDITY_FAILURE = "SCHEMA_VALIDITY_FAILURE"
    SEMANTIC_GROUNDING_FAILURE = "SEMANTIC_GROUNDING_FAILURE"


class FailureClassificationResult(BaseModel):
    """Deterministic failure classification result adhering to M4 primary precedence rules."""
    primary_category: PrimaryFailureCategory
    is_valid: bool
    error_message: Optional[str] = None
    downstream_cascade: List[str] = Field(default_factory=list)
    diagnostic_details: Dict[str, Any] = Field(default_factory=dict)


class AppModelDelta(BaseModel):
    """Model-proposed assumption regarding application workflow or state."""
    observation: str
    epistemic_status: Literal["MODEL_PROPOSED"] = "MODEL_PROPOSED"  # Model assumptions are strictly MODEL_PROPOSED


class ViolationAssessment(BaseModel):
    """Assessment of whether evidence supports or contradicts an invariant violation."""
    relation: ViolationRelation
    evidence_ids: List[str] = Field(default_factory=list)


class HypothesisModelOutput(BaseModel):
    """
    Authoritative structured output schema for the Reasoning Engine (M4 S0 Canonical).
    Preserves canonical S0 fields:
    invariant, evidence_gap, affected_target, decision, supporting_evidence_ids,
    methodology_references, reasoning_summary, experiment_proposal.
    """
    # Canonical S0 fields (M4 Section 8 I1 / Section 10.1)
    invariant: Optional[str] = Field(
        default=None,
        description="Target security invariant statement evaluated against available evidence."
    )
    evidence_gap: Optional[str] = Field(
        default=None,
        description="Identified evidence gap or uncertainty regarding target application state."
    )
    affected_target: Optional[str] = Field(
        default=None,
        description="Target endpoint, canonical asset ID, or parameter under evaluation."
    )
    decision: HypothesisDecision = Field(
        description="One of NO_RELEVANT_FUNCTIONALITY, INSUFFICIENT_EVIDENCE, HYPOTHESIS (never CONFIRMED)."
    )
    supporting_evidence_ids: List[str] = Field(
        default_factory=list,
        description="Canonical observation fact IDs supporting the invariant evaluation."
    )
    methodology_references: List[str] = Field(
        default_factory=list,
        description="Referenced VAPT methodology guidance identifiers."
    )
    reasoning_summary: Optional[str] = Field(
        default=None,
        description="Concise human-readable summary of rationale."
    )
    experiment_proposal: Optional[str] = Field(
        default=None,
        description="Proposed verification experiment to confirm or refute the hypothesis."
    )

    # M2 / M3 backwards-compatibility & telemetry fields
    category: Optional[str] = Field(
        default=None,
        description="Taxonomy category identifier, e.g. API-BOLA-001"
    )
    asset_id: Optional[str] = Field(
        default=None,
        description="Canonical asset ID from evidence graph"
    )
    parameter_ids: List[str] = Field(
        default_factory=list,
        description="Canonical parameter IDs referenced"
    )
    missing_evidence: List[str] = Field(
        default_factory=list,
        description="Identified missing evidence gaps"
    )
    cited_methodology_chunk_ids: List[str] = Field(
        default_factory=list,
        description="Cited VAPT methodology chunk IDs (CHK-xxx) supporting testing rationale or invariants."
    )
    contradicting_evidence_ids: List[str] = Field(
        default_factory=list
    )
    app_model_delta: Optional[AppModelDelta] = Field(
        default=None,
        description="Model-proposed assumption or observation regarding application state."
    )
    violation_assessment: Optional[ViolationAssessment] = Field(
        default=None,
        description="Assessment of whether cited evidence supports or contradicts the invariant violation."
    )
    actor_identity_id: Optional[str] = Field(
        default=None,
        description="Requesting identity for authorization testing"
    )
    target_identity_id: Optional[str] = Field(
        default=None,
        description="Resource-owning identity for authorization testing"
    )
    safety_check: Optional[str] = Field(
        default=None,
        description="Safety check evaluation"
    )
    evidence_sufficiency: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0
    )

    @model_validator(mode="after")
    def sync_canonical_and_legacy_fields(self) -> "HypothesisModelOutput":
        # Synchronize methodology_references and cited_methodology_chunk_ids
        if self.methodology_references and not self.cited_methodology_chunk_ids:
            self.cited_methodology_chunk_ids = list(self.methodology_references)
        elif self.cited_methodology_chunk_ids and not self.methodology_references:
            self.methodology_references = list(self.cited_methodology_chunk_ids)

        # Synchronize affected_target and asset_id
        if self.affected_target and not self.asset_id:
            self.asset_id = self.affected_target
        elif self.asset_id and not self.affected_target:
            self.affected_target = self.asset_id

        # Synchronize evidence_gap and missing_evidence
        if self.evidence_gap and not self.missing_evidence:
            self.missing_evidence = [self.evidence_gap]
        elif self.missing_evidence and not self.evidence_gap:
            self.evidence_gap = "; ".join(self.missing_evidence)

        return self

    @classmethod
    def get_inference_schema(cls) -> Dict[str, Any]:
        """
        Return the strict canonical S0 JSON schema for LLM inference.
        Preserves the 8 canonical fields defined by the M4 specification:
        - invariant
        - evidence_gap
        - affected_target
        - decision
        - supporting_evidence_ids
        - methodology_references
        - reasoning_summary
        - experiment_proposal

        No I2 namespace regex constraints.
        No field-length compaction.
        Standard type constraints only.
        """
        return {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "string",
                    "enum": [
                        "NO_RELEVANT_FUNCTIONALITY",
                        "INSUFFICIENT_EVIDENCE",
                        "HYPOTHESIS",
                    ],
                    "description": "One of NO_RELEVANT_FUNCTIONALITY, INSUFFICIENT_EVIDENCE, HYPOTHESIS (never CONFIRMED).",
                },
                "invariant": {
                    "type": "string",
                    "description": "Target security invariant statement evaluated against available evidence.",
                },
                "evidence_gap": {
                    "type": "string",
                    "description": "Identified evidence gap or uncertainty regarding target application state.",
                },
                "affected_target": {
                    "type": "string",
                    "description": "Target endpoint, canonical asset ID, or parameter under evaluation.",
                },
                "supporting_evidence_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Canonical observation fact IDs supporting the invariant evaluation.",
                },
                "methodology_references": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Referenced VAPT methodology guidance identifiers.",
                },
                "reasoning_summary": {
                    "type": "string",
                    "description": "Concise human-readable summary of rationale.",
                },
                "experiment_proposal": {
                    "type": "string",
                    "description": "Proposed verification experiment to confirm or refute the hypothesis.",
                },
            },
            "required": [
                "decision",
                "invariant",
                "evidence_gap",
                "affected_target",
                "supporting_evidence_ids",
                "methodology_references",
                "reasoning_summary",
                "experiment_proposal",
            ],
        }


# Formal M3 Model Output Alias per M3 Plan v2.3.8 Section 17 & 21
ReasoningHypothesis = HypothesisModelOutput


class I1ExecutionResult(BaseModel):
    """Result of an authoritative I1 schema-constrained structured generation attempt."""
    raw_response: str
    parsed_json: Optional[Dict[str, Any]] = None
    hypothesis: Optional[HypothesisModelOutput] = None
    classification: FailureClassificationResult
    latency_ms: float = 0.0
    eval_count: Optional[int] = None
    prompt_eval_count: Optional[int] = None
    diagnostic_repair: Optional[Dict[str, Any]] = None
    grounding_result: Optional[Dict[str, Any]] = None


def classify_primary_failure(
    transport_error: Optional[Exception] = None,
    raw_response: Optional[str] = None,
    eval_count: Optional[int] = None,
    done_reason: Optional[str] = None,
    num_predict: int = 300,
    parsed_json: Optional[Dict[str, Any]] = None,
    parse_error: Optional[Exception] = None,
    schema_error: Optional[Exception] = None,
    grounding_error: Optional[str] = None,
) -> FailureClassificationResult:
    """
    Deterministically classify an evaluation attempt into exactly one mutually exclusive PRIMARY category.

    Precedence:
    RUNTIME_TRANSPORT_FAILURE > MAX_TOKEN_TRUNCATION > PARSER_FAILURE > SCHEMA_VALIDITY_FAILURE > SEMANTIC_GROUNDING_FAILURE > VALID
    """
    cascade: List[str] = []

    # 1. RUNTIME_TRANSPORT_FAILURE (Precedence 1)
    if transport_error is not None:
        return FailureClassificationResult(
            primary_category=PrimaryFailureCategory.RUNTIME_TRANSPORT_FAILURE,
            is_valid=False,
            error_message=str(transport_error),
            downstream_cascade=[],
            diagnostic_details={"exception_type": type(transport_error).__name__},
        )

    # Check whether generation reached num_predict or was stopped by length
    is_truncation = False
    if eval_count is not None and eval_count >= num_predict:
        is_truncation = True
    elif done_reason == "length":
        is_truncation = True

    # 2. MAX_TOKEN_TRUNCATION (Precedence 2)
    # If output reached num_predict and failed parsing or schema validation, it is primary truncation.
    if is_truncation and (parse_error is not None or schema_error is not None or parsed_json is None):
        if parse_error is not None:
            cascade.append(PrimaryFailureCategory.PARSER_FAILURE.value)
        if schema_error is not None:
            cascade.append(PrimaryFailureCategory.SCHEMA_VALIDITY_FAILURE.value)
        return FailureClassificationResult(
            primary_category=PrimaryFailureCategory.MAX_TOKEN_TRUNCATION,
            is_valid=False,
            error_message=f"Terminated at {num_predict} token ceiling mid-generation (eval_count={eval_count}, done_reason={done_reason})",
            downstream_cascade=cascade,
            diagnostic_details={
                "eval_count": eval_count,
                "done_reason": done_reason,
                "raw_length_chars": len(raw_response) if raw_response else 0,
            },
        )

    # 3. PARSER_FAILURE (Precedence 3)
    if parse_error is not None:
        return FailureClassificationResult(
            primary_category=PrimaryFailureCategory.PARSER_FAILURE,
            is_valid=False,
            error_message=f"Invalid JSON syntax: {parse_error}",
            downstream_cascade=[],
            diagnostic_details={"exception_type": type(parse_error).__name__},
        )

    # 4. SCHEMA_VALIDITY_FAILURE (Precedence 4)
    if schema_error is not None:
        return FailureClassificationResult(
            primary_category=PrimaryFailureCategory.SCHEMA_VALIDITY_FAILURE,
            is_valid=False,
            error_message=f"Schema validation error: {schema_error}",
            downstream_cascade=[],
            diagnostic_details={"exception_type": type(schema_error).__name__},
        )

    # 5. SEMANTIC_GROUNDING_FAILURE (Precedence 5)
    if grounding_error is not None:
        return FailureClassificationResult(
            primary_category=PrimaryFailureCategory.SEMANTIC_GROUNDING_FAILURE,
            is_valid=False,
            error_message=f"Grounding failure: {grounding_error}",
            downstream_cascade=[],
            diagnostic_details={"grounding_error": grounding_error},
        )

    # 0. VALID
    return FailureClassificationResult(
        primary_category=PrimaryFailureCategory.VALID,
        is_valid=True,
        error_message=None,
        downstream_cascade=[],
        diagnostic_details={},
    )


def perform_diagnostic_repair(
    raw_dict: Dict[str, Any],
    target_asset: Optional[Dict[str, Any]] = None,
    category_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    DIAGNOSTIC ONLY.
    Records what post-hoc repairs could theoretically be applied.
    MUST NOT alter authoritative scoring or upgrade invalid outputs to valid.
    """
    repaired = dict(raw_dict)
    repairs_applied = []

    if not repaired.get("affected_target") and target_asset and target_asset.get("asset_id"):
        repaired["affected_target"] = target_asset["asset_id"]
        repairs_applied.append("injected_affected_target_from_context")

    if not repaired.get("decision"):
        repaired["decision"] = HypothesisDecision.NO_RELEVANT_FUNCTIONALITY.value
        repairs_applied.append("defaulted_missing_decision_to_abstention")

    cleaned_ids = []
    for eid in repaired.get("supporting_evidence_ids", []):
        if isinstance(eid, str):
            cleaned = eid.strip()
            if cleaned.startswith("EVIDENCE [") and cleaned.endswith("]"):
                cleaned = cleaned[10:-1].strip()
            elif cleaned.startswith("[") and cleaned.endswith("]"):
                cleaned = cleaned[1:-1].strip()
            elif cleaned.startswith("EVIDENCE-"):
                cleaned = cleaned[9:].strip()
            if cleaned != eid:
                repairs_applied.append(f"cleaned_evidence_id_prefix:{eid}->{cleaned}")
            cleaned_ids.append(cleaned)
        else:
            cleaned_ids.append(str(eid))
    repaired["supporting_evidence_ids"] = cleaned_ids

    return {
        "diagnostic_only": True,
        "repairs_applied": repairs_applied,
        "repaired_dict": repaired,
    }
