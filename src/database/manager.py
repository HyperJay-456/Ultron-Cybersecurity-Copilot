"""SQLite database manager for unified evidence.db."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional
from src.core.config import DatabaseConfig


class DatabaseManager:
    """
    Manages SQLite connections, schema initialization, and transactional
    integrity for the unified evidence.db database.
    """

    def __init__(self, config: Optional[DatabaseConfig] = None, db_path: Optional[Path] = None) -> None:
        if db_path:
            self.db_path = Path(db_path)
            self.timeout = 30.0
            self.enable_foreign_keys = True
            self.enable_wal = True
        elif config:
            self.db_path = Path(config.db_path)
            self.timeout = config.timeout_seconds
            self.enable_foreign_keys = config.enable_foreign_keys
            self.enable_wal = config.enable_wal_mode
        else:
            self.db_path = Path("data/evidence.db")
            self.timeout = 30.0
            self.enable_foreign_keys = True
            self.enable_wal = True

        if self.db_path != Path(":memory:"):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a contextual connection with foreign keys and Row factory enabled."""
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=self.timeout,
        )
        conn.row_factory = sqlite3.Row
        if self.enable_foreign_keys:
            conn.execute("PRAGMA foreign_keys = ON;")
        if self.enable_wal and self.db_path != Path(":memory:"):
            conn.execute("PRAGMA journal_mode = WAL;")
        try:
            yield conn
        finally:
            conn.close()

    def initialize_schema(self, schema_file: Optional[Path] = None) -> None:
        """Execute the DDL schema to initialize or migrate the database."""
        target_file = schema_file or (Path(__file__).parent / "schema.sql")
        with open(target_file, "r", encoding="utf-8") as f:
            ddl = f.read()

        with self.get_connection() as conn:
            conn.executescript(ddl)
            # Setup FTS5 for evidence items keyword search
            conn.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(
                    fact_id UNINDEXED,
                    statement,
                    source_tool UNINDEXED,
                    content='evidence_items',
                    content_rowid='rowid'
                );

                CREATE TRIGGER IF NOT EXISTS trg_evidence_ai AFTER INSERT ON evidence_items BEGIN
                    INSERT INTO evidence_fts(rowid, fact_id, statement, source_tool)
                    VALUES (new.rowid, new.fact_id, new.statement, new.source_tool);
                END;

                CREATE TRIGGER IF NOT EXISTS trg_evidence_ad AFTER DELETE ON evidence_items BEGIN
                    INSERT INTO evidence_fts(evidence_fts, rowid, fact_id, statement, source_tool)
                    VALUES('delete', old.rowid, old.fact_id, old.statement, old.source_tool);
                END;
            """)
            conn.commit()

    # Scope Decision Operations
    def insert_scope_decision(self, decision: Dict[str, Any]) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scope_decisions (
                    scope_decision_id, decision, requested_url, canonical_host,
                    resolved_addresses, matched_rule, out_of_scope_rule, tool_policy,
                    reason, scope_policy_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision["scope_decision_id"],
                    decision["decision"],
                    decision["requested_url"],
                    decision["canonical_host"],
                    json.dumps(decision["resolved_addresses"]) if isinstance(decision["resolved_addresses"], list) else decision["resolved_addresses"],
                    decision.get("matched_rule"),
                    decision.get("out_of_scope_rule"),
                    decision["tool_policy"],
                    decision.get("reason"),
                    decision["scope_policy_version"],
                ),
            )
            conn.commit()

    def get_scope_decision(self, scope_decision_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM scope_decisions WHERE scope_decision_id = ?", (scope_decision_id,))
            row = cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            if data.get("resolved_addresses"):
                try:
                    data["resolved_addresses"] = json.loads(data["resolved_addresses"])
                except Exception:
                    pass
            return data

    # Asset Operations
    def insert_asset(self, asset: Dict[str, Any]) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO assets (
                    asset_id, method, host, raw_path, normalized_path,
                    normalization_confidence, http_semantics, application_mutability,
                    liveness, scope_decision_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    last_checked_at = CURRENT_TIMESTAMP,
                    liveness = excluded.liveness,
                    application_mutability = CASE WHEN excluded.application_mutability != 'UNKNOWN' THEN excluded.application_mutability ELSE assets.application_mutability END
                """,
                (
                    asset["asset_id"],
                    asset["method"],
                    asset["host"],
                    asset["raw_path"],
                    asset["normalized_path"],
                    asset.get("normalization_confidence", 1.0),
                    asset.get("http_semantics", asset["method"]),
                    asset.get("application_mutability", "UNKNOWN"),
                    asset.get("liveness", "SHADOW_ACTIVE"),
                    asset.get("scope_decision_id"),
                ),
            )
            conn.commit()

    def update_asset_state(self, asset_id: str, field: str, new_value: str) -> None:
        """Update an asset state field and atomically record in asset_state_history."""
        if field not in ("liveness", "application_mutability"):
            raise ValueError(f"Invalid asset history field: {field}")

        _SELECT_QUERIES = {
            "liveness": "SELECT liveness FROM assets WHERE asset_id = ?",
            "application_mutability": "SELECT application_mutability FROM assets WHERE asset_id = ?",
        }
        _UPDATE_QUERIES = {
            "liveness": "UPDATE assets SET liveness = ?, last_checked_at = CURRENT_TIMESTAMP WHERE asset_id = ?",
            "application_mutability": "UPDATE assets SET application_mutability = ?, last_checked_at = CURRENT_TIMESTAMP WHERE asset_id = ?",
        }

        with self.get_connection() as conn:
            cursor = conn.execute(_SELECT_QUERIES[field], (asset_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Asset not found: {asset_id}")
            old_value = row[0]

            if old_value != new_value:
                conn.execute(_UPDATE_QUERIES[field], (new_value, asset_id))
                conn.execute(
                    "INSERT INTO asset_state_history (asset_id, field, old_value, new_value) VALUES (?, ?, ?, ?)",
                    (asset_id, field, old_value, new_value),
                )
                conn.commit()

    def get_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # Parameter Operations
    def insert_parameter(self, param: Dict[str, Any]) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO parameters (
                    param_id, asset_id, param_name, location, content_type,
                    param_type, is_server_volatile
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id, param_name, location) DO UPDATE SET
                    content_type = excluded.content_type,
                    param_type = excluded.param_type,
                    is_server_volatile = excluded.is_server_volatile
                """,
                (
                    param["param_id"],
                    param["asset_id"],
                    param["param_name"],
                    param["location"],
                    param.get("content_type"),
                    param.get("param_type"),
                    1 if param.get("is_server_volatile") else 0,
                ),
            )
            conn.commit()

    def get_parameters_for_asset(self, asset_id: str) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM parameters WHERE asset_id = ?", (asset_id,))
            return [dict(r) for r in cursor.fetchall()]

    # Identity Operations
    def insert_identity(self, identity: Dict[str, Any]) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO identities (identity_id, role, session_ref, notes)
                VALUES (?, ?, ?, ?)
                """,
                (
                    identity["identity_id"],
                    identity.get("role"),
                    identity.get("session_ref"),
                    identity.get("notes"),
                ),
            )
            conn.commit()

    def get_identity(self, identity_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM identities WHERE identity_id = ?", (identity_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # Evidence Item Operations
    def insert_evidence_item(self, item: Dict[str, Any]) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evidence_items (
                    fact_id, certainty, statement, source_tool, source_version,
                    trust, raw_evidence_ref, scope_decision_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["fact_id"],
                    item["certainty"],
                    item["statement"],
                    item["source_tool"],
                    item.get("source_version"),
                    item.get("trust", "UNTRUSTED"),
                    item.get("raw_evidence_ref"),
                    item.get("scope_decision_id"),
                ),
            )
            conn.commit()

    def get_evidence_item(self, fact_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM evidence_items WHERE fact_id = ?", (fact_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def query_fts(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Run BM25 keyword query against evidence_fts."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT f.fact_id, f.statement, f.source_tool, bm25(evidence_fts) as rank
                FROM evidence_fts f
                WHERE evidence_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            )
            return [dict(r) for r in cursor.fetchall()]

    # Security Invariants
    def insert_security_invariant(self, invariant: Dict[str, Any]) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO security_invariants (
                    invariant_id, description, origin, derived_from, confidence
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    invariant["invariant_id"],
                    invariant["description"],
                    invariant["origin"],
                    json.dumps(invariant.get("derived_from", [])),
                    invariant.get("confidence", "MEDIUM"),
                ),
            )
            conn.commit()

    def get_security_invariant(self, invariant_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM security_invariants WHERE invariant_id = ?", (invariant_id,))
            row = cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            if data.get("derived_from"):
                try:
                    data["derived_from"] = json.loads(data["derived_from"])
                except Exception:
                    pass
            return data

    # Hypotheses Operations
    def insert_hypothesis(self, hypothesis: Dict[str, Any]) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO hypotheses (
                    asset_id, category, decision, evidence_state, actor_identity_id,
                    target_identity_id, reasoning_summary, missing_evidence,
                    experiment_proposal, state, evidence_ref, revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hypothesis["asset_id"],
                    hypothesis["category"],
                    hypothesis["decision"],
                    hypothesis["evidence_state"],
                    hypothesis.get("actor_identity_id"),
                    hypothesis.get("target_identity_id"),
                    hypothesis.get("reasoning_summary"),
                    json.dumps(hypothesis.get("missing_evidence", [])),
                    json.dumps(hypothesis["experiment_proposal"]) if isinstance(hypothesis.get("experiment_proposal"), dict) else hypothesis.get("experiment_proposal"),
                    hypothesis.get("state", "New"),
                    hypothesis.get("evidence_ref"),
                    hypothesis.get("revision", 1),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def get_hypothesis(self, hypothesis_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM hypotheses WHERE id = ?", (hypothesis_id,))
            row = cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            if data.get("missing_evidence"):
                try:
                    data["missing_evidence"] = json.loads(data["missing_evidence"])
                except Exception:
                    pass
            return data

    def update_hypothesis_state(self, hypothesis_id: int, new_state: str, evidence_ref: Optional[str] = None) -> None:
        """Update hypothesis state. Hard triggers enforce evidence and verification records."""
        with self.get_connection() as conn:
            if evidence_ref:
                conn.execute(
                    "UPDATE hypotheses SET state = ?, evidence_ref = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (new_state, evidence_ref, hypothesis_id),
                )
            else:
                conn.execute(
                    "UPDATE hypotheses SET state = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (new_state, hypothesis_id),
                )
            conn.commit()

    # Verification Operations
    def record_verification(self, verification: Dict[str, Any]) -> None:
        """Record human verification decision in verifications table."""
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO verifications (
                    verification_id, hypothesis_id, actor, decision, evidence_ref,
                    dashboard_session_id, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    verification["verification_id"],
                    verification["hypothesis_id"],
                    verification["actor"],
                    verification["decision"],
                    verification["evidence_ref"],
                    verification["dashboard_session_id"],
                    verification.get("notes"),
                ),
            )
            conn.commit()
