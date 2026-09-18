"""Scope Gate enforcement engine with DNS TOCTOU hardening and auditable decisions."""

import ipaddress
import socket
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse
import tldextract
import yaml

from src.core.logging import AuditLogger, get_logger
from src.database.manager import DatabaseManager
from src.scope.models import ScopeDecision, ScopeDecisionObject, ScopePolicy, ToolPolicy

logger = get_logger("ScopeGate")


class ScopeValidationError(Exception):
    """Raised when scope configuration contains dangerous or invalid rules."""
    pass


class ScopeGate:
    """
    Architectural gatekeeper validating all network targets against program scope.
    Guarantees that every network action has an explicit, valid ScopeDecisionObject.
    """

    def __init__(
        self,
        policy_path: Optional[Path] = None,
        policy: Optional[ScopePolicy] = None,
        db_manager: Optional[DatabaseManager] = None,
        audit_logger: Optional[AuditLogger] = None,
        allow_private_ranges: bool = False,
        dns_resolver=None,
    ) -> None:
        self.db_manager = db_manager
        self.audit_logger = audit_logger
        self.allow_private_ranges = allow_private_ranges
        self.dns_resolver = dns_resolver or self._default_resolve_addresses

        # Initialize TLDExtract with offline local cache
        cache_dir = Path("data/cache/tld_cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._extractor = tldextract.TLDExtract(cache_dir=str(cache_dir), suffix_list_urls=None)

        if policy:
            self.policy = policy
        elif policy_path:
            self.policy = self.load_policy(policy_path)
        else:
            default_path = Path("scope.yaml")
            if default_path.exists():
                self.policy = self.load_policy(default_path)
            else:
                self.policy = ScopePolicy(
                    program_name="unconfigured",
                    platform="unknown",
                    in_scope=[],
                )

        self._validate_policy_patterns()

    def load_policy(self, path: Path) -> ScopePolicy:
        """Load and parse scope policy from YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        # Parse tool policies
        tool_policies = {}
        for tool, pol_str in (raw.get("tool_policy") or {}).items():
            try:
                tool_policies[tool.lower()] = ToolPolicy(pol_str)
            except ValueError:
                tool_policies[tool.lower()] = ToolPolicy.ACTIVE

        # Normalize rules of engagement
        roe = dict(raw.get("rules_of_engagement") or {})
        no_scan = roe.get("no_automated_scanning_on", [])
        if isinstance(no_scan, str):
            no_scan = [no_scan]
        elif not isinstance(no_scan, list):
            no_scan = []
        roe["no_automated_scanning_on"] = no_scan

        disallowed = roe.get("disallowed_techniques", [])
        if isinstance(disallowed, str):
            disallowed = [disallowed]
        elif not isinstance(disallowed, list):
            disallowed = []
        roe["disallowed_techniques"] = disallowed

        return ScopePolicy(
            program_name=raw.get("program_name", "unnamed"),
            platform=raw.get("platform", "unknown"),
            scope_policy_version=raw.get("scope_policy_version", "v6"),
            in_scope=raw.get("in_scope", []),
            out_of_scope=raw.get("out_of_scope", []),
            program_constraints=raw.get("program_constraints", {}) or {},
            rules_of_engagement=roe,
            tool_policy=tool_policies,
        )

    def _validate_policy_patterns(self) -> None:
        """Reject overbroad wildcard patterns that would place entire TLDs in scope."""
        all_patterns = self.policy.in_scope + self.policy.out_of_scope
        for pat in all_patterns:
            clean = pat.lower().strip()
            if clean.startswith("*."):
                domain_part = clean[2:]
                ext = self._extractor(domain_part)
                # If there is no domain or domain equals suffix, it's an entire TLD (e.g. *.com, *.co.uk)
                if not ext.domain:
                    raise ScopeValidationError(
                        f"Dangerous overbroad wildcard scope pattern '{pat}': cannot target an entire TLD."
                    )

    def canonicalize_host(self, raw_url: str) -> Optional[str]:
        """Extract canonical lowercased host without port."""
        if not raw_url or not isinstance(raw_url, str):
            return None
        if "://" not in raw_url:
            raw_url = f"https://{raw_url}"
        try:
            parsed = urlparse(raw_url)
            host = parsed.hostname
            if host:
                return host.lower().rstrip(".")
            return None
        except (ValueError, AttributeError):
            return None

    def _matches_pattern(self, host: str, pattern: str) -> bool:
        """Check if canonical host matches a scope pattern."""
        pat = pattern.lower().strip()
        if pat.startswith("*."):
            suffix = pat[2:]
            return host == suffix or host.endswith("." + suffix)
        return host == pat

    def _matches_path_rule(self, canonical_host: str, requested_url: str, pattern: str) -> bool:
        """Check if requested URL matches a no_automated_scanning_on rule pattern."""
        if not pattern or not isinstance(pattern, str):
            return False
        clean_pat = pattern.lower().strip()

        parsed = urlparse(requested_url if "://" in requested_url else f"https://{requested_url}")
        req_path = (parsed.path or "/").rstrip("/").lower()
        if not req_path:
            req_path = "/"

        # Pattern format 1: host/path (e.g. "auth.target.com/oauth/token")
        if "/" in clean_pat and not clean_pat.startswith("/"):
            parts = clean_pat.split("/", 1)
            rule_host = parts[0]
            rule_path = "/" + parts[1].rstrip("/")
            if self._matches_pattern(canonical_host, rule_host):
                if req_path == rule_path or req_path.startswith(f"{rule_path}/"):
                    return True
                if rule_path.endswith("*") and req_path.startswith(rule_path[:-1]):
                    return True
            return False

        # Pattern format 2: path only (e.g. "/oauth/token" or "oauth/token")
        rule_path = clean_pat if clean_pat.startswith("/") else f"/{clean_pat}"
        rule_path = rule_path.rstrip("/")
        if req_path == rule_path or req_path.startswith(f"{rule_path}/"):
            return True
        if rule_path.endswith("*") and req_path.startswith(rule_path[:-1]):
            return True
        return False

    def _default_resolve_addresses(self, host: str) -> List[str]:
        """Resolve all IPv4 and IPv6 addresses for a given host."""
        try:
            # Look up both A and AAAA records
            records = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
            addresses = set()
            for rec in records:
                sockaddr = rec[4]
                ip_str = sockaddr[0]
                addresses.add(ip_str)
            return sorted(list(addresses))
        except (socket.gaierror, socket.herror, ValueError):
            return []

    def evaluate(
        self,
        requested_url: str,
        tool_name: str = "httpx",
        technique: Optional[str] = None,
        allow_passive: bool = False,
    ) -> ScopeDecisionObject:
        """
        Evaluate requested target URL against Scope Gate invariants.
        Returns an immutable ScopeDecisionObject.
        """
        canonical_host = self.canonicalize_host(requested_url)
        tool_policy = self.policy.tool_policy.get(tool_name.lower(), ToolPolicy.ACTIVE)

        if not canonical_host:
            return self._record_decision(
                ScopeDecision.DENY,
                requested_url,
                canonical_host or "invalid-host",
                [],
                tool_policy,
                "Failed to parse valid canonical host from URL",
            )

        # 1. Tool policy enforcement: passive tools cannot perform active network requests
        if tool_policy == ToolPolicy.PASSIVE and not allow_passive:
            return self._record_decision(
                ScopeDecision.DENY,
                requested_url,
                canonical_host,
                [],
                tool_policy,
                f"Tool '{tool_name}' has passive policy; active network requests are prohibited by tool policy",
            )

        # 2. Rules of Engagement: Disallowed techniques enforcement
        if technique:
            clean_tech = technique.lower().strip()
            disallowed = [t.lower().strip() for t in self.policy.rules_of_engagement.get("disallowed_techniques", [])]
            if clean_tech in disallowed:
                return self._record_decision(
                    ScopeDecision.DENY,
                    requested_url,
                    canonical_host,
                    [],
                    tool_policy,
                    f"Technique '{technique}' is prohibited by rules of engagement",
                )

        # 3. Rules of Engagement: Prohibited automated scanning paths (no_automated_scanning_on)
        for pat in self.policy.rules_of_engagement.get("no_automated_scanning_on", []):
            if self._matches_path_rule(canonical_host, requested_url, pat):
                return self._record_decision(
                    ScopeDecision.DENY,
                    requested_url,
                    canonical_host,
                    [],
                    tool_policy,
                    f"Target endpoint matches no_automated_scanning_on rule: {pat}",
                )

        # 4. Check out-of-scope rules (Out-of-scope always wins)
        for out_rule in self.policy.out_of_scope:
            if self._matches_pattern(canonical_host, out_rule):
                return self._record_decision(
                    ScopeDecision.DENY,
                    requested_url,
                    canonical_host,
                    [],
                    tool_policy,
                    f"Host matches explicit out_of_scope rule: {out_rule}",
                    out_of_scope_rule=out_rule,
                )

        # 5. Check in-scope rules
        matched_in_rule = None
        for in_rule in self.policy.in_scope:
            if self._matches_pattern(canonical_host, in_rule):
                matched_in_rule = in_rule
                break

        if not matched_in_rule:
            return self._record_decision(
                ScopeDecision.DENY,
                requested_url,
                canonical_host,
                [],
                tool_policy,
                "Host does not match any authorized in_scope rule",
            )

        # 6. DNS TOCTOU Defense: Resolve all A and AAAA addresses
        resolved_ips = self.dns_resolver(canonical_host)
        if not resolved_ips:
            return self._record_decision(
                ScopeDecision.DENY,
                requested_url,
                canonical_host,
                [],
                tool_policy,
                "DNS resolution failed (fail-closed policy)",
                matched_rule=matched_in_rule,
            )

        # Validate every resolved IP against prohibited ranges (SSRF / DNS rebinding defense)
        for ip_str in resolved_ips:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                if ip_obj.is_loopback:
                    return self._record_decision(
                        ScopeDecision.DENY,
                        requested_url,
                        canonical_host,
                        resolved_ips,
                        tool_policy,
                        f"Resolved address {ip_str} is a loopback address",
                        matched_rule=matched_in_rule,
                    )
                if ip_obj.is_link_local:
                    return self._record_decision(
                        ScopeDecision.DENY,
                        requested_url,
                        canonical_host,
                        resolved_ips,
                        tool_policy,
                        f"Resolved address {ip_str} is a link-local address",
                        matched_rule=matched_in_rule,
                    )
                if ip_obj.is_multicast:
                    return self._record_decision(
                        ScopeDecision.DENY,
                        requested_url,
                        canonical_host,
                        resolved_ips,
                        tool_policy,
                        f"Resolved address {ip_str} is a multicast address",
                        matched_rule=matched_in_rule,
                    )
                if not self.allow_private_ranges and ip_obj.is_private:
                    return self._record_decision(
                        ScopeDecision.DENY,
                        requested_url,
                        canonical_host,
                        resolved_ips,
                        tool_policy,
                        f"Resolved address {ip_str} is a private IP address (SSRF blocked)",
                        matched_rule=matched_in_rule,
                    )
                if ip_obj.is_reserved:
                    return self._record_decision(
                        ScopeDecision.DENY,
                        requested_url,
                        canonical_host,
                        resolved_ips,
                        tool_policy,
                        f"Resolved address {ip_str} is an IETF reserved address",
                        matched_rule=matched_in_rule,
                    )
            except ValueError:
                return self._record_decision(
                    ScopeDecision.DENY,
                    requested_url,
                    canonical_host,
                    resolved_ips,
                    tool_policy,
                    f"Invalid IP address format: {ip_str}",
                    matched_rule=matched_in_rule,
                )

        # All invariants passed!
        return self._record_decision(
            ScopeDecision.ALLOW,
            requested_url,
            canonical_host,
            resolved_ips,
            tool_policy,
            f"Authorized destination matching rule: {matched_in_rule}",
            matched_rule=matched_in_rule,
        )

    def _record_decision(
        self,
        decision: ScopeDecision,
        requested_url: str,
        canonical_host: str,
        resolved_addresses: List[str],
        tool_policy: ToolPolicy,
        reason: str,
        matched_rule: Optional[str] = None,
        out_of_scope_rule: Optional[str] = None,
    ) -> ScopeDecisionObject:
        """Create, audit, and persist the ScopeDecisionObject."""
        obj = ScopeDecisionObject.create(
            decision=decision,
            requested_url=requested_url,
            canonical_host=canonical_host,
            resolved_addresses=resolved_addresses,
            tool_policy=tool_policy,
            reason=reason,
            matched_rule=matched_rule,
            out_of_scope_rule=out_of_scope_rule,
            scope_policy_version=self.policy.scope_policy_version,
        )

        if self.db_manager:
            try:
                self.db_manager.insert_scope_decision(obj.model_dump())
            except Exception as exc:
                logger.error(f"Failed to persist scope decision {obj.scope_decision_id} to database: {exc}")
                if decision == ScopeDecision.ALLOW:
                    # Fail closed: cannot permit network request if audit persistence fails
                    return ScopeDecisionObject.create(
                        decision=ScopeDecision.DENY,
                        requested_url=requested_url,
                        canonical_host=canonical_host,
                        resolved_addresses=resolved_addresses,
                        tool_policy=tool_policy,
                        reason=f"Audit database failure on ALLOW decision (fail-closed): {exc}",
                        scope_policy_version=self.policy.scope_policy_version,
                    )

        if self.audit_logger:
            try:
                self.audit_logger.log_event(
                    event_type="SCOPE_DECISION",
                    actor="ScopeGate",
                    subject_id=obj.scope_decision_id,
                    new_state=obj.decision.value,
                    details=obj.model_dump(),
                )
            except Exception as exc:
                logger.error(f"Failed to write scope decision {obj.scope_decision_id} to audit log: {exc}")
                if decision == ScopeDecision.ALLOW:
                    # Fail closed: cannot permit network request if audit log write fails
                    return ScopeDecisionObject.create(
                        decision=ScopeDecision.DENY,
                        requested_url=requested_url,
                        canonical_host=canonical_host,
                        resolved_addresses=resolved_addresses,
                        tool_policy=tool_policy,
                        reason=f"Audit logger failure on ALLOW decision (fail-closed): {exc}",
                        scope_policy_version=self.policy.scope_policy_version,
                    )

        return obj
