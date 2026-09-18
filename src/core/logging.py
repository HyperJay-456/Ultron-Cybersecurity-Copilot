"""Structured logging and immutable audit logging for the Bug Bounty Research Platform."""

import hashlib
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Obtain a structured console and file logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        ch = logging.StreamHandler()
        ch.setLevel(getattr(logging, level.upper(), logging.INFO))
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "logger": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}'
        )
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    return logger


class AuditLogger:
    """
    Append-only immutable audit logger recording every state transition,
    scope decision, tool invocation, and human verification decision.
    """

    def __init__(self, audit_file_path: Path) -> None:
        self.audit_file_path = Path(audit_file_path)
        self.audit_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _compute_payload_hash(self, payload: Dict[str, Any]) -> str:
        """Compute SHA256 digest of payload for tamper-evident auditing."""
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def log_event(
        self,
        event_type: str,
        actor: str,
        subject_id: str,
        previous_state: Optional[str] = None,
        new_state: Optional[str] = None,
        evidence_ref: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Record an immutable audit record to the JSONL log file.
        """
        now = datetime.now(timezone.utc).isoformat()
        payload = details or {}
        payload_hash = self._compute_payload_hash(payload)

        record: Dict[str, Any] = {
            "timestamp": now,
            "event_type": event_type,
            "actor": actor,
            "subject_id": subject_id,
            "previous_state": previous_state,
            "new_state": new_state,
            "evidence_ref": evidence_ref,
            "payload_hash": payload_hash,
            "details": payload,
        }

        line = json.dumps(record, sort_keys=True, default=str) + "\n"
        with self._lock:
            with open(self.audit_file_path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()

        return record

    def read_records(self, limit: Optional[int] = None) -> list[Dict[str, Any]]:
        """Read audit records from the log file in chronological order."""
        records: list[Dict[str, Any]] = []
        if not self.audit_file_path.exists():
            return records

        with self._lock:
            with open(self.audit_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        if limit:
            return records[-limit:]
        return records
