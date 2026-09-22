"""Scoped HTTP client enforcing Scope Gate validation, shared rate limiting, and DNS TOCTOU IP-pinning."""

import ipaddress
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
import httpx

from src.scope.gate import ScopeGate
from src.scope.models import ScopeDecision, ScopeDecisionObject


class ScopeViolationError(Exception):
    """Raised when an outbound HTTP request or redirect violates the program scope."""
    def __init__(self, decision: ScopeDecisionObject) -> None:
        self.decision = decision
        super().__init__(
            f"Scope Violation ({decision.decision.value}): Destination '{decision.requested_url}' "
            f"blocked by Scope Gate: {decision.reason} [ID: {decision.scope_decision_id}]"
        )


class SharedRateLimiter:
    """
    Thread-safe, process-wide shared rate limiter.
    Enforces requests-per-second limits across multiple client instances and concurrent workers.
    """
    _registry: Dict[str, "SharedRateLimiter"] = {}
    _registry_lock = threading.Lock()

    def __init__(self, rate_limit_rps: float, burst_capacity: Optional[float] = None) -> None:
        self.rate_limit_rps = float(rate_limit_rps)
        self.capacity = float(burst_capacity) if burst_capacity is not None else 1.0
        self.tokens = self.capacity
        self.last_update = time.monotonic()
        self.lock = threading.Lock()

    @classmethod
    def get_limiter(
        cls,
        key: str,
        rate_limit_rps: float,
        burst_capacity: Optional[float] = None,
    ) -> "SharedRateLimiter":
        with cls._registry_lock:
            if key not in cls._registry:
                cls._registry[key] = cls(rate_limit_rps=rate_limit_rps, burst_capacity=burst_capacity)
            else:
                limiter = cls._registry[key]
                if rate_limit_rps > 0 and limiter.rate_limit_rps != rate_limit_rps:
                    limiter.rate_limit_rps = rate_limit_rps
            return cls._registry[key]

    @classmethod
    def reset_all(cls) -> None:
        with cls._registry_lock:
            cls._registry.clear()

    def acquire(self, tokens: float = 1.0) -> float:
        """
        Acquires tokens from bucket under lock.
        Sleeps if insufficient tokens are available to pace requests.
        Returns time waited in seconds.
        """
        if self.rate_limit_rps <= 0:
            return 0.0

        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_limit_rps)

            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0

            needed = tokens - self.tokens
            sleep_time = needed / self.rate_limit_rps
            time.sleep(sleep_time)
            self.last_update = time.monotonic()
            self.tokens = 0.0
            return sleep_time


