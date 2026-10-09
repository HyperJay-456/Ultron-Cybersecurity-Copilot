export type EpistemicCertainty = 'OBSERVED' | 'DOCUMENTED' | 'DETERMINISTIC_DERIVATION';

export type StructuredCardType =
  | 'INVARIANT'
  | 'HYPOTHESIS'
  | 'EXPERIMENT'
  | 'APPROVAL'
  | 'EXECUTION'
  | 'OBSERVATION'
  | 'AUDIT'
  | 'NONE';

export interface ChatMessage {
  id: string;
  investigation_id: string;
  sender: 'user' | 'assistant' | 'system';
  content: string;
  structured_type: StructuredCardType;
  structured_data?: any;
  timestamp: string;
  sequence_number?: number;
  delivery_status?: 'sending' | 'delivered' | 'failed';
  cascade_trace_id?: string;
  model_name?: string;
  model_digest?: string;
  response_id?: string;
  status?: string;
}

export type ResponseStatus =
  | 'GENERATING'
  | 'CONTINUING'
  | 'COMPLETED'
  | 'USER_STOPPED'
  | 'MODEL_STOPPED'
  | 'TOKEN_LIMIT'
  | 'CONTEXT_LIMIT'
  | 'TIMEOUT'
  | 'ERROR';

export interface ResponseChunk {
  chunk_id: string;
  sequence_number: number;
  content: string;
  raw_content: string;
  content_hash: string;
  token_count: number;
  generation_time: number;
  stop_reason: string;
  created_at: string;
}

export interface ResponseVersion {
  version_id: string;
  response_id: string;
  version_number: number;
  content: string;
  model: string;
  status: ResponseStatus;
  created_at: string;
}

export interface ResponseSession {
  response_id: string;
  investigation_id: string;
  parent_message_id?: string;
  model: string;
  chunks: ResponseChunk[];
  cumulative_tokens: number;
  status: ResponseStatus;
  termination_reason?: string;
  final_content: string;
  started_at: string;
  completed_at?: string;
  active_version: number;
}

export interface InvestigationSummary {
  id: string;
  name: string;
  target_host: string;
  scope_status: 'ALLOWED' | 'DENY' | 'UNKNOWN';
  status: 'ACTIVE' | 'ARCHIVED';
  is_demo?: boolean;
  evidence_count: number;
  hypothesis_count: number;
  experiment_count: number;
  message_count?: number;
  last_activity: string;
}

export interface InvestigationDetail {
  id: string;
  name: string;
  target_host: string;
  scope_status: 'ALLOWED' | 'DENY' | 'UNKNOWN';
  status: string;
  is_demo?: boolean;
  evidence_count: number;
  hypothesis_count: number;
  messages: ChatMessage[];
  created_at: string;
  updated_at: string;
}

export interface CascadeStageTrace {
  stage_name: string;
  model_name?: string;
  model_digest?: string;
  status: string;
  latency_seconds: number;
  details: Record<string, any>;
}

export interface CascadeExecutionTrace {
  run_id: string;
  investigation_id?: string;
  user_message_id?: string;
  assistant_message_id?: string;
  timestamp: string;
  task_type: string;
  target_endpoint: string;
  stages: CascadeStageTrace[];
  overall_status: string;
  routing_decision?: string;
  escalated: boolean;
  handoff_provenance_hash?: string;
  total_latency_seconds: number;
  error_message?: string;
}

export interface SystemStatus {
  local_ai: string;
  ollama: string;
  evidence: string;
  vapt_rag: string;
  audit: string;
  active_model: string;
  cascade_mode?: string;
  execution_mode: string;
  gpu: {
    detected: boolean;
    name: string;
    driver?: string;
    vram_total?: string;
    vram_used?: string;
  };
  recent_traces?: CascadeExecutionTrace[];
  timestamp: string;
}

export interface EvidenceItem {
  fact_id: string;
  certainty: EpistemicCertainty;
  statement: string;
  source_tool: string;
  trust: string;
  raw_evidence_ref?: string;
  created_at?: string;
}

