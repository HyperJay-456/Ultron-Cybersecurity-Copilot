# Milestone M2.75: Deterministic State & Execution Engine Documentation

## 1. Overview & Operational Boundary
Milestone M2.75 extends the frozen Milestone M2 / Phase 11.6 cascade architecture with a deterministic execution and state management engine.

### Non-Goals (What M2.75 Is NOT)
- **NOT an autonomous crawler**: No recursive crawling or endpoint discovery.
- **NOT an autonomous scanner**: No automated fuzzing loops or vulnerability scanners.
- **NOT an exploit engine**: No autonomous exploitation or payload generation.
- **NOT a vulnerability confirmer**: Does not produce `VULNERABILITY_CONFIRMED`.
- **NOT an autonomous report submitter**: No external report dispatching.
- **NOT an LLM-controlled execution layer**: The LLM may propose experiments; deterministic gates alone govern whether and how an authorized experiment executes.

---

## 2. Supported State Model & Lifecycle Namespaces
To guarantee **zero collision** with hypothesis decisions, evidence states, and vulnerability taxonomy enums, all M2.75 lifecycle states are strictly namespaced:

### Credential Lifecycle (`CredentialLifecycleState`)
- `CRED_DISCOVERED`: Discovered token reference registered.
- `CRED_ACTIVE`: Valid, unexpired, and available for authorized execution.
- `CRED_EXPIRING`: Approaching expiration window.
- `CRED_EXPIRED`: Past expiration time; requires refresh.
- `CRED_ROTATED`: Replaced by a newer credential record.
- `CRED_REVOKED`: Invalidation signal received; unusable.
- `CRED_INVALID`: Malformed or failed validation.

### Session Lifecycle (`SessionLifecycleState`)
- `SESS_ACTIVE`: Active session with valid cookies.
- `SESS_EXPIRED`: Session timed out.
- `SESS_TERMINATED`: Explicitly closed or replaced.
- `SESS_INVALID`: Malformed session state.

### CSRF / Nonce Lifecycle (`CsrfLifecycleState`)
- `CSRF_DISCOVERED`: Token acquired from response or configuration.
- `CSRF_VALID`: Valid and eligible for single-use consumption.
- `CSRF_CONSUMED`: Atomically consumed; cannot be replayed.
- `CSRF_ROTATED`: Replaced by a rotated token.
- `CSRF_EXPIRED`: Timed out.
- `CSRF_INVALID`: Failed validation.

### Signing Key Lifecycle (`SigningLifecycleState`)
- `SIGN_KEY_ACTIVE`: Active key reference in vault.
- `SIGN_KEY_ROTATED`: Rotated signing key.
- `SIGN_KEY_EXPIRED`: Expired key.
- `SIGN_KEY_REVOKED`: Revoked key.

---

## 3. Ownership & Binding Invariants
Every credential, session, CSRF token, and signing key is cryptographically/logically bound to:
1. `identity_id`: The owning user/tenant (e.g., `user_a`).
2. `target_authority`: The allowed host (e.g., `api.target.com`).
3. `environment_context`: The target environment (e.g., `staging`).
4. `session_id`: (Where applicable) the bound cookie session.

### Cross-Identity & Cross-Target Rejection
Any attempt to:
- Use Identity A's credential for Identity B
- Use Identity A's CSRF token for Identity B
- Use Identity A's signing key for Identity B
- Use a staging credential against production
- Use a target X credential against target Y
- Use a session-bound CSRF token in a different session

fails closed immediately with `BLOCKED_AUTH_STATE` or `BLOCKED_CSRF` and records an immutable audit event.

---

## 4. Vault Integration & Secret Isolation
- `RedactionVault` remains the sole secret repository.
- State records, execution results, logs, and exception strings store strictly **typed placeholders** (e.g., `[REDACTED_JWT_1]`, `[REDACTED_CSRF_1]`, `[REDACTED_SECRET_1]`).
- Raw secrets are reversed from placeholders immediately before outbound transmission and are never persisted in execution records.

---

## 5. Exception & Secret Scrubbing Boundary
All exception paths (network errors, HTTP client errors, adapter exceptions) are scrubbed via `scrub_exception_text()` before logging or attaching to `ExecutionResult`:
- Authorization headers (`Bearer ...`, `Basic ...`)
- Cookie / Set-Cookie headers
- Sensitive URL query parameters (`?token=...`, `?api_key=...`, `?secret=...`, `?code=...`)
- Raw JWT strings
- Passwords and keys

---

## 6. Deterministic Authentication Adapters
All authentication flows are explicitly configured. Autonomous flow discovery, guessed endpoints, and LLM-generated auth requests are strictly prohibited.

### Supported Adapters
1. **`JwtRefreshAdapter`**: Bounded refresh via configured refresh endpoint using stored refresh token placeholder.
2. **`OAuthRefreshAdapter`**: Standard RFC 6749 refresh grant (`grant_type=refresh_token`).
3. **`CookieSessionAdapter`**: Re-authentication sequence via configured login endpoint.
4. **`ReauthenticationAdapter`**: Declared multi-step authentication sequence.

### Bounded Refresh & Retry Safety
- Fixed retry limit: `max_retries = 2`.
- On retry exhaustion: Raises `RetryExhaustionError`, failing closed with `BLOCKED_AUTH_STATE`.
- SSRF Defense: All outbound adapter requests route through `ScopedHttpClient` and `ScopeGate` (DNS TOCTOU, IP pinning, private range blocking, redirect scope, rate limiting).

---

