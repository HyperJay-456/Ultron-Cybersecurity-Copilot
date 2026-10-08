import type {
  AuditRecord,
  ChatMessage,
  EvidenceGap,
  EvidenceItem,
  ExecutionOutcome,
  ExperimentObject,
  ImportTrafficPayload,
  IngestionResult,
  InvestigationDetail,
  InvestigationObservation,
  InvestigationSummary,
  ManualObservationPayload,
  SecurityInvariant,
  SystemStatus,
} from './types';

const BASE_URL = '/api';

export async function fetchStatus(): Promise<SystemStatus> {
  const res = await fetch(`${BASE_URL}/status`);
  if (!res.ok) throw new Error(`Failed to fetch system status: ${res.statusText}`);
  return res.json();
}

export async function fetchInvestigations(searchQuery?: string): Promise<InvestigationSummary[]> {
  const url = searchQuery
    ? `${BASE_URL}/investigations?q=${encodeURIComponent(searchQuery)}`
    : `${BASE_URL}/investigations`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch investigations: ${res.statusText}`);
  return res.json();
}

export async function fetchInvestigation(id: string): Promise<InvestigationDetail> {
  const res = await fetch(`${BASE_URL}/investigations/${id}`);
  if (!res.ok) throw new Error(`Failed to fetch investigation ${id}: ${res.statusText}`);
  return res.json();
}

export async function renameInvestigation(id: string, name: string): Promise<InvestigationSummary> {
  const res = await fetch(`${BASE_URL}/investigations/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringify({ name }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to rename investigation: ${res.statusText}`);
  }
  return res.json();
}

export async function deleteInvestigation(id: string): Promise<{ success: boolean; id: string }> {
  const res = await fetch(`${BASE_URL}/investigations/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to delete investigation: ${res.statusText}`);
  }
  return res.json();
}

export async function createInvestigation(name: string, target_host: string): Promise<InvestigationSummary> {
  const res = await fetch(`${BASE_URL}/investigations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringify({ name, target_host }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to create investigation: ${res.statusText}`);
  }
  return res.json();
}

export async function sendMessage(inv_id: string, content: string, clientMsgId?: string): Promise<ChatMessage[]> {
  const res = await fetch(`${BASE_URL}/investigations/${inv_id}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringify({ content, client_msg_id: clientMsgId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to send message: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchEvidence(inv_id: string): Promise<EvidenceItem[]> {
  const res = await fetch(`${BASE_URL}/investigations/${inv_id}/evidence`);
  if (!res.ok) throw new Error(`Failed to fetch evidence: ${res.statusText}`);
  return res.json();
}

export async function fetchApplicationModel(inv_id: string): Promise<any> {
  const res = await fetch(`${BASE_URL}/investigations/${inv_id}/model`);
  if (!res.ok) throw new Error(`Failed to fetch application model: ${res.statusText}`);
  return res.json();
}

export async function fetchInvariants(inv_id: string): Promise<SecurityInvariant[]> {
  const res = await fetch(`${BASE_URL}/investigations/${inv_id}/invariants`);
  if (!res.ok) throw new Error(`Failed to fetch invariants: ${res.statusText}`);
  return res.json();
}

export async function fetchGaps(inv_id: string): Promise<EvidenceGap[]> {
  const res = await fetch(`${BASE_URL}/investigations/${inv_id}/gaps`);
  if (!res.ok) throw new Error(`Failed to fetch evidence gaps: ${res.statusText}`);
  return res.json();
}

export async function fetchExperiments(inv_id: string): Promise<ExperimentObject[]> {
  const res = await fetch(`${BASE_URL}/investigations/${inv_id}/experiments`);
  if (!res.ok) throw new Error(`Failed to fetch experiments: ${res.statusText}`);
  return res.json();
}

export async function validateExperiment(exp_id: string): Promise<any> {
  const res = await fetch(`${BASE_URL}/experiments/${exp_id}/validate`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Failed to validate experiment: ${res.statusText}`);
  return res.json();
}

export async function approveExperiment(
  exp_id: string,
  actor: string,
  safety_acknowledged: boolean,
  notes?: string
): Promise<any> {
  const res = await fetch(`${BASE_URL}/experiments/${exp_id}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringify({ actor, safety_acknowledged, notes }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Approval failed: ${res.statusText}`);
  }
  return res.json();
}

export async function rejectExperiment(exp_id: string, actor: string, reason: string): Promise<any> {
  const res = await fetch(`${BASE_URL}/experiments/${exp_id}/reject?actor=${encodeURIComponent(actor)}&reason=${encodeURIComponent(reason)}`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Rejection failed: ${res.statusText}`);
  return res.json();
}

export async function executeExperiment(exp_id: string): Promise<ExecutionOutcome> {
  const res = await fetch(`${BASE_URL}/experiments/${exp_id}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringify({ safe_simulation: true }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Execution failed: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchAuditLog(limit = 50): Promise<AuditRecord[]> {
  const res = await fetch(`${BASE_URL}/audit?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed to fetch audit log: ${res.statusText}`);
  return res.json();
}

export async function loadDemoFixture(): Promise<InvestigationSummary> {
  const res = await fetch(`${BASE_URL}/demo/load`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Failed to load demo fixture: ${res.statusText}`);
  return res.json();
}

export async function fetchCascadeTraces(limit = 10): Promise<any[]> {
  const res = await fetch(`${BASE_URL}/system/cascade-trace?limit=${limit}`);
  if (!res.ok) throw new Error(`Failed to fetch cascade traces: ${res.statusText}`);
  return res.json();
}

export async function fetchCascadeTrace(traceId: string): Promise<any> {
  const res = await fetch(`${BASE_URL}/cascade-traces/${encodeURIComponent(traceId)}`);
  if (!res.ok) throw new Error(`Failed to fetch trace ${traceId}: ${res.statusText}`);
  return res.json();
}

export async function fetchMessageTrace(invId: string, messageId: string): Promise<any> {
  const res = await fetch(`${BASE_URL}/investigations/${encodeURIComponent(invId)}/messages/${encodeURIComponent(messageId)}/trace`);
  if (!res.ok) throw new Error(`Failed to fetch message trace: ${res.statusText}`);
  return res.json();
}

export async function importTraffic(invId: string, payload: ImportTrafficPayload): Promise<IngestionResult> {
  const res = await fetch(`${BASE_URL}/investigations/${encodeURIComponent(invId)}/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Import failed: ${res.statusText}`);
  }
  return res.json();
}

export async function addObservation(invId: string, payload: ManualObservationPayload): Promise<IngestionResult> {
  const res = await fetch(`${BASE_URL}/investigations/${encodeURIComponent(invId)}/observations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: jsonStringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to add observation: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchObservationDetail(invId: string, obsId: string): Promise<InvestigationObservation> {
  const res = await fetch(`${BASE_URL}/investigations/${encodeURIComponent(invId)}/evidence/${encodeURIComponent(obsId)}`);
  if (!res.ok) throw new Error(`Failed to fetch observation: ${res.statusText}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// M11.5 Long Response API Methods
// ---------------------------------------------------------------------------

export async function fetchResponseSession(responseId: string): Promise<any> {
  const res = await fetch(`${BASE_URL}/responses/${encodeURIComponent(responseId)}`);
  if (!res.ok) throw new Error(`Failed to fetch response: ${res.statusText}`);
  return res.json();
}

export async function fetchResponseChunks(responseId: string): Promise<any[]> {
  const res = await fetch(`${BASE_URL}/responses/${encodeURIComponent(responseId)}/chunks`);
  if (!res.ok) throw new Error(`Failed to fetch response chunks: ${res.statusText}`);
  return res.json();
}

export async function fetchResponseVersions(responseId: string): Promise<any[]> {
  const res = await fetch(`${BASE_URL}/responses/${encodeURIComponent(responseId)}/versions`);
  if (!res.ok) throw new Error(`Failed to fetch response versions: ${res.statusText}`);
  return res.json();
}

export async function stopResponseGeneration(responseId: string, reason?: string): Promise<{ stopped: boolean; response_id: string }> {
  const res = await fetch(`${BASE_URL}/responses/${encodeURIComponent(responseId)}/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: reason || 'User requested stop' }),
  });
  if (!res.ok) throw new Error(`Failed to stop response: ${res.statusText}`);
  return res.json();
}

export async function continueResponse(responseId: string, directive?: string): Promise<any> {
  const res = await fetch(`${BASE_URL}/responses/${encodeURIComponent(responseId)}/continue`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ custom_directive: directive }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to continue response: ${res.statusText}`);
  }
  return res.json();
}

export async function regenerateResponse(responseId: string, temperature: number = 0.7): Promise<any> {
  const res = await fetch(`${BASE_URL}/responses/${encodeURIComponent(responseId)}/regenerate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ temperature }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to regenerate response: ${res.statusText}`);
  }
  return res.json();
}

export async function performResponseAction(responseId: string, action: string, detail?: string): Promise<any> {
  const res = await fetch(`${BASE_URL}/responses/${encodeURIComponent(responseId)}/actions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, detail }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to perform response action: ${res.statusText}`);
  }
  return res.json();
}

export async function exportResponse(responseId: string, format: 'markdown' | 'txt' = 'markdown'): Promise<{ response_id: string; format: string; content: string }> {
  const res = await fetch(`${BASE_URL}/responses/${encodeURIComponent(responseId)}/export?format=${format}`);
  if (!res.ok) throw new Error(`Failed to export response: ${res.statusText}`);
  return res.json();
}

export async function fetchResponseMetrics(): Promise<any> {
  const res = await fetch(`${BASE_URL}/responses/metrics`);
  if (!res.ok) throw new Error(`Failed to fetch response metrics: ${res.statusText}`);
  return res.json();
}

function jsonStringify(obj: any): string {
  return JSON.stringify(obj);
}