export interface SecurityInvariant {
  invariant_id: string;
  description: string;
  origin: string;
  confidence: string;
  derived_from?: string;
  created_at?: string;
}

export interface EvidenceGap {
  gap_id: string;
  target_asset: string;
  description: string;
  status: string;
  suggested_action: string;
}

export interface ExperimentObject {
  id: string;
  investigation_id: string;
  hypothesis_id?: number;
  category: string;
  action: string;
  target: string;
  asset_id: string;
  safety_level: 'READ_ONLY_SAFE' | 'STATE_CHANGING_REQUIRES_APPROVAL' | 'DESTRUCTIVE_ISOLATED_DATA';
  scope: string;
  grounding: string;
  polarity: string;
  status: string;
  approval_required: boolean;
  approval_id?: string | null;
  objective: string;
  supporting_observation: string;
  contradicting_observation: string;
  falsification_condition: string;
}

export interface TimelineStep {
  step: string;
  status: 'PASS' | 'FAIL' | 'BLOCKED' | 'SKIPPED';
  detail: string;
}

export interface ExecutionOutcome {
  experiment_id: string;
  status: string;
  success: boolean;
  timeline: TimelineStep[];
  observation?: {
    status_code: number;
    content_type: string;
    observation_type: string;
    summary: string;
    derived_epistemic_status: string;
  };
  hypothesis_state?: string;
  new_evidence?: any;
  error_message?: string;
}

export interface AuditRecord {
  timestamp: string;
  event_type: string;
  actor: string;
  subject_id: string;
  descriptor_digest?: string;
  previous_hash?: string;
  current_hash?: string;
  details?: any;
}

export interface InvestigationObservation {
  id: string;
  investigation_id: string;
  fact_id: string;
  asset_id: string;
  http_method: string;
  host: string;
  raw_path: string;
  normalized_path: string;
  response_status: number;
  request_headers: Record<string, string>;
  request_body: string;
  response_headers: Record<string, string>;
  response_body: string;
  statement: string;
  source_type: string;
  source_artifact?: string;
  researcher_note?: string;
  transaction_digest: string;
  redacted_secret_count: number;
  created_at: string;
}

export interface IngestionResult {
  imported_count: number;
  accepted_count: number;
  duplicate_count: number;
  out_of_scope_count: number;
  redacted_secret_count: number;
  parsing_failures: number;
  errors: string[];
  accepted_observations: InvestigationObservation[];
  observations_added?: number;
  duplicates?: number;
  out_of_scope?: Array<{ transaction?: number; host?: string; reason?: string }>;
  parse_errors?: string[];
}

export interface ImportTrafficPayload {
  format: 'har' | 'raw_http' | 'burp';
  content: string;
  filename?: string;
}

export interface ManualObservationPayload {
  method: string;
  host?: string;
  path: string;
  status_code: number;
  request_headers?: Record<string, string>;
  request_body?: string;
  response_headers?: Record<string, string>;
  response_body?: string;
  researcher_note?: string;
}

// ---------------------------------------------------------------------------
// M13 Full Security Assessment Workspace Types
// ---------------------------------------------------------------------------

export type AssessmentLifecycleState =
  | 'DRAFT'
  | 'AUTHORIZATION_PENDING'
  | 'AUTHORIZED'
  | 'SCOPE_DEFINED'
  | 'ASSESSMENT_ACTIVE'
  | 'ASSESSMENT_PAUSED'
  | 'REMEDIAL_HOLD'
  | 'REPORTING'
  | 'COMPLETED'
  | 'ARCHIVED'
  | 'REJECTED';

export interface AssessmentWorkflowStatus {
  authorization_valid: boolean;
  scope_defined: boolean;
  telemetry_ingested: boolean;
  attack_surface_mapped: boolean;
  hypotheses_evaluated: boolean;
  experiments_executed: boolean;
  findings_reviewed: boolean;
  report_generated: boolean;
  current_milestone: string;
}

