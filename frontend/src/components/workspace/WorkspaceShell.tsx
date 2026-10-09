import React, { useState, useEffect } from 'react';
import {
  fetchAssessments,
  fetchAssessmentWorkspace,
  fetchAssessmentOverview,
} from '../../api';
import type {
  AssessmentSummary,
  AssessmentWorkspace,
} from '../../types';
import { WorkspaceHeader } from './WorkspaceHeader';
import { AssessmentSwitcherModal } from './AssessmentSwitcherModal';
import { CreateAssessmentModal } from './CreateAssessmentModal';
import { GlobalSearchModal } from './GlobalSearchModal';

// 12 Functional Tab Views
import { OverviewTab } from './tabs/OverviewTab';
import { ScopeAssetsTab } from './tabs/ScopeAssetsTab';
import { AttackSurfaceTab } from './tabs/AttackSurfaceTab';
import { ArtifactsTab } from './tabs/ArtifactsTab';
import { ResearchTab } from './tabs/ResearchTab';
import { HypothesesTab } from './tabs/HypothesesTab';
import { EvidenceTab } from './tabs/EvidenceTab';
import { ExperimentsTab } from './tabs/ExperimentsTab';
import { FindingsReviewTab } from './tabs/FindingsReviewTab';
import { ReportsTab } from './tabs/ReportsTab';
import { MemoryKnowledgeTab } from './tabs/MemoryKnowledgeTab';
import { ActivityAuditTab } from './tabs/ActivityAuditTab';

interface WorkspaceShellProps {
  onBackToCopilot?: () => void;
}

