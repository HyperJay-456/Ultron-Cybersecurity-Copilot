"""Pydantic schemas and domain models for Phase 12 AI Investigation Workspace."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EpistemicType(str, Enum):
    TARGET_OBSERVATION = "TARGET_OBSERVATION"
    FACT = "FACT"
    SECURITY_INVARIANT = "SECURITY_INVARIANT"
    EVIDENCE_GAP = "EVIDENCE_GAP"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    GENERAL_VAPT_KNOWLEDGE = "GENERAL_VAPT_KNOWLEDGE"
    HUMAN_VERIFIED_FINDING = "HUMAN_VERIFIED_FINDING"


class StructuredCardType(str, Enum):
    INVARIANT = "INVARIANT"
    HYPOTHESIS = "HYPOTHESIS"
    EXPERIMENT = "EXPERIMENT"
    APPROVAL = "APPROVAL"
    EXECUTION = "EXECUTION"
    OBSERVATION = "OBSERVATION"
    AUDIT = "AUDIT"
    NONE = "NONE"


class SystemStatusResponse(BaseModel):
    local_ai: str = "READY"
    ollama: str = "READY"
    evidence: str = "READY"
    vapt_rag: str = "READY"
    audit: str = "VERIFIED"
    active_model: str = "Cascade Active (3B → 7B)"
    cascade_mode: str = "CASCADE_ACTIVE_3B_7B"
    execution_mode: str = "SAFE_LOCAL_SIMULATION"
    gpu: Dict[str, Any] = Field(default_factory=dict)
    recent_traces: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InvestigationSummary(BaseModel):
    id: str
    name: str
    target_host: str
    scope_status: str = "ALLOWED"
    status: str = "ACTIVE"
    is_demo: bool = False
    evidence_count: int = 0
    hypothesis_count: int = 0
    experiment_count: int = 0
    message_count: int = 0
    last_activity: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CreateInvestigationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    target_host: str = Field(min_length=3, max_length=255)
    description: Optional[str] = None


class RenameInvestigationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ChatMessage(BaseModel):
    id: str
    investigation_id: str
    sender: str # "user" | "assistant" | "system"
    content: str
    structured_type: StructuredCardType = StructuredCardType.NONE
    structured_data: Optional[Dict[str, Any]] = None
    sequence_number: Optional[int] = None
    delivery_status: Optional[str] = "delivered"
    cascade_trace_id: Optional[str] = None
    model_name: Optional[str] = None
    model_digest: Optional[str] = None
    response_id: Optional[str] = None
    status: Optional[str] = "COMPLETED"
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InvestigationDetail(BaseModel):
    id: str
    name: str
    target_host: str
    scope_status: str = "ALLOWED"
    status: str = "ACTIVE"
    is_demo: bool = False
    evidence_count: int = 0
    hypothesis_count: int = 0
    messages: List[ChatMessage] = Field(default_factory=list)
    created_at: str
    updated_at: str


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    client_msg_id: Optional[str] = None


class ExperimentValidationResult(BaseModel):
    experiment_id: str
    valid: bool
    grounding_passed: bool
    polarity_passed: bool
    scope_passed: bool
    details: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


class ExperimentApprovalRequest(BaseModel):
    actor: str = Field(default="authorized_security_lead", min_length=2)
    safety_acknowledged: bool = Field(default=False)
    notes: Optional[str] = "Human verified safe test parameter substitution."


class ExperimentExecuteRequest(BaseModel):
    safe_simulation: bool = Field(default=True)


class ExecutionOutcomeResponse(BaseModel):
    experiment_id: str
    status: str # EXECUTED | BLOCKED_APPROVAL | BLOCKED_SCOPE | etc.
    success: bool
    timeline: List[Dict[str, Any]] = Field(default_factory=list)
    observation: Optional[Dict[str, Any]] = None
    hypothesis_state: Optional[str] = None
    new_evidence: Optional[Dict[str, Any]] = None
    audit_event: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class ImportTrafficRequest(BaseModel):
    format: str = Field(default="har", description="Import format: 'har', 'raw_http', or 'burp'")
    content: str = Field(min_length=1, description="Raw content of the import file or text")
    filename: Optional[str] = Field(default=None, description="Original filename if uploaded")


class ManualObservationRequest(BaseModel):
    method: str = Field(default="GET", min_length=3, max_length=10)
    host: Optional[str] = None
    path: str = Field(default="/", min_length=1)
    status_code: int = Field(default=200, ge=100, le=599)
    request_headers: Optional[Dict[str, str]] = Field(default_factory=dict)
    request_body: Optional[str] = ""
    response_headers: Optional[Dict[str, str]] = Field(default_factory=dict)
    response_body: Optional[str] = ""
    researcher_note: Optional[str] = None


# ---------------------------------------------------------------------------
# M6 Authorized Security Assessment Dashboard Schemas
# ---------------------------------------------------------------------------

class CreateAssessmentRequest(BaseModel):
    organization: str = Field(min_length=2, max_length=150)
    assessment_name: str = Field(min_length=2, max_length=150)
    created_by: str = Field(default="HUMAN_OPERATOR")


class UpdateAssessmentRequest(BaseModel):
    state: Optional[str] = None
    notes: Optional[str] = None


class SetAuthorizationRequest(BaseModel):
    organization: str
    assessment_name: str
    authorized_by: str
    valid_from: str
    valid_until: str
    authorization_type: str = "PENETRATION_TEST"
    scope_reference: str
    rules: List[str] = Field(default_factory=list)
    restrictions: List[str] = Field(default_factory=list)
    status: str = "AUTHORIZED"


class SetScopeRequest(BaseModel):
    program_name: str
    platform: str = "M6_ASSESSMENT"
    in_scope: List[str]
    out_of_scope: List[str] = Field(default_factory=list)


class CreateAssetRequest(BaseModel):
    asset_type: str = "DOMAIN"
    canonical_identifier: str
    parent_asset_id: Optional[str] = None
    scope_status: str = "IN_SCOPE"
    tags: List[str] = Field(default_factory=list)


class ImportTelemetryRequest(BaseModel):
    format_type: str
    payload: Any
    tool_name: Optional[str] = None


class ProposeExperimentRequest(BaseModel):
    hypothesis_id: str
    objective: str
    target_asset: str
    steps: List[str]
    expected_secure_result: str
    expected_vulnerable_result: str
    falsification_condition: str
    negative_control: str
    risk_level: str = "PASSIVE"


class ImportExperimentResultRequest(BaseModel):
    result_payload: Dict[str, Any]
    executed_by: str


class VerifyHypothesisRequest(BaseModel):
    action: str  # ACCEPT | REQUEST_EVIDENCE | REFUTE
    human_reviewer: str
    notes: str


class VerifyFindingRequest(BaseModel):
    human_reviewer: str
    justification: str


class CreateFindingRequest(BaseModel):
    title: str
    severity: str = "MEDIUM"
    asset: str
    affected_component: str
    description: str
    impact: str
    evidence: List[str] = Field(default_factory=list)
    reproduction_reference: str
    security_invariant: str
    root_cause: str
    remediation: str
    references: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# M11.5 Long Response Subsystem Schemas
# ---------------------------------------------------------------------------

class ResponseActionRequest(BaseModel):
    action: str = Field(description="Action: explain | summarize | expand | compare | checklist | indicators | evidence | report")
    detail: Optional[str] = None


class ContinueResponseRequest(BaseModel):
    custom_directive: Optional[str] = None


class StopResponseRequest(BaseModel):
    reason: Optional[str] = "User requested stop"


class RegenerateResponseRequest(BaseModel):
    temperature: Optional[float] = 0.7
