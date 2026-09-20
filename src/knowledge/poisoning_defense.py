"""Knowledge Poisoning Defense & Safe Serialization Enclosure.

Implements M3.12 per M3 Plan v2.3.8 Sections 18, 20, and 22:
- Non-destructive inspection of retrieved advisory knowledge
- Preservation of legitimate security testing text without destructive sanitization
- Delimiter breakout prevention via XML entity escaping (&, <, >)
- Telemetry logging of suspicious prompt injection markers without authority elevation
- Cryptographic integrity verification with fail-soft degradation (omit VAPT on tamper)
- Non-overridable execution boundaries (M2.75 execution engine retains exclusive authority)
"""

import html
import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.knowledge.models import (
    CorpusManifest,
    KnowledgeChunk,
    TrustRootRecord,
    VaptKnowledgePack,
)
from src.knowledge.provenance import (
    CryptographicTrustAuthority,
    ProvenanceVerificationError,
)

logger = logging.getLogger("m3.poisoning_defense")

# Common prompt injection / directive patterns for non-destructive detection
INJECTION_DIRECTIVE_PATTERNS = [
    re.compile(r"(ignore|disregard)\s+(all\s+)?(previous|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?(system|prompt|above)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(in\s+)?(DAN|developer\s+mode|unrestricted)", re.IGNORECASE),
    re.compile(r"system\s+(prompt|override)\s*:\s*", re.IGNORECASE),
    re.compile(r"admin\s+override\s*:\s*", re.IGNORECASE),
    re.compile(r"execute\s+(tool\s+)?command\s*:\s*", re.IGNORECASE),
    re.compile(r"</?vapt_methodology_advisory>", re.IGNORECASE),
    re.compile(r"</?advisory_chunk>", re.IGNORECASE),
    re.compile(r"</?untrusted_target_data>", re.IGNORECASE),
    re.compile(r"curl\s+https?://", re.IGNORECASE),
    re.compile(r"rm\s+-rf", re.IGNORECASE),
]


class PoisoningTelemetryEvent(dict):
    """Structured telemetry record for detected suspicious patterns in knowledge chunks."""
    pass


class KnowledgePoisoningDefense:
    """
    Guards the reasoning pipeline against adversarial corpus manipulation
    and prompt injection attempts originating from retrieved advisory knowledge.
    """

    @staticmethod
    def escape_advisory_text(text: str) -> str:
        """
        Non-destructively escape XML/HTML special characters (&, <, >)
        to prevent XML tag breakout while preserving text content verbatim.
        """
        if not text:
            return ""
        # Escape & first, then < and >
        # Note: Do not escape quotes or apostrophes to preserve readability
        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return escaped

    @classmethod
    def scan_for_injection_markers(
        cls,
        text: str,
        chunk_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Non-destructively inspect chunk text for directive/injection markers.
        
        CRITICAL INVARIANT:
        This method logs telemetry; it NEVER alters, truncates, or deletes the text.
        Legitimate cybersecurity text frequently discusses injection techniques.
        """
        detections: List[Dict[str, Any]] = []
        for pattern in INJECTION_DIRECTIVE_PATTERNS:
            matches = list(pattern.finditer(text))
            for m in matches:
                event = {
                    "event_type": "POISONING_MARKER_DETECTED",
                    "chunk_id": chunk_id,
                    "matched_pattern": pattern.pattern,
                    "matched_text": m.group(0),
                    "start_offset": m.start(),
                    "end_offset": m.end(),
                    "action": "PRESERVED_NON_DESTRUCTIVE",
                }
                detections.append(event)
                logger.info(f"Advisory text marker logged: {event}")
        return detections

    @classmethod
    def sanitize_pack_for_serialization(
        cls,
        pack: VaptKnowledgePack,
    ) -> VaptKnowledgePack:
        """
        Apply non-destructive escaping and marker auditing to all chunks in a pack.
        """
        all_detections = []
        sanitized_items = []

        for item in pack.items:
            chunk = item.chunk
            # Audit for telemetry
            detections = cls.scan_for_injection_markers(
                chunk.content, chunk_id=chunk.chunk_id
            )
            all_detections.extend(detections)

            # Escaping: escape &, <, > in content
            escaped_content = cls.escape_advisory_text(chunk.content)
            chunk_copy = chunk.model_copy(update={"content": escaped_content})
            item_copy = item.model_copy(update={"chunk": chunk_copy})
            sanitized_items.append(item_copy)

        return pack.model_copy(update={"items": sanitized_items})

    @classmethod
    def verify_corpus_integrity(
        cls,
        manifest: CorpusManifest,
        signature_bytes: bytes,
        trust_root: TrustRootRecord,
        chunks: Sequence[KnowledgeChunk],
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify cryptographic integrity of advisory corpus.
        
        Returns:
            (True, None) if verified.
            (False, error_code) if verification failed.
        """
        try:
            CryptographicTrustAuthority.verify_corpus_integrity(
                manifest=manifest,
                signature_bytes=signature_bytes,
                trust_root=trust_root,
                chunks=chunks,
            )
            return True, None
        except ProvenanceVerificationError as e:
            logger.error(f"Corpus verification error [{e.code}]: {e.message}")
            return False, e.code
        except Exception as e:
            logger.error(f"Unexpected corpus verification error: {e}")
            return False, "CORPUS_INTEGRITY_UNKNOWN_ERROR"

    @staticmethod
    def enforce_execution_boundary(
        action_name: str,
        attempted_parameters: Dict[str, Any],
    ) -> None:
        """
        Enforce that advisory knowledge cannot alter M2.75 execution invariants:
        - Cannot approve execution
        - Cannot issue session tokens / CSRF nonces
        - Cannot expand CIDR scope
        """
        forbidden_keys = {
            "credentials",
            "cookies",
            "cookie",
            "csrf_token",
            "session_token",
            "refresh_token",
            "nonce",
            "signing_key",
            "cidr_scope",
            "execution_approval",
            "rate_limit_bypass",
        }
        found_keys = forbidden_keys.intersection(set(attempted_parameters.keys()))
        if found_keys:
            raise PermissionError(
                f"EXECUTION_BOUNDARY_VIOLATION: Advisory reasoning attempted to set execution-privileged parameter(s): {found_keys}"
            )
