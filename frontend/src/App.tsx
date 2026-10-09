import React, { useEffect, useState } from 'react';
import {
  approveExperiment,
  createInvestigation,
  deleteInvestigation,
  executeExperiment,
  fetchInvestigation,
  fetchInvestigations,
  fetchStatus,
  loadDemoFixture,
  rejectExperiment,
  renameInvestigation,
  sendMessage,
  validateExperiment,
} from './api';
import { Composer } from './components/Composer';
import { ContextDrawer } from './components/ContextDrawer';
import { ConversationView } from './components/ConversationView';
import { InvestigationHeader } from './components/InvestigationHeader';
import { NewInvestigationModal } from './components/NewInvestigationModal';
import { Sidebar } from './components/Sidebar';
import { SystemStatusModal } from './components/SystemStatusModal';
import { ImportTrafficModal } from './components/ImportTrafficModal';
import { AddObservationModal } from './components/AddObservationModal';
import { WorkspaceShell } from './components/workspace/WorkspaceShell';
import type { ChatMessage, IngestionResult, InvestigationDetail, InvestigationSummary, SystemStatus } from './types';

export const App: React.FC = () => {
  const getInitialAppMode = (): 'workspace' | 'copilot' => {
    const path = window.location.pathname.toLowerCase();
    const hash = window.location.hash.toLowerCase();
    const search = window.location.search.toLowerCase();
    if (path.includes('/workspace') || path.includes('/assessment') || hash.includes('workspace') || search.includes('mode=workspace')) {
      return 'workspace';
    }
    return 'copilot';
  };

  const [appMode, setAppMode] = useState<'workspace' | 'copilot'>(getInitialAppMode);
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<InvestigationDetail | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);

  const [loadingMessage, setLoadingMessage] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState('evidence');
  const [showStatusModal, setShowStatusModal] = useState(false);
  const [showNewModal, setShowNewModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showAddObsModal, setShowAddObsModal] = useState(false);
  const [importSummary, setImportSummary] = useState<IngestionResult | null>(null);

  useEffect(() => {
    initWorkspace();
  }, []);

  const initWorkspace = async () => {
    try {
      const [invs, sysStatus] = await Promise.all([
        fetchInvestigations(),
        fetchStatus().catch(() => null),
      ]);
      setInvestigations(invs);
      if (sysStatus) setStatus(sysStatus);

      // Check URL route for direct investigation navigation
      const pathParts = window.location.pathname.split('/');
      const invIndex = pathParts.indexOf('investigations');
      if (invIndex !== -1 && pathParts[invIndex + 1]) {
        selectInvestigation(pathParts[invIndex + 1]);
      } else if (invs && invs.length > 0 && !activeId) {
        // Auto-select first existing investigation so Copilot conversation is immediately ready
        selectInvestigation(invs[0].id);
      }
    } catch (err) {
      console.error('Failed to initialize workspace:', err);
    }
  };

  const selectInvestigation = async (id: string) => {
    setActiveId(id);
    setImportSummary(null);
    try {
      const data = await fetchInvestigation(id);
      setDetail(data);
    } catch (err) {
      console.error(`Failed to load investigation ${id}:`, err);
    }
  };

  const handleImportSuccess = async (result: IngestionResult) => {
    setImportSummary(result);
    if (activeId) {
      const updated = await fetchInvestigation(activeId);
      setDetail(updated);
      fetchInvestigations().then(setInvestigations).catch(() => {});
    }
  };

  const handleAddObservationSuccess = async () => {
    if (activeId) {
      const updated = await fetchInvestigation(activeId);
      setDetail(updated);
      fetchInvestigations().then(setInvestigations).catch(() => {});
    }
  };

  const handleStartAnalysis = async () => {
    await handleSendMessage("Analyze target traffic for security invariants, derived workflows, and evidence gaps.");
  };

  const handleViewEvidence = () => {
    openDrawerWithTab('evidence');
  };

  /**
   * Reconcile local conversation state with server conversation state.
   * Preserves pending or failed local user messages while preventing duplicates.
   */
  const reconcileMessages = (currentMessages: ChatMessage[], serverMessages: ChatMessage[]): ChatMessage[] => {
    const serverIds = new Set(serverMessages.map((m) => m.id));
    const serverUserSignatures = new Set(
      serverMessages
        .filter((m) => m.sender === 'user')
        .map((m) => m.content.trim())
    );

    const unconfirmedLocal = currentMessages.filter(
      (m) =>
        (m.delivery_status === 'sending' || m.delivery_status === 'failed') &&
        !serverIds.has(m.id) &&
        !serverUserSignatures.has(m.content.trim())
    );

    return [...serverMessages, ...unconfirmedLocal];
  };

  const handleSendMessage = async (content: string) => {
    if (!activeId) return;

    // 1. Generate stable client-side ID for optimistic rendering
    const clientMsgId = `USR-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`;
    const optimisticUserMsg: ChatMessage = {
      id: clientMsgId,
      investigation_id: activeId,
      sender: 'user',
      content,
      structured_type: 'NONE',
      timestamp: new Date().toISOString(),
      delivery_status: 'sending',
    };

    // 2. Immediately append user message to local state (immutable update)
    setDetail((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        messages: [...prev.messages, optimisticUserMsg],
      };
    });

    // 3. Set loading state to show processing/thinking indicator
    setLoadingMessage(true);

    try {
      // 4. Perform API request to post message
      const responseMessages = await sendMessage(activeId, content, clientMsgId);

      // 5. Assistant response received: mark user message delivered and append assistant response
      setDetail((prev) => {
        if (!prev) return prev;

        const updatedMessages = prev.messages.map((m) =>
          m.id === clientMsgId ? { ...m, delivery_status: 'delivered' as const } : m
        );

        // Deduplicate incoming messages
        const toAdd = responseMessages.filter((inc) => {
          if (updatedMessages.some((m) => m.id === inc.id)) return false;
          if (inc.sender === 'user' && inc.content.trim() === content.trim()) return false;
          return true;
        });

        return {
          ...prev,
          messages: [...updatedMessages, ...toAdd],
        };
      });

      // Refresh list metadata in background
      fetchInvestigations().then(setInvestigations).catch(() => {});
    } catch (err: any) {
      // 6. On failure: mark user message as failed (retains message in conversation with retry option)
      setDetail((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          messages: prev.messages.map((m) =>
            m.id === clientMsgId ? { ...m, delivery_status: 'failed' as const } : m
          ),
        };
      });
      console.error('Failed to send message:', err);
    } finally {
      setLoadingMessage(false);
    }
  };

  const handleRetryMessage = async (content: string, failedId: string) => {
    if (!activeId) return;
    setDetail((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        messages: prev.messages.filter((m) => m.id !== failedId),
      };
    });
    await handleSendMessage(content);
  };

  const handleRenameInvestigation = async (newName: string) => {
    if (!activeId) return;
    try {
      const updated = await renameInvestigation(activeId, newName);
      setInvestigations((prev) => prev.map((inv) => (inv.id === activeId ? updated : inv)));
      setDetail((prev) => (prev ? { ...prev, name: updated.name } : prev));
    } catch (err: any) {
      alert(`Failed to rename investigation: ${err.message}`);
    }
  };

  const handleDeleteInvestigation = async () => {
    if (!activeId) return;
    if (!window.confirm('Delete this investigation and its conversation messages? Canonical evidence remains preserved.')) {
      return;
    }
    try {
      await deleteInvestigation(activeId);
      setInvestigations((prev) => prev.filter((inv) => inv.id !== activeId));
      setActiveId(null);
      setDetail(null);
    } catch (err: any) {
      alert(`Failed to delete investigation: ${err.message}`);
    }
  };

  const handleCreateInvestigation = async (name: string, targetHost: string) => {
    const newInv = await createInvestigation(name, targetHost);
    setInvestigations((prev) => [newInv, ...prev]);
    selectInvestigation(newInv.id);
  };

  const handleLoadDemo = async () => {
    try {
      const demoInv = await loadDemoFixture();
      const updatedList = await fetchInvestigations();
      setInvestigations(updatedList);
      selectInvestigation(demoInv.id);
    } catch (err: any) {
      alert(`Failed to load demo fixture: ${err.message}`);
    }
  };

  const handleValidateExperiment = async (expId: string) => {
    return await validateExperiment(expId);
  };

  const handleApproveExperiment = async (
    expId: string,
    actor: string,
    ack: boolean,
    notes: string
  ) => {
    const res = await approveExperiment(expId, actor, ack, notes);
    if (activeId) {
      const updated = await fetchInvestigation(activeId);
      setDetail((prev) => {
        if (!prev || prev.id !== updated.id) return updated;
        return {
          ...updated,
          messages: reconcileMessages(prev.messages, updated.messages),
        };
      });
    }
    return res;
  };

  const handleRejectExperiment = async (expId: string) => {
    const res = await rejectExperiment(expId, 'authorized_security_lead', 'Rejected by researcher in workspace.');
    if (activeId) {
      const updated = await fetchInvestigation(activeId);
      setDetail((prev) => {
        if (!prev || prev.id !== updated.id) return updated;
        return {
          ...updated,
          messages: reconcileMessages(prev.messages, updated.messages),
        };
      });
    }
    return res;
  };

  const handleExecuteExperiment = async (expId: string) => {
    const outcome = await executeExperiment(expId);
    if (activeId) {
      const updated = await fetchInvestigation(activeId);
      setDetail((prev) => {
        if (!prev || prev.id !== updated.id) return updated;
        return {
          ...updated,
          messages: reconcileMessages(prev.messages, updated.messages),
        };
      });
      fetchInvestigations().then(setInvestigations).catch(() => {});
    }
    return outcome;
  };

  const openDrawerWithTab = (tab: string) => {
    setDrawerTab(tab);
    setDrawerOpen(true);
  };

  if (appMode === 'workspace') {
    return <WorkspaceShell onBackToCopilot={() => setAppMode('copilot')} />;
  }

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      {/* Sidebar */}
      <Sidebar
        investigations={investigations}
        activeId={activeId}
        onSelect={selectInvestigation}
        onNewInvestigation={() => setShowNewModal(true)}
        onLoadDemo={handleLoadDemo}
        onOpenSystemStatus={() => setShowStatusModal(true)}
        systemStatusReady={status?.local_ai === 'READY'}
        onOpenWorkspace={() => setAppMode('workspace')}
      />

      {/* Main Workspace Column */}
      <main
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          overflow: 'hidden',
          backgroundColor: 'var(--bg-app)',
          position: 'relative',
        }}
      >
        {detail ? (
          <>
            <InvestigationHeader
              name={detail.name}
              targetHost={detail.target_host}
              scopeStatus={detail.scope_status}
              isDemo={detail.is_demo}
              evidenceCount={detail.evidence_count}
              hypothesisCount={detail.hypothesis_count}
              activeModel={status?.active_model || 'qwen2.5-coder:7b'}
              onOpenDrawer={openDrawerWithTab}
              onOpenImport={() => setShowImportModal(true)}
              onOpenAddObservation={() => setShowAddObsModal(true)}
              onRename={handleRenameInvestigation}
              onDelete={handleDeleteInvestigation}
            />

            <ConversationView
              messages={detail.messages}
              loading={loadingMessage}
              evidenceCount={detail.evidence_count}
              importSummary={importSummary}
              targetHost={detail.target_host}
              onOpenImport={() => setShowImportModal(true)}
              onOpenAddObservation={() => setShowAddObsModal(true)}
              onViewEvidence={handleViewEvidence}
              onStartAnalysis={handleStartAnalysis}
              onRetryMessage={handleRetryMessage}
              onValidateExperiment={handleValidateExperiment}
              onApproveExperiment={handleApproveExperiment}
              onRejectExperiment={handleRejectExperiment}
              onExecuteExperiment={handleExecuteExperiment}
              onOpenDrawer={openDrawerWithTab}
              onSendFollowUp={handleSendMessage}
            />

            <Composer
              onSend={handleSendMessage}
              loading={loadingMessage}
              hasMessages={Boolean(detail.messages && detail.messages.length > 0)}
            />
          </>
        ) : (
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '40px 24px',
              maxWidth: '540px',
              margin: '0 auto',
              textAlign: 'center',
            }}
          >
            <h1
              style={{
                fontSize: '24px',
                fontWeight: 500,
                color: 'var(--text-primary)',
                letterSpacing: '-0.015em',
                marginBottom: '10px',
              }}
            >
              What are you investigating?
            </h1>

            <p
              style={{
                fontSize: '14px',
                color: 'var(--text-secondary)',
                marginBottom: '28px',
                lineHeight: 1.6,
              }}
            >
              Select an ongoing investigation from the sidebar, create a new one, or explore the local BOLA fixture.
            </p>

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'center', marginBottom: '32px' }}>
              <button
                onClick={() => setShowNewModal(true)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '9px 18px',
                  backgroundColor: 'var(--accent-primary)',
                  color: '#FFFFFF',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '13.5px',
                  fontWeight: 500,
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                <span>+</span>
                <span>New investigation</span>
              </button>

              <button
                onClick={handleLoadDemo}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '9px 16px',
                  backgroundColor: 'transparent',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '13px',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--bg-surface)';
                  e.currentTarget.style.color = 'var(--text-primary)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                  e.currentTarget.style.color = 'var(--text-secondary)';
                }}
              >
                <span>Load demo fixture</span>
              </button>
            </div>

            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '12px',
                color: 'var(--text-muted)',
              }}
            >
              <span
                style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  backgroundColor: status?.local_ai === 'READY' ? 'var(--status-success)' : '#B8860B',
                }}
              />
              <span>Local AI: {status?.active_model || 'Connecting...'}</span>
              <span>·</span>
              <span>{status?.execution_mode || 'SAFE_LOCAL_SIMULATION'}</span>
            </div>
          </div>
        )}
      </main>

      {/* Slide-in Context Drawer */}
      {drawerOpen && activeId && (
        <ContextDrawer
          investigationId={activeId}
          initialTab={drawerTab}
          onClose={() => setDrawerOpen(false)}
          onOpenImport={() => setShowImportModal(true)}
          onOpenAddObservation={() => setShowAddObsModal(true)}
        />
      )}

      {/* System Status Modal */}
      {showStatusModal && (
        <SystemStatusModal
          status={status}
          onClose={() => setShowStatusModal(false)}
        />
      )}

      {/* New Investigation Modal */}
      {showNewModal && (
        <NewInvestigationModal
          onCreate={handleCreateInvestigation}
          onClose={() => setShowNewModal(false)}
        />
      )}

      {/* Import Traffic Modal */}
      {showImportModal && activeId && detail && (
        <ImportTrafficModal
          investigationId={activeId}
          targetHost={detail.target_host}
          onClose={() => setShowImportModal(false)}
          onImportComplete={handleImportSuccess}
          onViewEvidence={handleViewEvidence}
          onStartAnalysis={handleStartAnalysis}
        />
      )}

      {/* Add Observation Modal */}
      {showAddObsModal && activeId && detail && (
        <AddObservationModal
          investigationId={activeId}
          targetHost={detail.target_host}
          onClose={() => setShowAddObsModal(false)}
          onObservationAdded={handleAddObservationSuccess}
          onViewEvidence={handleViewEvidence}
          onStartAnalysis={handleStartAnalysis}
        />
      )}
    </div>
  );
};

export default App;
