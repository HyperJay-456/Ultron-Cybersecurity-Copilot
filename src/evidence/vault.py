"""Reversible Secret Redaction Vault protecting sensitive credentials while preserving correlation."""

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple


class RedactionVault:
    """
    Reversible secret redaction vault. Replaces secrets, JWTs, AWS credentials,
    and passwords with stable typed placeholders ([REDACTED_JWT_1]) so the LLM
    reasons over placeholders without leaking secrets into embeddings or logs.
    Preserves exact value identity across sessions for correlation.
    """

    # Secret identification patterns
    JWT_PATTERN = re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}")
    AWS_KEY_PATTERN = re.compile(r"AKIA[0-9A-Z]{16}")
    AWS_SECRET_PATTERN = re.compile(
        r"""(["']?(?:aws_secret_access_key|secret_access_key|SecretAccessKey|aws_secret_key)["']?\s*[:=]\s*["']?)([A-Za-z0-9/+=]{40})(["']?)""",
        re.IGNORECASE,
    )
    BASIC_AUTH_PATTERN = re.compile(r"(Basic\s+)([A-Za-z0-9+/=]{16,})", re.IGNORECASE)
    BEARER_AUTH_PATTERN = re.compile(r"(Bearer\s+)([A-Za-z0-9_\-\.]{16,})", re.IGNORECASE)
    COOKIE_HEADER_PATTERN = re.compile(r"((?:Cookie|Set-Cookie):\s*)([^\r\n]+)", re.IGNORECASE)
    SESSION_TOKEN_PATTERN = re.compile(
        r"""(["']?(?:session_?token|aws_session_token|session_?id|sess_?id|phpsessid|jsessionid|connect\.sid)["']?\s*[:=]\s*["']?)([^"'\s&,;\}]+)(["']?)""",
        re.IGNORECASE,
    )
    REFRESH_TOKEN_PATTERN = re.compile(
        r"""(["']?(?:refresh_?token)["']?\s*[:=]\s*["']?)([^"'\s&,;\}]+)(["']?)""",
        re.IGNORECASE,
    )
    SENSITIVE_KEY_PATTERN = re.compile(
        r"^(password|passwd|secret|token|api[_-]?key|auth|authorization|access[_-]?token|"
        r"refresh[_-]?token|session[_-]?(?:token|id)?|sess[_-]?id|phpsessid|jsessionid|connect\.sid|"
        r"ssn|credit[_-]?card|aws[_-]?(?:secret[_-]?access[_-]?)?key|secret[_-]?key)$",
        re.IGNORECASE,
    )
    KEY_VALUE_SECRET_PATTERN = re.compile(
        r"""(["']?(?:password|passwd|secret|token|api[_-]?key|auth|access[_-]?token|ssn|credit[_-]?card)["']?\s*[:=]\s*["']?)([^"'\s&,;\}]+)(["']?)""",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        self._raw_to_placeholder: Dict[str, str] = {}
        self._placeholder_to_raw: Dict[str, str] = {}
        self._category_counters: Dict[str, int] = {}

    def _get_or_create_placeholder(self, raw_value: str, category: str) -> str:
        """Assign or retrieve a stable placeholder for this exact raw value."""
        if raw_value in self._raw_to_placeholder:
            return self._raw_to_placeholder[raw_value]

        count = self._category_counters.get(category, 0) + 1
        self._category_counters[category] = count
        placeholder = f"[REDACTED_{category}_{count}]"

        self._raw_to_placeholder[raw_value] = placeholder
        self._placeholder_to_raw[placeholder] = raw_value
        return placeholder

    def redact_text(self, text: str) -> str:
        """Scan free text and replace sensitive signatures with typed placeholders."""
        if not text:
            return ""

        # 1. Redact JWTs
        def _replace_jwt(match: re.Match) -> str:
            val = match.group(0)
            return self._get_or_create_placeholder(val, "JWT")
        text = self.JWT_PATTERN.sub(_replace_jwt, text)

        # 2. Redact AWS Access Keys
        def _replace_aws_key(match: re.Match) -> str:
            val = match.group(0)
            return self._get_or_create_placeholder(val, "AWS_KEY")
        text = self.AWS_KEY_PATTERN.sub(_replace_aws_key, text)

        # 3. Redact AWS Secret Access Keys
        def _replace_aws_secret(match: re.Match) -> str:
            prefix, val, suffix = match.group(1), match.group(2), match.group(3)
            if val.startswith("[REDACTED_"):
                return match.group(0)
            placeholder = self._get_or_create_placeholder(val, "AWS_SECRET")
            return f"{prefix}{placeholder}{suffix}"
        text = self.AWS_SECRET_PATTERN.sub(_replace_aws_secret, text)

        # 4. Redact Basic Auth
        def _replace_basic(match: re.Match) -> str:
            prefix, val = match.group(1), match.group(2)
            if val.startswith("[REDACTED_"):
                return match.group(0)
            placeholder = self._get_or_create_placeholder(val, "BASIC_AUTH")
            return f"{prefix}{placeholder}"
        text = self.BASIC_AUTH_PATTERN.sub(_replace_basic, text)

        # 5. Redact Bearer Auth
        def _replace_bearer(match: re.Match) -> str:
            prefix, val = match.group(1), match.group(2)
            if val.startswith("[REDACTED_"):
                return match.group(0)
            placeholder = self._get_or_create_placeholder(val, "BEARER_TOKEN")
            return f"{prefix}{placeholder}"
        text = self.BEARER_AUTH_PATTERN.sub(_replace_bearer, text)

        # 6. Redact Cookie / Set-Cookie Headers preserving attributes
        def _replace_cookie_header(match: re.Match) -> str:
            header_prefix = match.group(1)
            raw_cookies = match.group(2)
            parts = raw_cookies.split(";")
            preserved_parts = []
            standard_attrs = {"path", "domain", "expires", "max-age", "samesite", "secure", "httponly"}

            for part in parts:
                trimmed = part.strip()
                if "=" in trimmed:
                    c_name, c_val = trimmed.split("=", 1)
                    clean_name = c_name.strip()
                    clean_val = c_val.strip()
                    if clean_name.lower() in standard_attrs or clean_val.startswith("[REDACTED_"):
                        preserved_parts.append(trimmed)
                    else:
                        placeholder = self._get_or_create_placeholder(clean_val, "COOKIE")
                        preserved_parts.append(f"{clean_name}={placeholder}")
                else:
                    preserved_parts.append(trimmed)
            return f"{header_prefix}{'; '.join(preserved_parts)}"
        text = self.COOKIE_HEADER_PATTERN.sub(_replace_cookie_header, text)

        # 7. Redact Session Tokens / Session IDs
        def _replace_session(match: re.Match) -> str:
            prefix, val, suffix = match.group(1), match.group(2), match.group(3)
            if val.startswith("[REDACTED_"):
                return match.group(0)
            placeholder = self._get_or_create_placeholder(val, "SESSION_TOKEN")
            return f"{prefix}{placeholder}{suffix}"
        text = self.SESSION_TOKEN_PATTERN.sub(_replace_session, text)

        # 8. Redact Refresh Tokens
        def _replace_refresh(match: re.Match) -> str:
            prefix, val, suffix = match.group(1), match.group(2), match.group(3)
            if val.startswith("[REDACTED_"):
                return match.group(0)
            placeholder = self._get_or_create_placeholder(val, "REFRESH_TOKEN")
            return f"{prefix}{placeholder}{suffix}"
        text = self.REFRESH_TOKEN_PATTERN.sub(_replace_refresh, text)

        # 9. Redact Key-Value Secrets (password, token, api_key, etc.)
        def _replace_kv(match: re.Match) -> str:
            prefix = match.group(1)
            val = match.group(2)
            suffix = match.group(3)
            if val.startswith("[REDACTED_"):
                return match.group(0)
            placeholder = self._get_or_create_placeholder(val, "SECRET")
            return f"{prefix}{placeholder}{suffix}"
        text = self.KEY_VALUE_SECRET_PATTERN.sub(_replace_kv, text)

        return text

    def redact_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively redact dictionary keys and values."""
        clean: Dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, dict):
                clean[key] = self.redact_dict(value)
            elif isinstance(value, list):
                clean[key] = [
                    self.redact_dict(item) if isinstance(item, dict)
                    else (self.redact_text(str(item)) if isinstance(item, str) else item)
                    for item in value
                ]
            elif isinstance(value, str):
                if self.SENSITIVE_KEY_PATTERN.search(key):
                    # Redact entire value if key name indicates a secret
                    clean[key] = self._get_or_create_placeholder(value, "SECRET")
                else:
                    clean[key] = self.redact_text(value)
            else:
                clean[key] = value
        return clean

    def reverse_placeholder(self, placeholder: str) -> Optional[str]:
        """Look up the original raw secret for an authorized human verification check."""
        return self._placeholder_to_raw.get(placeholder)

    def reverse_text(self, text: str) -> str:
        """Reconstitute placeholders back to original secrets for human verification."""
        result = text
        for placeholder, raw in self._placeholder_to_raw.items():
            result = result.replace(placeholder, raw)
        return result