## 7. Dynamic Request Signing & Signing Profiles
Signing is strictly controlled via registered `SigningProfile` configurations:
- **Canonical Request Format**: `METHOD\nNORMALIZED_PATH\nSORTED_QUERY\nSHA256(BODY)\nTIMESTAMP\nNONCE`.
- **HMAC-SHA256**: Generates signature using vault-resolved secret.
- **Freshness Window**: Timestamp must fall within `+/- timestamp_window_seconds` (default 300s); otherwise fails with `EXPIRED_TIMESTAMP`.
- **Replay Protection**: Nonce is atomically consumed in `DeterministicStateManager`; reuse fails with `REPLAYED_NONCE`.
- **Tamper Protection**: Any post-signing mutation of method, path, query, or body breaks signature verification.
- **Unsupported Profiles**: Fail closed with `UNSUPPORTED_SIGNING_FLOW`.

---

## 8. Human Approval Binding
Pre-execution human approval is mandatory for:
- `STATE_CHANGING_REQUIRES_APPROVAL`
- `DESTRUCTIVE_ISOLATED_DATA`

### Cryptographic Binding
Approval is bound to an immutable SHA-256 digest of the canonical `ExecutionDescriptor`:
- `experiment_id`
- `identity_id`
- `environment_context`
- `target_authority`
- `destination`
- `resolved_ip`
- `http_method`
- `normalized_route`
- `normalized_query`
- `request_body_digest`
- `safety_classification`
- `affected_resource`
- `expected_state_transition`

The digest is recomputed immediately prior to transmission. Any mismatch, missing approval, or expired approval returns `BLOCKED_APPROVAL`.

---

## 9. Mandatory 14-Step Execution Pipeline
The execution pipeline in `DeterministicExecutionEngine` enforces the following strict order:
1. **Live Execution Mode Check**: If `live_execution_enabled == False` and no mock transport is configured -> `BLOCKED_EXECUTION_MODE`.
2. **Build ExecutionDescriptor**: Normalizes parameters and computes initial digest.
3. **Initial Scope Gate Evaluation**: Validates destination authority and resolves/pins IP.
4. **Human Approval Verification**: Checks approval before any state mutation or token consumption.
5. **Pre-flight TTL and Token Validation**: Checks token presence and freshness via `DeterministicTTLValidator`.
6. **Bounded Auth Refresh**: Executes adapter refresh if expired.
7. **Post-Refresh Ownership Revalidation**: Ensures refreshed token still belongs to expected identity and target.
8. **CSRF Validation & Atomic Consumption**: Checks single-use, freshness, and marks `CONSUMED`. Injects header.
9. **Request Signing**: Generates HMAC signature if profile is registered.
10. **Final TOCTOU Descriptor & Scope Re-check**: Verifies descriptor digest and destination immediately before transmission.
11. **Rate-Limit Gate**: Enforces inter-request pacing via `ScopedHttpClient`.
12. **Controlled HTTP Execution**: Dispatches request via `ScopedHttpClient` or deterministic mock transport.
13. **Redact & Package Raw Observation Evidence**: Redacts response headers and body, packaging evidence as `OBSERVED`.
14. **Audit Logging**: Emits sanitized provenance record via `AuditLogger`.

---

## 10. Execution Result Taxonomy
Execution outcomes are classified into structured, unambiguous statuses:
- `EXECUTED`: Experiment executed and observation captured.
- `BLOCKED_SCOPE`: Destination or redirect outside authorized scope.
- `BLOCKED_SAFETY`: Disallowed technique or safety violation.
- `BLOCKED_APPROVAL`: Missing, expired, or mismatched human approval.
- `BLOCKED_AUTH_STATE`: Cross-identity, cross-target, or invalid credential state.
- `BLOCKED_TTL`: Expired token with failed or unavailable refresh.
- `BLOCKED_CSRF`: Replayed, expired, or cross-identity CSRF token.
- `BLOCKED_RATE_LIMIT`: Exceeded request rate limit.
- `UNSUPPORTED_AUTH_FLOW`: Unconfigured or unhandled authentication protocol.
- `UNSUPPORTED_SIGNING_FLOW`: Unconfigured or unhandled request signing scheme.
- `BLOCKED_EXECUTION_MODE`: Live execution disabled (default-off).
- `EXECUTION_ERROR`: Scrubbed network or library execution error.

---

## 11. Concurrency Model & Deployment Scope
- **Supported Deployment Model**: **Single-Process, Multi-Threaded**.
- **Concurrency Mechanism**: `threading.RLock()` protects all atomic check-and-transition sequences in `DeterministicStateManager`.
- **Atomicity Guarantees**:
  - Concurrent CSRF consumption: Exactly 1 thread succeeds; all competing threads receive `CSRF_ALREADY_CONSUMED`.
  - Concurrent signing nonce: Exactly 1 thread succeeds; all competing threads receive `SIGNING_NONCE_REPLAYED`.
  - Concurrent credential refresh: Serialized atomically.
- **Multi-Process Limitation**: If multi-process deployment is required in future milestones (e.g. Celery / multiprocess workers), atomic state management must be migrated to SQLite transactions or an external transactional store.

---

## 12. Observation Feedback Invariant
- The execution engine strictly emits raw interaction observations with `epistemic_status = "OBSERVED"`.
- It **NEVER** directly emits `VULNERABILITY_CONFIRMED`.
- The existing Phase 11.6 interaction-enrichment pipeline (`StructuralDiffEngine` + `InteractionEvidenceEnricher`) processes observations into structured facts for LLM reasoning.
