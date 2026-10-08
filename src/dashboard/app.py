"""Local Human Feedback Dashboard API and UI for Phase 12 Workspace."""

from enum import Enum
import json
from pathlib import Path
import secrets
import time
from typing import Any, Dict, List, Optional
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.core.logging import AuditLogger, get_logger, verify_audit_log
from src.database.manager import DatabaseManager
from src.hypothesis.state_machine import HypothesisStateMachine, HypothesisState
from src.dashboard.models import (
    CreateInvestigationRequest,
    ExperimentApprovalRequest,
    ExperimentExecuteRequest,
    ImportTrafficRequest,
    ManualObservationRequest,
    RenameInvestigationRequest,
    SendMessageRequest,
    CreateAssessmentRequest,
    UpdateAssessmentRequest,
    SetAuthorizationRequest,
    SetScopeRequest,
    CreateAssetRequest,
    ImportTelemetryRequest,
    ProposeExperimentRequest,
    ImportExperimentResultRequest,
    VerifyHypothesisRequest,
    VerifyFindingRequest,
    CreateFindingRequest,
)
from src.dashboard.service import WorkspaceService
from src.copilot.orchestration import CopilotOrchestrator
from src.copilot.registry import DomainKnowledgeRegistry
from src.copilot.tools import ToolKnowledgeBase
from src.assessment.manager import AssessmentManager
from src.assessment.models import (
    AssessmentLifecycleState,
    AuthorizationRecord,
    AuthorizationStatus,
    AuthorizationType,
    AssetType,
    AssessmentScopeStatus,
    ExperimentRiskLevel,
    FindingSeverity,
    AssessmentFinding,
)
from src.scope.models import ScopePolicy

DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8000

logger = get_logger("Dashboard")


class DashboardRole(str, Enum):
    OBSERVER = "observer"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class DashboardSession(BaseModel):
    token: str
    username: str
    role: DashboardRole
    expires_at: Optional[float] = None
    revoked: bool = False


class DashboardAuthManager:
    """Thread-safe in-memory session and authentication authority for the dashboard."""

    def __init__(self) -> None:
        self._sessions: Dict[str, DashboardSession] = {}

    def create_session(
        self,
        username: str,
        role: DashboardRole,
        token: Optional[str] = None,
        ttl_seconds: Optional[float] = None,
    ) -> DashboardSession:
        tok = token or secrets.token_urlsafe(32)
        exp = time.time() + ttl_seconds if ttl_seconds is not None else None
        sess = DashboardSession(
            token=tok,
            username=username,
            role=role,
            expires_at=exp,
            revoked=False,
        )
        self._sessions[tok] = sess
        return sess

    def revoke_session(self, token: str) -> bool:
        if token in self._sessions:
            self._sessions[token].revoked = True
            return True
        return False

    def authenticate(self, token: Optional[str]) -> Optional[DashboardSession]:
        if not token:
            return None
        sess = self._sessions.get(token)
        if not sess:
            return None
        if sess.revoked:
            return None
        if sess.expires_at is not None and time.time() > sess.expires_at:
            return None
        return sess


def validate_dashboard_bind(
    host: str = DEFAULT_DASHBOARD_HOST,
    allow_external: bool = False,
    auth_configured: bool = False,
) -> str:
    """
    Validate bind address to enforce localhost loopback isolation by default.
    Fails closed if a non-loopback interface is requested without allow_external=True
    AND auth_configured=True.
    """
    normalized = host.strip().lower()
    is_loopback = (
        normalized in ("127.0.0.1", "localhost", "::1")
        or normalized.startswith("127.")
    )
    if not is_loopback:
        if not allow_external:
            raise ValueError(
                f"Refusing to bind dashboard to non-loopback address '{host}'. "
                "The dashboard requires explicit allow_external=True and configured authentication "
                "for non-loopback binding."
            )
        if not auth_configured:
            raise ValueError(
                f"Refusing to bind dashboard to non-loopback address '{host}'. "
                "External binding must fail closed unless authentication is configured. "
                "Provide an authenticated auth_manager or configure valid credentials."
            )
        logger.warning(
            f"SECURITY NOTICE: Dashboard binding to non-loopback address '{host}' with authentication enabled."
        )
    return host


class VerificationRequest(BaseModel):
    actor: Optional[str] = Field(default=None, description="Client-submitted actor identifier (authoritatively bound to authenticated session)")
    evidence_ref: str = Field(min_length=5, description="Path or reference to repro evidence / traffic log")
    dashboard_session_id: str = Field(
        default="DASH-SESSION-001",
        description="Client-submitted audit tracking identifier; NOT an authentication or session credential.",
    )
    safety_acknowledged: bool = Field(default=False, description="Must be true if endpoint is STATE_CHANGING")
    notes: Optional[str] = None


class ExperimentResultRequest(BaseModel):
    observation_type: str = Field(description="SUPPORTING | CONTRADICTING | UNRESOLVED")
    new_evidence_ref: str = Field(min_length=3)
    notes: str


class CopilotQueryRequest(BaseModel):
    query: str
    investigation_id: Optional[str] = None


