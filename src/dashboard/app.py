"""Local Human Feedback Dashboard API and UI."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from src.core.logging import AuditLogger, get_logger
from src.database.manager import DatabaseManager
from src.hypothesis.state_machine import HypothesisStateMachine, HypothesisState

DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8000

logger = get_logger("Dashboard")


def validate_dashboard_bind(host: str = DEFAULT_DASHBOARD_HOST, allow_external: bool = False) -> str:
    """
    Validate bind address to enforce localhost loopback isolation by default.
    Raises ValueError if a non-loopback interface is requested without allow_external=True.
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
                "The dashboard has no authentication mechanism and relies strictly on loopback isolation. "
                "Set allow_external=True to explicitly override."
            )
        logger.warning(
            f"CRITICAL SECURITY WARNING: Dashboard binding to non-loopback address '{host}' with allow_external=True. "
            "Anyone on the local network can access hypotheses and trigger state transitions without authentication."
        )
    return host


class VerificationRequest(BaseModel):
    actor: str = Field(description="Researcher identifier")
    evidence_ref: str = Field(min_length=5, description="Path or reference to repro evidence / traffic log")
    dashboard_session_id: str = Field(
        default="DASH-SESSION-001",
        description="Client-submitted audit tracking identifier; NOT an authentication or session credential. Access security relies strictly on localhost loopback binding.",
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
) -> FastAPI:
    """Factory creating the FastAPI human review dashboard app."""
    app = FastAPI(
        title="Local AI-Assisted Bug Bounty Research Platform - Human Feedback Dashboard",
        version="0.6.0",
    )
    db = db_manager or DatabaseManager()
    auditor = audit_logger or AuditLogger(Path("data/audit.log"))
    state_machine = HypothesisStateMachine(db)

    @app.get("/api/hypotheses")
    def list_hypotheses(state: Optional[str] = None) -> List[Dict[str, Any]]:
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
    def get_hypothesis_detail(hypothesis_id: int) -> Dict[str, Any]:
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
    def start_hypothesis_review(hypothesis_id: int) -> Dict[str, Any]:
        """Move hypothesis from New to Under Review."""
        try:
            state_machine.start_review(hypothesis_id)
            auditor.log_event(
                event_type="STATE_TRANSITION",
                actor="researcher",
                subject_id=str(hypothesis_id),
                previous_state="New",
                new_state="Under Review",
            )
            return {"status": "success", "state": "Under Review"}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/hypotheses/{hypothesis_id}/experiment/result")
    def submit_experiment_result(hypothesis_id: int, req: ExperimentResultRequest) -> Dict[str, Any]:
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
                actor="researcher",
                subject_id=str(hypothesis_id),
                new_state=revised.get("state"),
                evidence_ref=req.new_evidence_ref,
                details={"observation_type": req.observation_type, "notes": req.notes},
            )
            return {"status": "success", "hypothesis": revised}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/hypotheses/{hypothesis_id}/confirm")
    def confirm_hypothesis(hypothesis_id: int, req: VerificationRequest) -> Dict[str, Any]:
        """Confirm hypothesis with human verification."""
        hyp_detail = get_hypothesis_detail(hypothesis_id)
        if hyp_detail["safety"]["requires_safety_acknowledgment"] and not req.safety_acknowledged:
            raise HTTPException(
                status_code=400,
                detail="Safety acknowledgment required for STATE_CHANGING or DESTRUCTIVE endpoints before confirmation.",
            )

        try:
            state_machine.confirm_with_human_verification(
                hypothesis_id=hypothesis_id,
                actor=req.actor,
                evidence_ref=req.evidence_ref,
                session_id=req.dashboard_session_id,
                notes=req.notes,
            )
            auditor.log_event(
                event_type="HUMAN_VERIFICATION",
                actor=req.actor,
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
    def list_invariants(origin: Optional[str] = None) -> List[Dict[str, Any]]:
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
    def get_audit_log(limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent immutable audit records."""
        return auditor.read_records(limit=limit)

    @app.get("/", response_class=HTMLResponse)
    def index_page() -> str:
        """Render local verification dashboard interface."""
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
        h1, h2 { color: #fff; }
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
                if (!data.length) { el.innerHTML = '<p>No hypotheses generated yet.</p>'; return; }
                el.innerHTML = data.map(h => `
                    <div class="card">
                        <div class="flex" style="justify-content: space-between;">
                            <h3>#${h.id} - ${h.category}</h3>
                            <span class="badge ${h.state === 'Confirmed' ? 'badge-obs' : 'badge-model'}">${h.state} (Rev ${h.revision})</span>
                        </div>
                        <p><strong>Asset:</strong> ${h.asset_id}</p>
                        <p><strong>Reasoning:</strong> ${h.reasoning_summary || 'N/A'}</p>
                    </div>
                `).join('');
            });
    </script>
</body>
</html>"""

    return app
