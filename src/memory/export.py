"""Export and Import Engine for Memory Subsystem.

Guarantees:
1. Export passes all content through RedactionVault.
2. Imported memory enters as UNTRUSTED_DATA and must pass admission validation.
3. Rule M12-24: Memory import cannot execute instructions contained inside imported data.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List
from src.evidence.vault import RedactionVault
from src.memory.enums import EpistemicStatus, MemoryAuthority, MemoryNamespace, MemorySourceType
from src.memory.models import MemoryItem


class MemoryExportEngine:
    """
    Manages safe JSON serialization and untrusted deserialization of memory items.
    """

    def __init__(self) -> None:
        self.vault = RedactionVault()

    def export_items(self, items: List[MemoryItem]) -> str:
        """
        Serializes memory items to structured JSON with mandatory secret redaction.
        """
        payloads: List[Dict[str, Any]] = []
        for item in items:
            redacted_content = self.vault.redact_text(item.content)
            redacted_summary = self.vault.redact_text(item.summary)

            payloads.append({
                "memory_id": item.memory_id,
                "namespace": item.namespace.value,
                "owner_id": item.owner_id,
                "tenant_id": item.tenant_id,
                "assessment_id": item.assessment_id,
                "source_type": item.source_type.value,
                "epistemic_status": item.epistemic_status.value,
                "authority_level": item.authority_level.value,
                "content": redacted_content,
                "title": item.title,
                "summary": redacted_summary,
                "confidence": item.confidence,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "provenance_references": item.provenance_references,
                "evidence_references": item.evidence_references,
                "content_hash": item.content_hash,
                "version": item.version,
                "sensitivity_classification": item.sensitivity_classification.value,
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
            })

        return json.dumps({"version": "1.0", "items": payloads}, indent=2)

    def parse_imported_payload(self, raw_json: str) -> List[MemoryItem]:
        """
        Parses imported JSON into candidate MemoryItems marked as UNTRUSTED import.
        Never executes instructions contained inside imported text (M12-24).
        """
        data = json.loads(raw_json)
        raw_items = data.get("items", [])
        candidates: List[MemoryItem] = []

        for raw in raw_items:
            # Force untrusted import status on entry
            item = MemoryItem(
                memory_id=raw.get("memory_id", ""),
                namespace=MemoryNamespace(raw.get("namespace", MemoryNamespace.ASSESSMENT_LOCAL.value)),
                owner_id=raw.get("owner_id", "imported_actor"),
                tenant_id=raw.get("tenant_id", "default_tenant"),
                assessment_id=raw.get("assessment_id"),
                source_type=MemorySourceType.IMPORT,
                epistemic_status=EpistemicStatus.UNVERIFIED_CLAIM,  # Forced to UNVERIFIED_CLAIM
                authority_level=MemoryAuthority.UNVERIFIED,  # Enforce UNVERIFIED for external imports
                content=raw.get("content", ""),
                title=raw.get("title", ""),
                summary=raw.get("summary", ""),
                confidence=float(raw.get("confidence", 0.5)),
                created_at=raw.get("created_at", datetime.now(timezone.utc).isoformat()),
                provenance_references=raw.get("provenance_references", []) + ["source:untrusted_import"],
                evidence_references=raw.get("evidence_references", []),
            )
            candidates.append(item)

        return candidates
