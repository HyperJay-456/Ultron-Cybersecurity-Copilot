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