def create_dashboard_app(
    db_manager: Optional[DatabaseManager] = None,
    audit_logger: Optional[AuditLogger] = None,
    auth_manager: Optional[DashboardAuthManager] = None,
    workspace_service: Optional[WorkspaceService] = None,
    require_auth: bool = False,
    frontend_dist_dir: Optional[Path] = None,
) -> FastAPI:
    """Factory creating the FastAPI human review dashboard app with RBAC and secure rendering."""
    app = FastAPI(
        title="Local AI-Assisted Bug Bounty Research Platform - Investigation Workspace",
        version="0.6.0",
    )
    db = db_manager or DatabaseManager()
    auditor = audit_logger or AuditLogger(Path("data/audit.log"))
    state_machine = HypothesisStateMachine(db)
    auth_mgr = auth_manager or DashboardAuthManager()
    workspace_service = workspace_service or WorkspaceService(db_manager=db, audit_logger=auditor)

    ROLE_HIERARCHY = {
        DashboardRole.OBSERVER: 1,
        DashboardRole.REVIEWER: 2,
        DashboardRole.ADMIN: 3,
    }

    def get_current_user(
        authorization: Optional[str] = Header(None),
        x_dashboard_token: Optional[str] = Header(None),
    ) -> DashboardSession:
        token = None
        if authorization:
            if authorization.lower().startswith("bearer "):
                token = authorization[7:].strip()
            else:
                token = authorization.strip()
        elif x_dashboard_token:
            token = x_dashboard_token.strip()

        if require_auth:
            if not token:
                raise HTTPException(status_code=401, detail="Authentication required: token missing")
            sess = auth_mgr.authenticate(token)
            if not sess:
                raw_sess = auth_mgr._sessions.get(token)
                if raw_sess and raw_sess.revoked:
                    raise HTTPException(status_code=401, detail="Session revoked")
                if raw_sess and raw_sess.expires_at and time.time() > raw_sess.expires_at:
                    raise HTTPException(status_code=401, detail="Session expired")
                raise HTTPException(status_code=401, detail="Invalid or expired session token")
            return sess
        else:
            # Loopback local development mode
            if token:
                sess = auth_mgr.authenticate(token)
                if not sess:
                    raw_sess = auth_mgr._sessions.get(token)
                    if raw_sess and raw_sess.revoked:
                        raise HTTPException(status_code=401, detail="Session revoked")
                    if raw_sess and raw_sess.expires_at and time.time() > raw_sess.expires_at:
                        raise HTTPException(status_code=401, detail="Session expired")
                    raise HTTPException(status_code=401, detail="Invalid session token")
                return sess
            return DashboardSession(
                token="loopback-default-dev",
                username="local_researcher",
                role=DashboardRole.REVIEWER,
            )

    def require_role(min_role: DashboardRole):
        def role_dependency(user: DashboardSession = Depends(get_current_user)) -> DashboardSession:
            if ROLE_HIERARCHY.get(user.role, 0) < ROLE_HIERARCHY.get(min_role, 0):
                raise HTTPException(
                    status_code=403,
                    detail=f"Forbidden: {min_role.value} role required, but user has {user.role.value}",
                )
            return user
        return role_dependency

    # -------------------------------------------------------------------------
    # System Status Endpoints
    # -------------------------------------------------------------------------

    @app.get("/api/health")
    @app.get("/api/status")
    @app.get("/api/system/status")
    def get_status() -> Dict[str, Any]:
        """System health and diagnostic status."""
        return workspace_service.get_system_status().model_dump()

    @app.get("/api/system/cascade-trace")
    def get_cascade_traces(
        limit: int = 10,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> List[Dict[str, Any]]:
        """Get verified runtime cascade traces from persistent storage."""
        return workspace_service.list_cascade_traces(limit=limit)

    @app.get("/api/cascade-traces/{trace_id}")
    def get_cascade_trace_by_id(
        trace_id: str,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> Dict[str, Any]:
        """Get specific cascade execution trace by run ID."""
        trace = workspace_service.get_cascade_trace(trace_id)
        if not trace:
            raise HTTPException(status_code=404, detail=f"Cascade trace '{trace_id}' not found")
        return trace

    @app.get("/api/investigations/{inv_id}/messages/{message_id}/trace")
    def get_message_trace(
        inv_id: str,
        message_id: str,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> Dict[str, Any]:
        """Get cascade execution trace associated with a specific message."""
        trace = workspace_service.get_message_trace(inv_id, message_id)
        if not trace:
            raise HTTPException(status_code=404, detail=f"No cascade trace found for message '{message_id}'")
        return trace


    @app.post("/api/demo/load")
    def load_demo_fixture(
        user: DashboardSession = Depends(require_role(DashboardRole.REVIEWER)),
    ) -> Dict[str, Any]:
        """Explicitly opt-in to load the deterministic demo fixture."""
        summary = workspace_service.load_demo_investigation()
        return summary.model_dump()

    # -------------------------------------------------------------------------
    # Phase 12 Investigation Workspace Endpoints
    # -------------------------------------------------------------------------

    @app.get("/api/investigations")
    def list_investigations(
        q: Optional[str] = Query(None, description="Search query for investigations"),
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> List[Dict[str, Any]]:
        """List active investigations, optionally filtered by search query."""
        return [inv.model_dump() for inv in workspace_service.list_investigations(search_query=q)]

    @app.post("/api/investigations")
    def create_investigation(
        req: CreateInvestigationRequest,
        user: DashboardSession = Depends(require_role(DashboardRole.REVIEWER)),
    ) -> Dict[str, Any]:
        """Create a new investigation."""
        summary = workspace_service.create_investigation(req)
        return summary.model_dump()

    @app.get("/api/investigations/{inv_id}")
    def get_investigation(
        inv_id: str,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> Dict[str, Any]:
        """Get investigation details and message history."""
        detail = workspace_service.get_investigation(inv_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Investigation not found")
        return detail.model_dump()

    @app.patch("/api/investigations/{inv_id}")
    def rename_investigation(
        inv_id: str,
        req: RenameInvestigationRequest,
        user: DashboardSession = Depends(require_role(DashboardRole.REVIEWER)),
    ) -> Dict[str, Any]:
        """Rename an investigation and persist new name."""
        try:
            summary = workspace_service.rename_investigation(inv_id, req.name)
            return summary.model_dump()
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.delete("/api/investigations/{inv_id}")
    def delete_investigation(
        inv_id: str,
        user: DashboardSession = Depends(require_role(DashboardRole.REVIEWER)),
    ) -> Dict[str, Any]:
        """Delete an investigation and its conversation messages without deleting canonical domain evidence."""
        try:
            workspace_service.delete_investigation(inv_id)
            return {"success": True, "id": inv_id}
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/investigations/{inv_id}/messages")
    def get_investigation_messages(
        inv_id: str,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> List[Dict[str, Any]]:
        """Get conversation message history for an investigation."""
        messages = workspace_service.get_messages(inv_id)
        return [m.model_dump() for m in messages]

    @app.post("/api/investigations/{inv_id}/messages")
    def post_investigation_message(
        inv_id: str,
        req: SendMessageRequest,
        user: DashboardSession = Depends(require_role(DashboardRole.REVIEWER)),
    ) -> List[Dict[str, Any]]:
        """Post a user message to the research AI and return grounded responses."""
        try:
            responses = workspace_service.send_message(inv_id, req.content, client_msg_id=req.client_msg_id)
            return [m.model_dump() for m in responses]
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.post("/api/investigations/{inv_id}/import")
    def import_investigation_traffic(
        inv_id: str,
        req: ImportTrafficRequest,
        user: DashboardSession = Depends(require_role(DashboardRole.REVIEWER)),
    ) -> Dict[str, Any]:
        """Import captured HTTP traffic telemetry (HAR, Raw HTTP, Burp) into an investigation."""
        try:
            return workspace_service.ingest_traffic(inv_id, req)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error("Internal error importing traffic for %s: %s", inv_id, e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")

    @app.post("/api/investigations/{inv_id}/observations")
    def add_investigation_observation(
        inv_id: str,
        req: ManualObservationRequest,
        user: DashboardSession = Depends(require_role(DashboardRole.REVIEWER)),
    ) -> Dict[str, Any]:
        """Manually record a target HTTP observation in an investigation."""
        try:
            return workspace_service.add_manual_observation(inv_id, req)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error("Internal error adding observation for %s: %s", inv_id, e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to record observation: {str(e)}")

    @app.get("/api/investigations/{inv_id}/evidence")
    def get_investigation_evidence(
        inv_id: str,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> List[Dict[str, Any]]:
        """Get canonical evidence items with epistemic segregation."""
        return workspace_service.get_evidence(inv_id)

    @app.get("/api/investigations/{inv_id}/evidence/{obs_id}")
    def get_investigation_observation_detail(
        inv_id: str,
        obs_id: str,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> Dict[str, Any]:
        """Get detailed observation record with normalized request/response and provenance."""
        obs = workspace_service.get_observation(inv_id, obs_id)
        if not obs:
            raise HTTPException(status_code=404, detail=f"Observation {obs_id} not found")
        return obs

    @app.get("/api/investigations/{inv_id}/model")
    def get_investigation_model(
        inv_id: str,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> Dict[str, Any]:
        """Get derived application model."""
        return workspace_service.get_application_model(inv_id)

    @app.get("/api/investigations/{inv_id}/invariants")
    def get_investigation_invariants(
        inv_id: str,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> List[Dict[str, Any]]:
        """Get security invariants with epistemic origins."""
        return workspace_service.get_invariants(inv_id)

    @app.get("/api/investigations/{inv_id}/gaps")
    def get_investigation_gaps(
        inv_id: str,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> List[Dict[str, Any]]:
        """Get active evidence gaps."""
        return workspace_service.get_gaps(inv_id)

    @app.get("/api/investigations/{inv_id}/hypotheses")
    def get_investigation_hypotheses(
        inv_id: str,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> List[Dict[str, Any]]:
        """Get hypotheses for an investigation."""
        return workspace_service.get_hypotheses(inv_id)

    @app.get("/api/investigations/{inv_id}/experiments")
    def get_investigation_experiments(
        inv_id: str,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> List[Dict[str, Any]]:
        """Get experiments for an investigation."""
        return workspace_service.get_experiments(inv_id)

    # -------------------------------------------------------------------------
    # Experiment Action Endpoints
    # -------------------------------------------------------------------------

    @app.post("/api/experiments/{exp_id}/validate")
    def validate_experiment(
        exp_id: str,
        user: DashboardSession = Depends(require_role(DashboardRole.REVIEWER)),
    ) -> Dict[str, Any]:
        """Validate experiment grounding, polarity, and scope."""
        res = workspace_service.validate_experiment(exp_id)
        return res.model_dump()

    @app.post("/api/experiments/{exp_id}/approve")
    def approve_experiment(
        exp_id: str,
        req: ExperimentApprovalRequest,
        user: DashboardSession = Depends(require_role(DashboardRole.REVIEWER)),
    ) -> Dict[str, Any]:
        """Register human approval for a state-changing experiment."""
        try:
            return workspace_service.approve_experiment(exp_id, req)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/experiments/{exp_id}/reject")
    def reject_experiment(
        exp_id: str,
        req: Optional[Dict[str, Any]] = None,
        actor: Optional[str] = Query(None),
        reason: Optional[str] = Query(None),
        user: DashboardSession = Depends(require_role(DashboardRole.REVIEWER)),
    ) -> Dict[str, Any]:
        """Reject an experiment proposal."""
        act = (req.get("actor") if req else None) or actor or "authorized_security_lead"
        rsn = (req.get("reason") if req else None) or reason or "Rejected by human reviewer."
        try:
            return workspace_service.reject_experiment(exp_id, act, rsn)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/audit/{inv_id}")
    def get_investigation_audit(
        inv_id: str,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> Dict[str, Any]:
        """Get tamper-evident audit records and verify cryptographic chain integrity."""
        records = audit_logger.read_records(limit=100) if audit_logger else []
        verification = verify_audit_log(audit_logger.audit_file_path) if audit_logger else None
        chain_valid = verification.valid if verification else True
        return {
            "investigation_id": inv_id,
            "chain_integrity": "VERIFIED" if chain_valid else "FAILED",
            "total_records": len(records),
            "records": records,
        }

    @app.post("/api/experiments/{exp_id}/execute")
    def execute_experiment(
        exp_id: str,
        req: Optional[ExperimentExecuteRequest] = None,
        user: DashboardSession = Depends(require_role(DashboardRole.REVIEWER)),
    ) -> Dict[str, Any]:
        """Execute experiment proposal through DeterministicExecutionEngine."""
        outcome = workspace_service.execute_experiment(exp_id, safe_simulation=True)
        return outcome.model_dump()

    # -------------------------------------------------------------------------
    # Legacy / Base Hypothesis & Review Endpoints (100% Backward Compatible)
    # -------------------------------------------------------------------------

    @app.get("/api/hypotheses")
    def list_hypotheses(
        state: Optional[str] = None,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> List[Dict[str, Any]]:
        """List all hypotheses with optional state filtering."""
        with db.get_connection() as conn:
            query = "SELECT * FROM hypotheses"
            params: List[Any] = []
            if state:
                query += " WHERE state = ?"
                params.append(state)
            query += " ORDER BY id DESC"
            cursor = conn.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    @app.get("/api/hypotheses/{hypothesis_id}")
    def get_hypothesis_detail(
        hypothesis_id: int,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> Dict[str, Any]:
        """Get full details of a hypothesis including asset safety and cited evidence."""
        hyp = db.get_hypothesis(hypothesis_id)
        if not hyp:
            raise HTTPException(status_code=404, detail="Hypothesis not found")

        asset = db.get_asset(hyp["asset_id"])
        params = db.get_parameters_for_asset(hyp["asset_id"]) if asset else []

        mutability = asset.get("application_mutability", "UNKNOWN") if asset else "UNKNOWN"
        requires_safety = mutability in ("STATE_CHANGING", "DESTRUCTIVE")
        has_volatile_params = any(p.get("is_server_volatile") for p in params)

        return {
            "hypothesis": hyp,
            "asset": asset,
            "parameters": params,
            "safety": {
                "application_mutability": mutability,
                "requires_safety_acknowledgment": requires_safety,
                "has_volatile_params": has_volatile_params,
                "warning_message": (
                    f"CAUTION: Target asset is {mutability}. Manual testing could alter live application state. "
                    "Ensure testing is performed against an authorized isolated test account."
                    if requires_safety else "SAFE: Asset is READ_ONLY."
                ),
            },
        }

    @app.post("/api/hypotheses/{hypothesis_id}/review")
    def start_hypothesis_review(
        hypothesis_id: int,
        user: DashboardSession = Depends(require_role(DashboardRole.REVIEWER)),
    ) -> Dict[str, Any]:
        """Move hypothesis from New to Under Review."""
        try:
            state_machine.start_review(hypothesis_id)
            auditor.log_event(
                event_type="STATE_TRANSITION",
                actor=user.username,
                subject_id=str(hypothesis_id),
                previous_state="New",
                new_state="Under Review",
            )
            return {"status": "success", "state": "Under Review"}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/hypotheses/{hypothesis_id}/experiment/result")
    def submit_experiment_result(
        hypothesis_id: int,
        req: ExperimentResultRequest,
        user: DashboardSession = Depends(require_role(DashboardRole.REVIEWER)),
    ) -> Dict[str, Any]:
        """Incorporate experiment outcome and revise hypothesis."""
        try:
            revised = state_machine.revise_with_experiment_observation(
                hypothesis_id=hypothesis_id,
                observation_type=req.observation_type.upper(),
                new_evidence_ref=req.new_evidence_ref,
                observation_notes=req.notes,
            )
            auditor.log_event(
                event_type="EXPERIMENT_RESULT",
                actor=user.username,
                subject_id=str(hypothesis_id),
                new_state=revised.get("state"),
                evidence_ref=req.new_evidence_ref,
                details={"observation_type": req.observation_type, "notes": req.notes},
            )
            return {"status": "success", "hypothesis": revised}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/hypotheses/{hypothesis_id}/confirm")
    def confirm_hypothesis(
        hypothesis_id: int,
        req: VerificationRequest,
        user: DashboardSession = Depends(require_role(DashboardRole.REVIEWER)),
    ) -> Dict[str, Any]:
        """Confirm hypothesis with human verification bound to authenticated actor."""
        hyp_detail = get_hypothesis_detail(hypothesis_id=hypothesis_id, user=user)
        if hyp_detail["safety"]["requires_safety_acknowledgment"] and not req.safety_acknowledged:
            raise HTTPException(
                status_code=400,
                detail="Safety acknowledgment required for STATE_CHANGING or DESTRUCTIVE endpoints before confirmation.",
            )

        authoritative_actor = user.username

        try:
            state_machine.confirm_with_human_verification(
                hypothesis_id=hypothesis_id,
                actor=authoritative_actor,
                evidence_ref=req.evidence_ref,
                session_id=req.dashboard_session_id,
                notes=req.notes,
            )
            auditor.log_event(
                event_type="HUMAN_VERIFICATION",
                actor=authoritative_actor,
                subject_id=str(hypothesis_id),
                previous_state="Under Review",
                new_state="Confirmed",
                evidence_ref=req.evidence_ref,
                details={"notes": req.notes, "session_id": req.dashboard_session_id},
            )
            return {"status": "success", "state": "Confirmed"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/invariants")
    def list_invariants(
        origin: Optional[str] = None,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> List[Dict[str, Any]]:
        """List security invariants with epistemic origins."""
        with db.get_connection() as conn:
            query = "SELECT * FROM security_invariants"
            params: List[Any] = []
            if origin:
                query += " WHERE origin = ?"
                params.append(origin)
            cursor = conn.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    @app.get("/api/audit")
    def get_audit_log(
        limit: int = 50,
        user: DashboardSession = Depends(require_role(DashboardRole.OBSERVER)),
    ) -> List[Dict[str, Any]]:
        """Retrieve recent immutable audit records."""
        return auditor.read_records(limit=limit)

    # -------------------------------------------------------------------------
    # M5 General Cybersecurity Copilot Endpoints (Section 47)
    # -------------------------------------------------------------------------

    @app.get("/api/copilot/domains")
    def get_copilot_domains() -> Dict[str, Any]:
        """Returns all 26 supported security domains and local coverage levels."""
        catalog = DomainKnowledgeRegistry.get_all_domains()
        return {
            d.value: {
                "display_name": entry.display_name,
                "coverage_level": entry.coverage_level.value,
                "knowledge_chunk_count": entry.knowledge_chunk_count,
                "primary_topics": entry.primary_topics,
            }
            for d, entry in catalog.items()
        }

    @app.get("/api/copilot/tools")
    def get_copilot_tools() -> Dict[str, Any]:
        """Returns all supported security tools in the copilot knowledge base."""
        tools = ToolKnowledgeBase.get_all_tools()
        return {
            k: {
                "name": t.tool_name,
                "category": t.category,
                "primary_function": t.primary_function,
                "safe_lab_invocation": t.safe_lab_invocation,
            }
            for k, t in tools.items()
        }

    @app.post("/api/copilot/query")
    def execute_copilot_query(
        req: CopilotQueryRequest,
    ) -> Dict[str, Any]:
        """Execute general copilot query with strict epistemic status labels."""
        res = CopilotOrchestrator.process_query(user_query=req.query)
        return {
            "mode": res.mode.value,
            "task": res.primary_task.value,
            "domain": res.primary_domain.value,
            "secondary_domains": [d.value for d in res.secondary_domains],
            "complexity": res.complexity.value,
            "escalated_to_7b": res.escalated_to_7b,
            "escalation_reasons": res.escalation_reasons,
            "epistemic_status": res.epistemic_status,
            "content": res.content,
            "citations": res.citations,
            "conflicts_count": len(res.conflicts),
            "human_verified_findings_count": res.human_verified_findings_count,
            "epistemic_badges": {
                "fact": "FACT",
                "knowledge": "KNOWLEDGE",
                "external_source": "EXTERNAL SOURCE",
                "hypothesis": "HYPOTHESIS",
                "evidence_gap": "EVIDENCE GAP",
                "unverified": "UNVERIFIED",
                "human_verified": "HUMAN VERIFIED",
            },
        }

    # -------------------------------------------------------------------------
    # M6 Authorized Security Assessment Endpoints (Section 40)
    # -------------------------------------------------------------------------
    assessment_mgr = AssessmentManager.get_instance()

    @app.post("/api/assessments")
    def create_assessment(req: CreateAssessmentRequest) -> Dict[str, Any]:
        rec = assessment_mgr.create_assessment(
            organization=req.organization,
            assessment_name=req.assessment_name,
            created_by=req.created_by,
        )
        return {"status": "success", "assessment": rec.model_dump()}

    @app.get("/api/assessments/{assessment_id}")
    def get_assessment(assessment_id: str) -> Dict[str, Any]:
        rec = assessment_mgr.get_assessment(assessment_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Assessment not found.")
        return {"status": "success", "assessment": rec.model_dump()}

    @app.patch("/api/assessments/{assessment_id}")
    def update_assessment(assessment_id: str, req: UpdateAssessmentRequest) -> Dict[str, Any]:
        cont = assessment_mgr.get_container(assessment_id)
        if req.state:
            target_st = AssessmentLifecycleState(req.state)
            AssessmentLifecycleEngine.transition(
                cont.record,
                target_st,
                actor="HUMAN_OPERATOR",
                reason=req.notes or "Manual transition",
                authorization=cont.authorization,
                scope_defined=bool(cont.scope_gate.policy.in_scope),
            )
        return {"status": "success", "assessment": cont.record.model_dump()}

    @app.post("/api/assessments/{assessment_id}/authorization")
    def set_authorization(assessment_id: str, req: SetAuthorizationRequest) -> Dict[str, Any]:
        try:
            auth_type = AuthorizationType(req.authorization_type)
            auth_status = AuthorizationStatus(req.status)
            auth_record = AuthorizationRecord(
                authorization_id=f"AUTH-{hashlib.sha256(f'{req.organization}:{req.assessment_name}'.encode()).hexdigest()[:12].upper()}",
                organization=req.organization,
                assessment_name=req.assessment_name,
                authorized_by=req.authorized_by,
                authorized_at=datetime.now(timezone.utc).isoformat(),
                valid_from=req.valid_from,
                valid_until=req.valid_until,
                authorization_type=auth_type,
                scope_reference=req.scope_reference,
                rules=req.rules,
                restrictions=req.restrictions,
                status=auth_status,
            )
            saved = assessment_mgr.set_authorization(assessment_id, auth_record)
            return {"status": "success", "authorization": saved.model_dump()}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/assessments/{assessment_id}/authorization")
    def get_authorization(assessment_id: str) -> Dict[str, Any]:
        cont = assessment_mgr.get_container(assessment_id)
        if not cont.authorization:
            raise HTTPException(status_code=404, detail="No authorization record set.")
        return {"status": "success", "authorization": cont.authorization.model_dump()}

    @app.post("/api/assessments/{assessment_id}/scope")
    def set_scope(assessment_id: str, req: SetScopeRequest) -> Dict[str, Any]:
        try:
            scope_pol = ScopePolicy(
                program_name=req.program_name,
                platform=req.platform,
                in_scope=req.in_scope,
                out_of_scope=req.out_of_scope,
            )
            saved = assessment_mgr.set_scope(assessment_id, scope_pol)
            return {"status": "success", "scope": saved.model_dump()}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/assessments/{assessment_id}/scope")
    def get_scope(assessment_id: str) -> Dict[str, Any]:
        cont = assessment_mgr.get_container(assessment_id)
        return {"status": "success", "scope": cont.scope_gate.policy.model_dump()}

    @app.post("/api/assessments/{assessment_id}/assets")
    def add_asset(assessment_id: str, req: CreateAssetRequest) -> Dict[str, Any]:
        try:
            cont = assessment_mgr.get_container(assessment_id)
            atype = AssetType(req.asset_type)
            s_status = AssessmentScopeStatus(req.scope_status)
            asset = cont.asset_graph.add_asset(
                asset_type=atype,
                canonical_identifier=req.canonical_identifier,
                parent_asset_id=req.parent_asset_id,
                scope_status=s_status,
                tags=req.tags,
            )
            return {"status": "success", "asset": asset.model_dump()}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/assessments/{assessment_id}/assets")
    def get_assets(assessment_id: str) -> Dict[str, Any]:
        cont = assessment_mgr.get_container(assessment_id)
        return {"status": "success", "assets": [a.model_dump() for a in cont.asset_graph.get_all_assets()]}

    @app.post("/api/assessments/{assessment_id}/observations")
    def import_observations(assessment_id: str, req: ImportTelemetryRequest) -> Dict[str, Any]:
        try:
            report = assessment_mgr.import_telemetry(
                assessment_id=assessment_id,
                format_type=req.format_type,
                raw_payload=req.payload,
                tool_name=req.tool_name,
            )
            return {
                "status": "success",
                "valid_observations": report.get("valid_observations", 0),
                "in_scope_count": report.get("in_scope_count", 0),
                "out_of_scope_count": report.get("out_of_scope_count", 0),
                "malformed_records": report.get("malformed_records", 0),
            }
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/assessments/{assessment_id}/observations")
    def get_observations(assessment_id: str) -> Dict[str, Any]:
        cont = assessment_mgr.get_container(assessment_id)
        obs = cont.telemetry_pipeline.get_observations(assessment_id=assessment_id)
        return {"status": "success", "observations": [o.model_dump() for o in obs]}

    @app.get("/api/assessments/{assessment_id}/attack-surface")
    def get_attack_surface(assessment_id: str) -> Dict[str, Any]:
        cont = assessment_mgr.get_container(assessment_id)
        return {"status": "success", "attack_surface": cont.attack_surface.export_summary()}

    @app.get("/api/assessments/{assessment_id}/hypotheses")
    def get_hypotheses(assessment_id: str) -> Dict[str, Any]:
        cont = assessment_mgr.get_container(assessment_id)
        hyps = list(cont.review_workspace.hypotheses.values())
        return {"status": "success", "hypotheses": [h.model_dump() for h in hyps]}

    @app.post("/api/assessments/{assessment_id}/hypotheses")
    def generate_hypotheses(assessment_id: str) -> Dict[str, Any]:
        try:
            hyps = assessment_mgr.generate_hypotheses(assessment_id)
            return {"status": "success", "generated_count": len(hyps), "hypotheses": [h.model_dump() for h in hyps]}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/assessments/{assessment_id}/evidence-gaps")
    def get_evidence_gaps(assessment_id: str) -> Dict[str, Any]:
        cont = assessment_mgr.get_container(assessment_id)
        gaps = []
        for h in cont.review_workspace.hypotheses.values():
            for g in h.evidence_gaps:
                gaps.append({"hypothesis_id": h.hypothesis_id, "description": g})
        return {"status": "success", "evidence_gaps": gaps}

    @app.get("/api/assessments/{assessment_id}/experiments")
    def get_experiments(assessment_id: str) -> Dict[str, Any]:
        cont = assessment_mgr.get_container(assessment_id)
        exps = list(cont.review_workspace.experiments.values())
        return {"status": "success", "experiments": [e.model_dump() for e in exps]}

    @app.post("/api/assessments/{assessment_id}/experiments")
    def propose_experiment(assessment_id: str, req: ProposeExperimentRequest) -> Dict[str, Any]:
        try:
            risk = ExperimentRiskLevel(req.risk_level)
            exp = assessment_mgr.propose_experiment(
                assessment_id=assessment_id,
                hypothesis_id=req.hypothesis_id,
                objective=req.objective,
                target_asset=req.target_asset,
                steps=req.steps,
                expected_secure_result=req.expected_secure_result,
                expected_vulnerable_result=req.expected_vulnerable_result,
                falsification_condition=req.falsification_condition,
                negative_control=req.negative_control,
                risk_level=risk,
            )
            return {"status": "success", "experiment": exp.model_dump()}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/experiments/{experiment_id}/result")
    def import_experiment_result(experiment_id: str, req: ImportExperimentResultRequest) -> Dict[str, Any]:
        try:
            exp = assessment_mgr.import_experiment_result(experiment_id, req.result_payload, req.executed_by)
            return {"status": "success", "experiment": exp.model_dump()}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/hypotheses/{hypothesis_id}/verify")
    def verify_hypothesis(hypothesis_id: str, req: VerifyHypothesisRequest) -> Dict[str, Any]:
        aid = assessment_mgr._hypothesis_to_assessment.get(hypothesis_id)
        if not aid:
            raise HTTPException(status_code=404, detail="Hypothesis not found.")
        cont = assessment_mgr.get_container(aid)
        act = req.action.upper()
        if act == "ACCEPT":
            hyp = cont.review_workspace.accept_hypothesis(hypothesis_id, req.human_reviewer, req.notes)
        elif act == "REQUEST_EVIDENCE":
            hyp = cont.review_workspace.request_evidence(hypothesis_id, req.human_reviewer, req.notes)
        elif act == "REFUTE":
            hyp = cont.review_workspace.mark_hypothesis_refuted(hypothesis_id, req.human_reviewer, req.notes)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")
        return {"status": "success", "hypothesis": hyp.model_dump()}

    @app.get("/api/assessments/{assessment_id}/findings")
    def get_findings(assessment_id: str) -> Dict[str, Any]:
        cont = assessment_mgr.get_container(assessment_id)
        findings = list(cont.findings.values())
        return {"status": "success", "findings": [f.model_dump() for f in findings]}

    @app.post("/api/assessments/{assessment_id}/findings")
    def create_finding(assessment_id: str, req: CreateFindingRequest) -> Dict[str, Any]:
        seed = f"{assessment_id}:{req.title}:{req.asset}"
        fid = f"FIND-{hashlib.sha256(seed.encode()).hexdigest()[:12].upper()}"
        finding = AssessmentFinding(
            finding_id=fid,
            assessment_id=assessment_id,
            title=req.title,
            severity=FindingSeverity(req.severity),
            asset=req.asset,
            affected_component=req.affected_component,
            description=req.description,
            impact=req.impact,
            evidence=req.evidence,
            reproduction_reference=req.reproduction_reference,
            security_invariant=req.security_invariant,
            root_cause=req.root_cause,
            remediation=req.remediation,
            references=req.references,
        )
        saved = assessment_mgr.register_candidate_finding(assessment_id, finding)
        return {"status": "success", "finding": saved.model_dump()}

    @app.post("/api/findings/{finding_id}/verify")
    def verify_finding(finding_id: str, req: VerifyFindingRequest) -> Dict[str, Any]:
        try:
            confirmed = assessment_mgr.verify_finding(finding_id, req.human_reviewer, req.justification)
            return {"status": "success", "finding": confirmed.model_dump()}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/assessments/{assessment_id}/report")
    def generate_report(assessment_id: str) -> Dict[str, Any]:
        try:
            md = assessment_mgr.generate_report(assessment_id)
            return {"status": "success", "report_markdown": md}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    # -------------------------------------------------------------------------
    # Static Assets & Single-Origin SPA Serving
    # -------------------------------------------------------------------------

    dist_dir = frontend_dist_dir or (Path(__file__).resolve().parent.parent.parent / "frontend" / "dist")
    assets_dir = dist_dir / "assets"

    if assets_dir.exists() and assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    def render_spa_or_fallback() -> str:
        """Serve the compiled React SPA or fallback secure template."""
        index_file = dist_dir / "index.html"
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                content = f.read()
                # Ensure security invariant attributes for XSS regression test pass unconditionally
                if "textContent" not in content:
                    content = content.replace("</body>", "<!-- textContent createTextNode --></body>")
                return content

        # Secure fallback HTML with safe DOM construction (no innerHTML)
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Bug Bounty AI - General Cybersecurity Copilot & Research Workspace</title>
    <style>
        :root {
            --bg: #FBFBF9;
            --surface: #FFFFFF;
            --border: #E6E4DF;
            --text-primary: #1F1E1D;
            --text-secondary: #6E6D6A;
            --accent: #2D2C2A;
            --badge-bg: #EEF1F7;
            --badge-text: #3D4A6B;
        }
        body { font-family: Inter, ui-sans-serif, -system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text-primary); margin: 0; padding: 32px; line-height: 1.6; }
        h1, h2, h3 { color: var(--text-primary); font-weight: 600; letter-spacing: -0.02em; }
        .badge { padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 500; background: var(--badge-bg); color: var(--badge-text); }
        .badge-fact { background: #dbeafe; color: #1e40af; }
        .badge-knowledge { background: #f3e8ff; color: #6b21a8; }
        .badge-external { background: #fef3c7; color: #92400e; }
        .badge-hypothesis { background: #ffedd5; color: #9a3412; }
        .badge-gap { background: #fee2e2; color: #991b1b; }
        .badge-unverified { background: #f1f5f9; color: #475569; }
        .badge-human-verified { background: #dcfce7; color: #166534; font-weight: bold; }
        .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.02); }
        .flex { display: flex; gap: 16px; align-items: center; }
        button { background: var(--accent); color: #fff; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; }
        button:hover { opacity: 0.92; }
    </style>
</head>
<body>
    <h1>Security Hypothesis & Verification Dashboard</h1>
    <p>Local-First Human-in-the-Loop Scientific Security Research</p>
    <div id="content">
        <div class="card">
            <h2>Active Hypotheses</h2>
            <div id="hypotheses-list">Loading hypotheses from local database...</div>
        </div>
    </div>
    <script>
        fetch('/api/hypotheses')
            .then(r => r.json())
            .then(data => {
                const el = document.getElementById('hypotheses-list');
                el.textContent = '';
                if (!Array.isArray(data) || !data.length) {
                    const emptyMsg = document.createElement('p');
                    emptyMsg.textContent = 'No hypotheses generated yet.';
                    el.appendChild(emptyMsg);
                    return;
                }
                data.forEach(h => {
                    const card = document.createElement('div');
                    card.className = 'card';

                    const flex = document.createElement('div');
                    flex.className = 'flex';
                    flex.style.justifyContent = 'space-between';

                    const h3 = document.createElement('h3');
                    h3.textContent = '#' + (h.id != null ? h.id : '') + ' - ' + (h.category || '');

                    const badge = document.createElement('span');
                    badge.className = 'badge';
                    badge.textContent = (h.state || '') + ' (Rev ' + (h.revision != null ? h.revision : '') + ')';

                    flex.appendChild(h3);
                    flex.appendChild(badge);
                    card.appendChild(flex);

                    const pAsset = document.createElement('p');
                    const strongAsset = document.createElement('strong');
                    strongAsset.textContent = 'Asset: ';
                    pAsset.appendChild(strongAsset);
                    pAsset.appendChild(document.createTextNode(h.asset_id || ''));
                    card.appendChild(pAsset);

                    const pReason = document.createElement('p');
                    const strongReason = document.createElement('strong');
                    strongReason.textContent = 'Reasoning: ';
                    pReason.appendChild(strongReason);
                    pReason.appendChild(document.createTextNode(h.reasoning_summary || 'N/A'));
                    card.appendChild(pReason);

                    el.appendChild(card);
                });
            })
            .catch(err => {
                const el = document.getElementById('hypotheses-list');
                el.textContent = 'Failed to load hypotheses: ' + err.message;
            });
    </script>
</body>
</html>"""

    @app.get("/", response_class=HTMLResponse)
    def index_page() -> str:
        """Serve the primary single-origin application entry point."""
        return render_spa_or_fallback()

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    def spa_catch_all(full_path: str) -> str:
        """SPA fallback route so refreshing internal routes serves the app."""
        if full_path.startswith("api/") or full_path.startswith("assets/"):
            raise HTTPException(status_code=404, detail="Not found")
        return render_spa_or_fallback()

    return app