class ScopedHttpClient:
    """
    HTTP client that guarantees no network request or redirect executes
    without authorization from the ScopeGate, with shared rate limiting and
    DNS TOCTOU IP-pinning.
    """

    def __init__(
        self,
        scope_gate: ScopeGate,
        tool_name: str = "httpx",
        max_redirects: int = 5,
        timeout: float = 15.0,
        rate_limit_rps: Optional[float] = None,
        enforce_ip_pinning: bool = True,
        transport: Optional[httpx.BaseTransport] = None,
        client: Optional[httpx.Client] = None,
        shared_rate_limiter: Optional[SharedRateLimiter] = None,
    ) -> None:
        self.scope_gate = scope_gate
        self.tool_name = tool_name
        self.max_redirects = max_redirects
        self.timeout = timeout
        self.enforce_ip_pinning = enforce_ip_pinning
        self.transport = transport

        # Validate and harden injected client against redirect bypass
        self._external_client = client
        if self._external_client is not None:
            if hasattr(self._external_client, "follow_redirects"):
                try:
                    self._external_client.follow_redirects = False
                except Exception as e:
                    raise ValueError(f"Cannot control redirect behavior on injected client: {e}")

        # Configure rate limit (rps)
        if rate_limit_rps is not None:
            self.rate_limit_rps = float(rate_limit_rps) if rate_limit_rps > 0 else None
        else:
            pol_rps = scope_gate.policy.rules_of_engagement.get("rate_limit_rps")
            try:
                self.rate_limit_rps = float(pol_rps) if pol_rps and float(pol_rps) > 0 else None
            except (ValueError, TypeError):
                self.rate_limit_rps = None

        # Bind to shared process-wide rate limiter
        if shared_rate_limiter:
            self.rate_limiter = shared_rate_limiter
        elif self.rate_limit_rps and self.rate_limit_rps > 0:
            program_key = scope_gate.policy.program_name or "default_program"
            self.rate_limiter = SharedRateLimiter.get_limiter(
                key=f"program:{program_key}",
                rate_limit_rps=self.rate_limit_rps,
            )
        else:
            self.rate_limiter = None

    def _enforce_rate_limit(self) -> None:
        """Paces requests across all clients and workers using shared limiter."""
        if self.rate_limiter:
            self.rate_limiter.acquire(1.0)

    def request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
        json_data: Optional[Any] = None,
        follow_redirects: bool = True,
        technique: Optional[str] = None,
        **kwargs: Any,
    ) -> Tuple[httpx.Response, ScopeDecisionObject]:
        """
        Execute request after verifying initial URL and every redirect hop.
        Guarantees that no redirect occurs without ScopeGate evaluation.
        """
        current_url = url
        redirect_count = 0
        visited_urls: Set[str] = set()

        client_cm = self._external_client or httpx.Client(
            timeout=self.timeout,
            follow_redirects=False,
            transport=self.transport,
        )

        should_close = self._external_client is None

        # Always enforce follow_redirects=False on HTTP transport
        kwargs["follow_redirects"] = False

        try:
            while True:
                # 1. Gate check for current target (initial URL or redirect destination)
                decision = self.scope_gate.evaluate(
                    current_url,
                    tool_name=self.tool_name,
                    technique=technique,
                )
                if decision.decision != ScopeDecision.ALLOW:
                    raise ScopeViolationError(decision)

                # 2. Shared Rate limit pacing
                self._enforce_rate_limit()

                # 3. DNS TOCTOU Defense: IP-Pinning with TLS SNI and Host preservation
                req_headers = dict(headers or {})
                req_extensions = dict(kwargs.pop("extensions", {}) or {})

                parsed = urlparse(current_url)
                canonical_host = parsed.hostname or ""
                scheme = parsed.scheme.lower()
                port = parsed.port or (443 if scheme == "https" else 80)
                path_and_query = parsed.path or "/"
                if parsed.query:
                    path_and_query += f"?{parsed.query}"

                if self.enforce_ip_pinning and decision.resolved_addresses:
                    pinned_ip = decision.resolved_addresses[0]
                    try:
                        ip_obj = ipaddress.ip_address(pinned_ip)
                        formatted_ip = f"[{pinned_ip}]" if ip_obj.version == 6 else pinned_ip
                    except ValueError:
                        formatted_ip = pinned_ip

                    dest_url = f"{scheme}://{formatted_ip}:{port}{path_and_query}"

                    # Host header preservation
                    if "Host" not in req_headers and "host" not in req_headers:
                        req_headers["Host"] = f"{canonical_host}:{port}" if parsed.port else canonical_host

                    # TLS SNI preservation
                    if scheme == "https":
                        req_extensions["sni_hostname"] = canonical_host
                else:
                    dest_url = current_url

                # 4. Execute request for current target strictly without automatic redirects
                response = client_cm.request(
                    method=method,
                    url=dest_url,
                    headers=req_headers,
                    data=data,
                    json=json_data,
                    extensions=req_extensions,
                    **kwargs,
                )

                # 5. Check for redirect hop
                if follow_redirects and response.is_redirect and "location" in response.headers:
                    redirect_count += 1
                    if redirect_count > self.max_redirects:
                        raise httpx.TooManyRedirects(f"Exceeded maximum redirects ({self.max_redirects})")

                    location = response.headers["location"]
                    next_url = urljoin(current_url, location)

                    # Redirect loop detection
                    if next_url in visited_urls:
                        raise httpx.TooManyRedirects(f"Redirect loop detected: {next_url}")
                    visited_urls.add(current_url)

                    # Next hop will be evaluated by ScopeGate at the start of next loop iteration
                    current_url = next_url
                    if response.status_code in (302, 303):
                        method = "GET"
                        data = None
                        json_data = None
                    continue

                return response, decision
        finally:
            if should_close:
                client_cm.close()

    def get(self, url: str, **kwargs: Any) -> Tuple[httpx.Response, ScopeDecisionObject]:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Tuple[httpx.Response, ScopeDecisionObject]:
        return self.request("POST", url, **kwargs)
