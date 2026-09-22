"""Structured logging and tamper-evident chained audit logging for the Bug Bounty Research Platform."""

import hashlib
import json
import logging
from pathlib import Path
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

GENESIS_PREVIOUS_HASH = "0" * 64


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


class AuditLogVerificationResult(BaseModel):
    """Result of independent verification of the chained audit log."""
    valid: bool
    total_records: int
    tampered_records: List[int] = Field(default_factory=list)
    tampering_types: List[str] = Field(default_factory=list)
    error_messages: List[str] = Field(default_factory=list)


class AuditLogger:
    """
    Append-only tamper-evident chained audit logger recording every state transition,
    scope decision, tool invocation, and human verification decision.

    Integrity Model:
    Each record binds:
    - sequence_number (strictly monotonically increasing)
    - previous_record_hash (cryptographic hash chain back to genesis)
    - timestamp, actor, event_type, subject_id, states, evidence_ref
    - canonical payload_hash
    - canonical record_hash covering ALL top-level security fields

    Detects:
    - In-place modifications
    - Record deletions
    - Record insertions / replays
    - Record reorderings
    - Record replacements
    """

    def __init__(self, audit_file_path: Path) -> None:
        self.audit_file_path = Path(audit_file_path)
        self.audit_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

        # Initialize chain state under lock
        with self._lock:
            self._current_sequence = 0
            self._last_record_hash = GENESIS_PREVIOUS_HASH
            self._initialize_chain_state()

    def _initialize_chain_state(self) -> None:
        """Scan existing records to resume sequence and hash chain."""
        if not self.audit_file_path.exists():
            return

        last_seq = 0
        last_hash = GENESIS_PREVIOUS_HASH
        try:
            with open(self.audit_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        if "sequence_number" in rec and "record_hash" in rec:
                            last_seq = rec["sequence_number"]
                            last_hash = rec["record_hash"]
                    except Exception:
                        continue
        except Exception:
            pass

        self._current_sequence = last_seq
        self._last_record_hash = last_hash

    @staticmethod
    def compute_canonical_hash(data: Dict[str, Any]) -> str:
        """Compute SHA256 digest over canonical JSON representation."""
        serialized = json.dumps(data, sort_keys=True, default=str)
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
        Record a chained, tamper-evident audit record to the JSONL log file.
        """
        now = datetime.now(timezone.utc).isoformat()
        payload = details or {}
        payload_hash = self.compute_canonical_hash(payload)

        with self._lock:
            sequence_number = self._current_sequence + 1
            previous_record_hash = self._last_record_hash

            # Body containing all security-relevant fields to be hashed
            record_body: Dict[str, Any] = {
                "sequence_number": sequence_number,
                "previous_record_hash": previous_record_hash,
                "timestamp": now,
                "event_type": event_type,
                "actor": actor,
                "subject_id": subject_id,
                "previous_state": previous_state,
                "new_state": new_state,
                "evidence_ref": evidence_ref,
                "payload_hash": payload_hash,
            }

            # Canonical record hash covering all security-relevant metadata
            record_hash = self.compute_canonical_hash(record_body)

            # Complete record written to disk
            record: Dict[str, Any] = {
                **record_body,
                "record_hash": record_hash,
                "details": payload,
            }

            line = json.dumps(record, sort_keys=True, default=str) + "\n"
            with open(self.audit_file_path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()

            self._current_sequence = sequence_number
            self._last_record_hash = record_hash

        return record

    def read_records(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Read audit records from the log file in chronological order."""
        records: List[Dict[str, Any]] = []
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


def verify_audit_log(audit_file_path: Path) -> AuditLogVerificationResult:
    """
    Independently verifies the integrity and cryptographic hash chain of an audit log.
    Detects record modification, deletion, insertion, reordering, and replacement.
    """
    if not audit_file_path.exists():
        return AuditLogVerificationResult(
            valid=True,
            total_records=0,
            tampered_records=[],
            tampering_types=[],
            error_messages=["Audit file does not exist (empty log)."],
        )

    expected_prev_hash = GENESIS_PREVIOUS_HASH
    expected_seq = 1
    tampered_records: List[int] = []
    tampering_types: List[str] = []
    errors: List[str] = []
    total_records = 0

    with open(audit_file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            total_records += 1

            try:
                rec = json.loads(line)
            except Exception as e:
                tampered_records.append(line_num)
                tampering_types.append("MALFORMED_JSON")
                errors.append(f"Line {line_num}: Malformed JSON: {e}")
                continue

            seq = rec.get("sequence_number")
            prev_hash = rec.get("previous_record_hash")
            rec_hash = rec.get("record_hash")
            payload_hash = rec.get("payload_hash")
            details = rec.get("details", {})

            # 1. Check sequence monotonicity
            if seq != expected_seq:
                tampered_records.append(line_num)
                if seq is not None and seq > expected_seq:
                    tampering_types.append("DELETION")
                    errors.append(f"Line {line_num}: Sequence gap detected (expected {expected_seq}, got {seq}): record deleted")
                else:
                    tampering_types.append("REORDERING_OR_INSERTION")
                    errors.append(f"Line {line_num}: Sequence mismatch (expected {expected_seq}, got {seq})")

            # 2. Check hash chain continuity
            if prev_hash != expected_prev_hash:
                tampered_records.append(line_num)
                tampering_types.append("CHAIN_BROKEN_OR_REPLACED")
                errors.append(
                    f"Line {line_num}: Hash chain broken (expected prev {expected_prev_hash[:12]}..., got {str(prev_hash)[:12]}...)"
                )

            # 3. Check payload hash integrity
            computed_payload_hash = AuditLogger.compute_canonical_hash(details)
            if payload_hash != computed_payload_hash:
                tampered_records.append(line_num)
                tampering_types.append("MODIFICATION")
                errors.append(f"Line {line_num}: Details payload hash mismatch")

            # 4. Recompute canonical record hash
            record_body: Dict[str, Any] = {
                "sequence_number": seq,
                "previous_record_hash": prev_hash,
                "timestamp": rec.get("timestamp"),
                "event_type": rec.get("event_type"),
                "actor": rec.get("actor"),
                "subject_id": rec.get("subject_id"),
                "previous_state": rec.get("previous_state"),
                "new_state": rec.get("new_state"),
                "evidence_ref": rec.get("evidence_ref"),
                "payload_hash": payload_hash,
            }
            computed_record_hash = AuditLogger.compute_canonical_hash(record_body)
            if rec_hash != computed_record_hash:
                tampered_records.append(line_num)
                tampering_types.append("MODIFICATION")
                errors.append(f"Line {line_num}: Canonical record hash mismatch (tampered content)")

            # Advance expected chain state
            expected_seq = (seq + 1) if seq is not None else (expected_seq + 1)
            expected_prev_hash = rec_hash if rec_hash else "INVALID_PREV"

    valid = len(tampered_records) == 0
    return AuditLogVerificationResult(
        valid=valid,
        total_records=total_records,
        tampered_records=list(set(tampered_records)),
        tampering_types=list(set(tampering_types)),
        error_messages=errors,
    )