export const WorkspaceShell: React.FC<WorkspaceShellProps> = ({ onBackToCopilot }) => {
  const [assessments, setAssessments] = useState<AssessmentSummary[]>([]);
  const [activeAssessmentId, setActiveAssessmentId] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<AssessmentWorkspace | null>(null);
  const [activeSection, setActiveSection] = useState<string>('overview');
  const [loading, setLoading] = useState<boolean>(true);

  // Modals
  const [showSwitcher, setShowSwitcher] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showSearchModal, setShowSearchModal] = useState(false);

  useEffect(() => {
    initWorkspace();
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setShowSearchModal((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const initWorkspace = async () => {
    setLoading(true);
    try {
      const list = await fetchAssessments();
      setAssessments(list);
      if (list.length > 0) {
        selectAssessment(list[0].assessment_id);
      } else {
        setLoading(false);
      }
    } catch (err) {
      console.error('Failed to load assessment list:', err);
      setLoading(false);
    }
  };

  const selectAssessment = async (aid: string) => {
    setActiveAssessmentId(aid);
    setLoading(true);
    try {
      const ws = await fetchAssessmentWorkspace(aid);
      setWorkspace(ws);
      if (ws.view_state && ws.view_state.active_section) {
        setActiveSection(ws.view_state.active_section);
      }
    } catch (err) {
      console.error(`Failed to load workspace for ${aid}:`, err);
    } finally {
      setLoading(false);
    }
  };

  const refreshOverview = async () => {
    if (!activeAssessmentId) return;
    try {
      const [ov, list] = await Promise.all([
        fetchAssessmentOverview(activeAssessmentId),
        fetchAssessments(),
      ]);
      setAssessments(list);
      if (workspace) {
        setWorkspace({ ...workspace, overview: ov });
      }
    } catch (err) {
      console.error('Failed to refresh overview:', err);
    }
  };

  const navItems = [
    { id: 'overview', label: '1. Overview', icon: '📊' },
    { id: 'scope_assets', label: '2. Scope & Assets', icon: '🎯' },
    { id: 'attack_surface', label: '3. Attack Surface', icon: '🌐' },
    { id: 'artifacts', label: '4. Artifacts Lab', icon: '📦' },
    { id: 'research', label: '5. Research & Q&A', icon: '💡' },
    { id: 'hypotheses', label: '6. Hypotheses & Gaps', icon: '❓' },
    { id: 'evidence', label: '7. Evidence & Lineage', icon: '🔍' },
    { id: 'experiments', label: '8. Controlled Experiments', icon: '🧪' },
    { id: 'findings_review', label: '9. Findings & Review', icon: '⚖️' },
    { id: 'reports', label: '10. Report Center', icon: '📄' },
    { id: 'memory_knowledge', label: '11. Research Memory', icon: '🧠' },
    { id: 'activity_audit', label: '12. Audit Timeline', icon: '📜' },
  ];

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      width: '100vw',
      background: 'var(--bg-app)',
      color: 'var(--text-primary)',
      overflow: 'hidden',
    }}>
      {/* Top Application Bar */}
      <div style={{
        padding: '8px 20px',
        borderBottom: '1px solid var(--border-subtle)',
        background: 'var(--bg-sidebar)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        fontSize: '12px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontWeight: 700, letterSpacing: '-0.02em', fontSize: '13px' }}>
            BUG BOUNTY AI — M13 UNIFIED WORKSPACE
          </span>
          <span style={{ color: 'var(--text-muted)' }}>|</span>
          <span style={{ color: 'var(--text-secondary)' }}>Full Lifecycle Security Research</span>
        </div>
        {onBackToCopilot && (
          <button
            onClick={onBackToCopilot}
            style={{
              padding: '4px 10px',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              fontSize: '11px',
              fontWeight: 600,
            }}
          >
            ← Switch to Copilot Investigations
          </button>
        )}
      </div>

      {/* Header */}
      <WorkspaceHeader
        overview={workspace?.overview || null}
        onOpenSwitcher={() => setShowSwitcher(true)}
        onOpenSearch={() => setShowSearchModal(true)}
        onRefresh={refreshOverview}
      />

      {/* Main Body: 12-Section Sidebar + Tab View */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Navigation Sidebar */}
        <aside style={{
          width: '240px',
          background: 'var(--bg-sidebar)',
          borderRight: '1px solid var(--border-subtle)',
          padding: '12px 8px',
          display: 'flex',
          flexDirection: 'column',
          gap: '2px',
          overflowY: 'auto',
        }}>
          <div style={{
            fontSize: '11px',
            fontWeight: 700,
            textTransform: 'uppercase',
            color: 'var(--text-muted)',
            padding: '4px 10px 8px 10px',
          }}>
            Assessment Workflow
          </div>

          {navItems.map((item) => {
            const isActive = activeSection === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveSection(item.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '8px 12px',
                  borderRadius: 'var(--radius-md)',
                  background: isActive ? 'var(--bg-surface-active)' : 'transparent',
                  color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                  fontWeight: isActive ? 600 : 400,
                  fontSize: '13px',
                  textAlign: 'left',
                  border: 'none',
                }}
              >
                <span>{item.icon}</span>
                <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {item.label}
                </span>
              </button>
            );
          })}
        </aside>

        {/* Content Pane */}
        <main style={{
          flex: 1,
          overflowY: 'auto',
          padding: '24px 32px',
          background: 'var(--bg-app)',
        }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>
              Loading assessment workspace...
            </div>
          ) : !workspace ? (
            <div style={{
              textAlign: 'center',
              padding: '60px',
              background: 'var(--bg-surface)',
              borderRadius: 'var(--radius-lg)',
              border: '1px solid var(--border-subtle)',
              maxWidth: '500px',
              margin: '40px auto',
            }}>
              <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>No Active Assessment</h3>
              <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '20px' }}>
                Create or select an authorized security assessment program to begin research.
              </p>
              <button
                onClick={() => setShowCreateModal(true)}
                style={{
                  padding: '8px 18px',
                  borderRadius: 'var(--radius-md)',
                  background: 'var(--accent-primary)',
                  color: '#fff',
                  fontSize: '13px',
                  fontWeight: 600,
                }}
              >
                + Create New Assessment
              </button>
            </div>
          ) : (
            <>
              {activeSection === 'overview' && (
                <OverviewTab
                  overview={workspace.overview}
                  warningBanners={workspace.warning_banners}
                  onNavigateSection={(sec) => setActiveSection(sec)}
                  onRefresh={refreshOverview}
                />
              )}
              {activeSection === 'scope_assets' && (
                <ScopeAssetsTab
                  assessmentId={workspace.overview.assessment_id}
                  onRefreshOverview={refreshOverview}
                />
              )}
              {activeSection === 'attack_surface' && (
                <AttackSurfaceTab
                  assessmentId={workspace.overview.assessment_id}
                />
              )}
              {activeSection === 'artifacts' && (
                <ArtifactsTab
                  assessmentId={workspace.overview.assessment_id}
                />
              )}
              {activeSection === 'research' && (
                <ResearchTab
                  assessmentId={workspace.overview.assessment_id}
                  onRefreshOverview={refreshOverview}
                  onNavigateSection={(sec) => setActiveSection(sec)}
                />
              )}
              {activeSection === 'hypotheses' && (
                <HypothesesTab
                  assessmentId={workspace.overview.assessment_id}
                  onRefreshOverview={refreshOverview}
                  onNavigateSection={(sec) => setActiveSection(sec)}
                />
              )}
              {activeSection === 'evidence' && (
                <EvidenceTab
                  assessmentId={workspace.overview.assessment_id}
                />
              )}
              {activeSection === 'experiments' && (
                <ExperimentsTab
                  assessmentId={workspace.overview.assessment_id}
                  onRefreshOverview={refreshOverview}
                />
              )}
              {activeSection === 'findings_review' && (
                <FindingsReviewTab
                  assessmentId={workspace.overview.assessment_id}
                  onRefreshOverview={refreshOverview}
                  onNavigateSection={(sec) => setActiveSection(sec)}
                />
              )}
              {activeSection === 'reports' && (
                <ReportsTab
                  assessmentId={workspace.overview.assessment_id}
                />
              )}
              {activeSection === 'memory_knowledge' && (
                <MemoryKnowledgeTab
                  assessmentId={workspace.overview.assessment_id}
                />
              )}
              {activeSection === 'activity_audit' && (
                <ActivityAuditTab
                  assessmentId={workspace.overview.assessment_id}
                />
              )}
            </>
          )}
        </main>
      </div>

      {/* Switcher Modal */}
      {showSwitcher && (
        <AssessmentSwitcherModal
          assessments={assessments}
          activeAssessmentId={activeAssessmentId}
          onSelect={(aid) => selectAssessment(aid)}
          onOpenCreate={() => {
            setShowSwitcher(false);
            setShowCreateModal(true);
          }}
          onClose={() => setShowSwitcher(false)}
        />
      )}

      {/* Create Assessment Modal */}
      {showCreateModal && (
        <CreateAssessmentModal
          onCreated={(aid) => {
            fetchAssessments().then(setAssessments);
            selectAssessment(aid);
          }}
          onClose={() => setShowCreateModal(false)}
        />
      )}

      {/* Global Search Modal */}
      {showSearchModal && (
        <GlobalSearchModal
          assessmentId={activeAssessmentId}
          onNavigateSection={(sec) => setActiveSection(sec)}
          onClose={() => setShowSearchModal(false)}
        />
      )}
    </div>
  );
};