export interface AssessmentSummary {
  assessment_id: string;
  organization: string;
  assessment_name: string;
  state: AssessmentLifecycleState;
  authorization_status: string;
  authorization_type?: string;
  created_at: string;
  updated_at: string;
  asset_count: number;
  observation_count: number;
  hypothesis_count: number;
  finding_count: number;
  verified_finding_count: number;
  last_activity_at?: string;
}

export interface AssessmentOverview {
  assessment_id: string;
  organization: string;
  assessment_name: string;
  state: AssessmentLifecycleState;
  authorization_id?: string;
  authorization_status: string;
  valid_from?: string;
  valid_until?: string;
  scope_policy_id?: string;
  in_scope_count: number;
  out_of_scope_count: number;
  asset_count: number;
  observation_count: number;
  hypothesis_count: number;
  evidence_gap_count: number;
  experiment_count: number;
  finding_count: number;
  verified_finding_count: number;
  workflow_status: AssessmentWorkflowStatus;
  created_at: string;
  updated_at: string;
  created_by: string;
}

export interface WorkspaceViewState {
  active_section: string;
  search_query: string;
  selected_asset_id?: string;
  selected_hypothesis_id?: string;
  selected_finding_id?: string;
  selected_artifact_id?: string;
  filter_severity?: string;
  filter_verification?: string;
  filter_scope?: string;
}

export interface AssessmentWorkspace {
  overview: AssessmentOverview;
  view_state: WorkspaceViewState;
  allowed_sections: string[];
  is_read_only: boolean;
  warning_banners: string[];
}

export interface AssessmentActivity {
  event_id: string;
  assessment_id: string;
  timestamp: string;
  actor: string;
  component: string;
  event_type: string;
  summary: string;
  details: Record<string, any>;
  authorization_state: string;
  scope_state: string;
  epistemic_state: string;
}

export interface GlobalSearchResultItem {
  entity_id: string;
  entity_type: string;
  title: string;
  assessment_id?: string;
  assessment_name?: string;
  snippet: string;
  provenance: Record<string, any>;
  url_target: string;
}

export interface AssetItem {
  asset_id: string;
  assessment_id: string;
  asset_type: string;
  canonical_identifier: string;
  parent_asset_id?: string;
  scope_status: 'IN_SCOPE' | 'OUT_OF_SCOPE' | 'UNKNOWN';
  tags: string[];
  discovered_at: string;
  discovery_method: string;
}

export interface FindingItem {
  finding_id: string;
  assessment_id: string;
  title: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFORMATIONAL';
  asset: string;
  affected_component: string;
  description: string;
  impact: string;
  evidence: string[];
  reproduction_reference: string;
  security_invariant: string;
  root_cause: string;
  remediation: string;
  references: string[];
  verification_status: 'UNVERIFIED' | 'EVIDENCE_REVIEW' | 'HUMAN_VERIFIED' | 'REJECTED' | 'DISPUTED';
  verified_by?: string;
  verified_at?: string;
  justification?: string;
}

export interface HypothesisItem {
  hypothesis_id: string;
  assessment_id: string;
  title: string;
  description: string;
  target_asset: string;
  epistemic_certainty: string;
  evidence_ids: string[];
  evidence_gaps: string[];
  state: string;
  author: string;
}

export interface ExperimentItem {
  experiment_id: string;
  hypothesis_id: string;
  objective: string;
  target_asset: string;
  steps: string[];
  expected_secure_result: string;
  expected_vulnerable_result: string;
  falsification_condition: string;
  negative_control: string;
  risk_level: string;
  status: string;
  approval_status: string;
}

export interface ArtifactItem {
  artifact_id: string;
  assessment_id: string;
  filename: string;
  sha256: string;
  byte_size: number;
  artifact_type: string;
  quarantine_status: 'CLEARED' | 'QUARANTINED' | 'PENDING';
  created_at?: string;
}


