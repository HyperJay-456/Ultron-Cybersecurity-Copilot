"""Local Human Feedback Dashboard API and UI."""

from enum import Enum
import json
from pathlib import Path
import secrets
import time
from typing import Any, Dict, List, Optional
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.core.logging import AuditLogger, get_logger
from src.database.manager import DatabaseManager
from src.hypothesis.state_machine import HypothesisStateMachine, HypothesisState

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


def create_dashboard_app(
    db_manager: Optional[DatabaseManager] = None,
    audit_logger: Optional[AuditLogger] = None,
    auth_manager: Optional[DashboardAuthManager] = None,
    require_auth: bool = False,
) -> FastAPI:
    """Factory creating the FastAPI human review dashboard app with RBAC and secure rendering."""
    app = FastAPI(
        title="Local AI-Assisted Bug Bounty Research Platform - Human Feedback Dashboard",
        version="0.6.0",
    )
    db = db_manager or DatabaseManager()
    auditor = audit_logger or AuditLogger(Path("data/audit.log"))
    state_machine = HypothesisStateMachine(db)
    auth_mgr = auth_manager or DashboardAuthManager()

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

        # Determine safety requirements
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

        # Authoritatively bind the verifying actor to the authenticated user
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

    @app.get("/", response_class=HTMLResponse)
    def index_page() -> str:
        """Render local verification dashboard interface with safe DOM construction (no innerHTML)."""
        return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Bug Bounty Research Platform - Dashboard</title>
    <style>
        :root {
            --bg: #0d1117;
            --surface: #161b22;
            --border: #30363d;
            --text: #c9d1d9;
            --accent: #58a6ff;
            --warn: #d29922;
            --danger: #f85149;
            --success: #3fb950;
        }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 24px; }
        h1, h2, h3 { color: #fff; }
        .badge { padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
        .badge-model { background: #6e40c9; color: #fff; }
        .badge-obs { background: #238636; color: #fff; }
        .badge-warn { background: #9e6a03; color: #fff; }
        .card { background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 16px; margin-bottom: 16px; }
        .flex { display: flex; gap: 16px; }
        button { background: var(--accent); color: #0d1117; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: bold; }
        button:hover { opacity: 0.9; }
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
                    badge.className = 'badge ' + (h.state === 'Confirmed' ? 'badge-obs' : 'badge-model');
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

    return app
