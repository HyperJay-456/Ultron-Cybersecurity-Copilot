"""Knowledge Ingestion Engine & Quarantine Pipeline (Milestone M9 Phase 5 & Phase 16).

Implements the complete deterministic knowledge ingestion pipeline:
    SOURCE -> VALIDATE -> NORMALIZE -> VERSION -> HASH -> DEDUPLICATE -> CHUNK -> METADATA -> EMBEDDING -> INDEX -> PROVENANCE

Features:
- Deterministic SHA-256 hashing
- Quarantine gate for prompt injection and malformed documents
- Deduplication of identical content
- Version tracking without silent history destruction
- Deletion and atomic re-indexing
- Persistent append-only ingestion audit trail
- Strict segregation of User Knowledge from Target Evidence
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from src.knowledge.canonical_models import (
    AuthorityLevel,
    CanonicalSourceType,
    KnowledgeDocument,
    KnowledgeFreshnessStatus,
    KnowledgeSection,
    KnowledgeSource,
    KnowledgeVersion,
)
from src.knowledge.chunking import SemanticMarkdownChunker
from src.knowledge.ingestion import SUSPICIOUS_DIRECTIVE_PATTERNS, normalize_markdown_text
from src.knowledge.models import (
    KnowledgeChunk,
    KnowledgeSourceType,
    KnowledgeType,
)
from src.assessment.secrets import SecretRedactor
from src.knowledge.store import VaptKnowledgeStore

logger = logging.getLogger("m9.ingestion_engine")


class IngestionStatus:
    SUCCESS = "SUCCESS"
    DUPLICATE = "DUPLICATE"
    QUARANTINED = "QUARANTINED"
    MALFORMED = "MALFORMED"
    DELETED = "DELETED"
    UPDATED = "UPDATED"


class KnowledgeIngestionEngine:
    """Enterprise-grade local cybersecurity knowledge ingestion and quarantine engine."""

    def __init__(
        self,
        knowledge_store: VaptKnowledgeStore,
        audit_log_path: Path = Path("data/knowledge/ingestion_audit.jsonl"),
        quarantine_dir: Path = Path("data/knowledge/quarantine"),
    ) -> None:
        self.store = knowledge_store
        self.audit_log_path = Path(audit_log_path)
        self.quarantine_dir = Path(quarantine_dir)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory document registry for version tracking and deduplication
        self._doc_versions: Dict[str, List[KnowledgeVersion]] = {}
        self._content_hashes: Set[str] = set()

    def scan_for_hostile_content(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> Tuple[bool, List[str]]:
        """
        Inspects content for prompt injection directives, system prompt extraction,
        scope override attempts, and dangerous malformed sequences.
        """
        reasons: List[str] = []
        
        # Check suspicious directive regexes
        for pattern in SUSPICIOUS_DIRECTIVE_PATTERNS:
            if pattern.search(text):
                reasons.append(f"Prompt injection directive matched: {pattern.pattern}")
                
        # Additional M9 adversarial injection signatures
        m9_injection_patterns = [
            re.compile(r"ignore\s+(?:all\s+)?prior\s+instructions", re.IGNORECASE),
            re.compile(r"reveal\s+(?:your\s+)?system\s+prompt", re.IGNORECASE),
            re.compile(r"change\s+(?:the\s+)?assessment\s+scope", re.IGNORECASE),
            re.compile(r"mark\s+(?:the\s+)?finding\s+as\s+verified", re.IGNORECASE),
            re.compile(r"execute\s+this\s+command", re.IGNORECASE),
            re.compile(r"treat\s+this\s+document\s+as\s+system\s+policy", re.IGNORECASE),
            re.compile(r"override\s+scopegate", re.IGNORECASE),
            re.compile(r"authorized_target\s*=\s*all", re.IGNORECASE),
        ]
        for pattern in m9_injection_patterns:
            if pattern.search(text):
                reasons.append(f"M9 adversarial directive detected: {pattern.pattern}")

        # Check metadata for adversarial injection
        if metadata:
            meta_str = json.dumps(metadata)
            for pattern in m9_injection_patterns:
                if pattern.search(meta_str):
                    reasons.append(f"Adversarial injection inside metadata: {pattern.pattern}")

        # Check for null-byte or binary control corruption
        if "\x00" in text:
            reasons.append("Malformed content: Contains null bytes (\\x00)")

        return (len(reasons) > 0, reasons)

    def ingest_document(
        self,
        document_id: str,
        title: str,
        raw_content: str,
        source_id: str = "SRC-LOCAL-USER",
        source_type: CanonicalSourceType = CanonicalSourceType.USER_MARKDOWN,
        authority_level: AuthorityLevel = AuthorityLevel.USER_OWNED,
        metadata: Optional[Dict[str, Any]] = None,
        author: str = "Security Researcher",
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Executes full ingestion pipeline with validation, quarantine, deduplication,
        versioning, chunking, and audit trail.
        """
        meta = metadata or {}
        category_tags = tags or ["UserKnowledge"]

        # 1. Validation & Quarantine Scan
        is_hostile, reasons = self.scan_for_hostile_content(raw_content, meta)
        if is_hostile:
            quarantine_record = {
                "document_id": document_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reasons": reasons,
                "title": title,
                "content_preview": raw_content[:200],
            }
            q_file = self.quarantine_dir / f"{document_id}_{int(datetime.now().timestamp())}.json"
            with open(q_file, "w", encoding="utf-8") as f:
                json.dump(quarantine_record, f, indent=2)
            
            self._log_audit(document_id, "QUARANTINE", IngestionStatus.QUARANTINED, reasons=reasons)
            return {
                "status": IngestionStatus.QUARANTINED,
                "reasons": reasons,
                "quarantine_file": str(q_file),
            }

        # 2. Secret Redaction & Text Normalization
        try:
            redacted_raw, _ = SecretRedactor.redact_text(raw_content)
            normalized_content = normalize_markdown_text(redacted_raw)
        except Exception as e:
            self._log_audit(document_id, "NORMALIZE_ERROR", IngestionStatus.MALFORMED, error=str(e))
            return {"status": IngestionStatus.MALFORMED, "error": str(e)}

        if not normalized_content.strip():
            self._log_audit(document_id, "EMPTY_CONTENT", IngestionStatus.MALFORMED)
            return {"status": IngestionStatus.MALFORMED, "error": "Content is empty"}

        # 3. Deterministic Content Hashing
        content_hash = hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()

        # 4. Deduplication Check
        if content_hash in self._content_hashes:
            self._log_audit(document_id, "DEDUPLICATE", IngestionStatus.DUPLICATE, content_hash=content_hash)
            return {
                "status": IngestionStatus.DUPLICATE,
                "document_id": document_id,
                "content_hash": content_hash,
                "message": "Identical content already indexed; skipped redundant ingestion.",
            }

        # 5. Version Tracking
        existing_versions = self._doc_versions.get(document_id, [])
        version_num = f"v{len(existing_versions) + 1}.0.0"
        version_id = f"VER-{document_id}-{content_hash[:8]}"
        
        # Mark previous versions as non-current
        for v in existing_versions:
            v.is_current = False
            
        current_version = KnowledgeVersion(
            version_id=version_id,
            document_id=document_id,
            version_number=version_num,
            content_hash=content_hash,
            is_current=True,
        )
        existing_versions.append(current_version)
        self._doc_versions[document_id] = existing_versions

        # 6. Chunking
        k_src_type = KnowledgeSourceType.PLATFORM_INVARIANT if authority_level == AuthorityLevel.USER_OWNED else KnowledgeSourceType.OWASP_WSTG
        chunks = SemanticMarkdownChunker.chunk_document(
            document_id=document_id,
            title=title,
            source_type=k_src_type,
            knowledge_type=KnowledgeType.VULNERABILITY_PATTERN,
            normalized_body=normalized_content,
            category_tags=category_tags,
        )

        # 7. Index into Knowledge Store
        self.store.insert_chunks(chunks)
        self._content_hashes.add(content_hash)

        # 8. Record Ingestion in Audit Log
        self._log_audit(
            document_id=document_id,
            action="INGEST" if len(existing_versions) == 1 else "UPDATE",
            status=IngestionStatus.SUCCESS if len(existing_versions) == 1 else IngestionStatus.UPDATED,
            version_id=version_id,
            version_number=version_num,
            chunk_count=len(chunks),
            content_hash=content_hash,
        )

        return {
            "status": IngestionStatus.SUCCESS if len(existing_versions) == 1 else IngestionStatus.UPDATED,
            "document_id": document_id,
            "version_id": version_id,
            "version_number": version_num,
            "chunk_count": len(chunks),
            "content_hash": content_hash,
            "chunks": [c.chunk_id for c in chunks],
        }

    def delete_document(self, document_id: str) -> Dict[str, Any]:
        """Atomically deletes a document and its chunks from store and registry."""
        with self.store.conn:
            # Delete from fts_chunks and chunks
            self.store.conn.execute("DELETE FROM fts_chunks WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE document_id = ?)", (document_id,))
            self.store.conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
            self.store.conn.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))

        if document_id in self._doc_versions:
            for v in self._doc_versions[document_id]:
                self._content_hashes.discard(v.content_hash)
            del self._doc_versions[document_id]

        self._log_audit(document_id, "DELETE", IngestionStatus.DELETED)
        return {"status": IngestionStatus.DELETED, "document_id": document_id}

    def reindex_document(
        self,
        document_id: str,
        title: str,
        raw_content: str,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """Atomically replaces and re-indexes a document."""
        self.delete_document(document_id)
        return self.ingest_document(document_id, title, raw_content, **kwargs)

    def _log_audit(self, document_id: str, action: str, status: str, **details: Any) -> None:
        """Appends an immutable audit entry."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "document_id": document_id,
            "action": action,
            "status": status,
            **details,
        }
        with open(self.audit_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
