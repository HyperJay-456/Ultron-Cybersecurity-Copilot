"""SQLite persistence manager for M11.5 Long Response Subsystem.
Stores response sessions, granular chunk lineage, provenance hashes, and version histories.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
from src.core.logging import get_logger
from src.evidence.vault import RedactionVault
from src.database.manager import DatabaseManager
from src.response.models import (
    GenerationTermination,
    ResponseChunk,
    ResponseSession,
    ResponseStatus,
    ResponseVersion,
)
from src.response.errors import PersistenceError

logger = get_logger("ResponsePersistence")


class ResponsePersistence:
    """
    Manages transactional storage and retrieval of response sessions,
    chunks, and historical versions in SQLite.
    """

    DDL_SCHEMA = """
    CREATE TABLE IF NOT EXISTS response_sessions (
        response_id         TEXT PRIMARY KEY,
        investigation_id    TEXT NOT NULL,
        parent_message_id   TEXT,
        model               TEXT NOT NULL,
        cumulative_tokens   INTEGER DEFAULT 0,
        status              TEXT NOT NULL,
        termination_reason  TEXT,
        final_content       TEXT NOT NULL,
        started_at          TEXT NOT NULL,
        completed_at        TEXT,
        active_version      INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS response_chunks (
        chunk_id            TEXT PRIMARY KEY,
        response_id         TEXT NOT NULL REFERENCES response_sessions(response_id) ON DELETE CASCADE,
        sequence_number     INTEGER NOT NULL,
        content             TEXT NOT NULL,
        raw_content         TEXT NOT NULL,
        content_hash        TEXT NOT NULL,
        token_count         INTEGER DEFAULT 0,
        generation_time     REAL DEFAULT 0.0,
        stop_reason         TEXT NOT NULL,
        created_at          TEXT NOT NULL,
        UNIQUE(response_id, sequence_number)
    );

    CREATE TABLE IF NOT EXISTS response_versions (
        version_id          TEXT PRIMARY KEY,
        response_id         TEXT NOT NULL REFERENCES response_sessions(response_id) ON DELETE CASCADE,
        version_number      INTEGER NOT NULL,
        content             TEXT NOT NULL,
        model               TEXT NOT NULL,
        status              TEXT NOT NULL,
        created_at          TEXT NOT NULL,
        UNIQUE(response_id, version_number)
    );

    CREATE INDEX IF NOT EXISTS idx_response_sessions_inv ON response_sessions(investigation_id);
    CREATE INDEX IF NOT EXISTS idx_response_chunks_session ON response_chunks(response_id, sequence_number);
    CREATE INDEX IF NOT EXISTS idx_response_versions_session ON response_versions(response_id, version_number);
    """

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager
        self.vault = RedactionVault()
        self._initialize_tables()

    def _initialize_tables(self) -> None:
        """Create tables idempotently."""
        with self.db.get_connection() as conn:
            conn.executescript(self.DDL_SCHEMA)
            conn.commit()

    def create_session(self, session: ResponseSession) -> None:
        """Insert new response session."""
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO response_sessions (
                    response_id, investigation_id, parent_message_id, model,
                    cumulative_tokens, status, termination_reason, final_content,
                    started_at, completed_at, active_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.response_id,
                    session.investigation_id,
                    session.parent_message_id,
                    session.model,
                    session.cumulative_tokens,
                    session.status.value,
                    session.termination_reason.value if session.termination_reason else None,
                    self.vault.redact_text(session.final_content),
                    session.started_at,
                    session.completed_at,
                    session.active_version,
                ),
            )
            conn.commit()

    def update_session(
        self,
        response_id: str,
        status: ResponseStatus,
        final_content: str,
        cumulative_tokens: int,
        termination_reason: Optional[GenerationTermination] = None,
        completed_at: Optional[str] = None,
    ) -> None:
        """Update session state upon chunk arrival or completion."""
        with self.db.get_connection() as conn:
            conn.execute(
                """
                UPDATE response_sessions
                SET status = ?,
                    final_content = ?,
                    cumulative_tokens = ?,
                    termination_reason = ?,
                    completed_at = COALESCE(?, completed_at)
                WHERE response_id = ?
                """,
                (
                    status.value,
                    self.vault.redact_text(final_content),
                    cumulative_tokens,
                    termination_reason.value if termination_reason else None,
                    completed_at,
                    response_id,
                ),
            )
            conn.commit()

    def save_chunk(self, response_id: str, chunk: ResponseChunk) -> None:
        """Insert or replace an individual response chunk with cryptographic hash."""
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO response_chunks (
                    chunk_id, response_id, sequence_number, content,
                    raw_content, content_hash, token_count, generation_time,
                    stop_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.chunk_id,
                    response_id,
                    chunk.sequence_number,
                    self.vault.redact_text(chunk.content),
                    self.vault.redact_text(chunk.raw_content),
                    chunk.content_hash,
                    chunk.token_count,
                    chunk.generation_time,
                    chunk.stop_reason,
                    chunk.created_at,
                ),
            )
            conn.commit()

    def save_version(self, version: ResponseVersion) -> None:
        """Persist a discrete generation version for an answer."""
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO response_versions (
                    version_id, response_id, version_number, content,
                    model, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version.version_id,
                    version.response_id,
                    version.version_number,
                    self.vault.redact_text(version.content),
                    version.model,
                    version.status.value,
                    version.created_at,
                ),
            )
            conn.commit()

    def get_session(self, response_id: str) -> Optional[ResponseSession]:
        """Load session and associated chunks by response ID."""
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM response_sessions WHERE response_id = ?", (response_id,)).fetchone()
            if not row:
                return None
            session_dict = dict(row)

            # Fetch chunks
            chunk_rows = conn.execute(
                "SELECT * FROM response_chunks WHERE response_id = ? ORDER BY sequence_number ASC",
                (response_id,),
            ).fetchall()
            chunks = [ResponseChunk(**dict(r)) for r in chunk_rows]

            term_reason = (
                GenerationTermination(session_dict["termination_reason"])
                if session_dict.get("termination_reason")
                else None
            )

            return ResponseSession(
                response_id=session_dict["response_id"],
                investigation_id=session_dict["investigation_id"],
                parent_message_id=session_dict.get("parent_message_id"),
                model=session_dict["model"],
                chunks=chunks,
                cumulative_tokens=session_dict["cumulative_tokens"],
                status=ResponseStatus(session_dict["status"]),
                termination_reason=term_reason,
                final_content=session_dict["final_content"],
                started_at=session_dict["started_at"],
                completed_at=session_dict.get("completed_at"),
                active_version=session_dict.get("active_version", 1),
            )

    def get_chunks(self, response_id: str) -> List[ResponseChunk]:
        """Fetch all chunks for a response session."""
        with self.db.get_connection() as conn:
            chunk_rows = conn.execute(
                "SELECT * FROM response_chunks WHERE response_id = ? ORDER BY sequence_number ASC",
                (response_id,),
            ).fetchall()
            return [ResponseChunk(**dict(r)) for r in chunk_rows]

    def get_versions(self, response_id: str) -> List[ResponseVersion]:
        """Fetch all historical versions for a response session."""
        with self.db.get_connection() as conn:
            v_rows = conn.execute(
                "SELECT * FROM response_versions WHERE response_id = ? ORDER BY version_number ASC",
                (response_id,),
            ).fetchall()
            return [ResponseVersion(**dict(r)) for r in v_rows]
