import React from 'react';
import type { AssessmentOverview } from '../../../types';

interface OverviewTabProps {
  overview: AssessmentOverview;
  warningBanners: string[];
  onNavigateSection: (section: string) => void;
  onRefresh: () => void;
}

export const OverviewTab: React.FC<OverviewTabProps> = ({
  overview,
  warningBanners,
  onNavigateSection,
  onRefresh,
}) => {
  const wf = overview.workflow_status;

  const checklistItems = [
    { label: 'Authorization Validated', completed: wf.authorization_valid, targetSection: 'overview' },
    { label: 'Scope Defined & Bound', completed: wf.scope_defined, targetSection: 'scope_assets' },
    { label: 'Telemetry & Evidence Ingested', completed: wf.telemetry_ingested, targetSection: 'evidence' },
    { label: 'Attack Surface Mapped', completed: wf.attack_surface_mapped, targetSection: 'attack_surface' },
    { label: 'Hypotheses Formulated & Analyzed', completed: wf.hypotheses_evaluated, targetSection: 'hypotheses' },
    { label: 'Controlled Experiments Executed', completed: wf.experiments_executed, targetSection: 'experiments' },
    { label: 'Findings Formally Reviewed', completed: wf.findings_reviewed, targetSection: 'findings_review' },
    { label: 'Final Report Generated', completed: wf.report_generated, targetSection: 'reports' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Warning Banners */}
      {warningBanners.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {warningBanners.map((warn, i) => (
            <div
              key={i}
              style={{
                padding: '10px 16px',
                borderRadius: 'var(--radius-md)',
                background: 'var(--badge-amber-bg)',
                color: 'var(--badge-amber-text)',
                border: '1px solid var(--badge-amber-border)',
                fontSize: '13px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <span>⚠️</span>
              <span>{warn}</span>
            </div>
          ))}
        </div>
      )}

      {/* Metric Cards Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
        gap: '14px',
      }}>
        <div
          onClick={() => onNavigateSection('scope_assets')}
          style={{
            padding: '16px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            cursor: 'pointer',
          }}
        >
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Target Assets</div>
          <div style={{ fontSize: '24px', fontWeight: 700, margin: '4px 0' }}>{overview.asset_count}</div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            {overview.in_scope_count} in-scope · {overview.out_of_scope_count} out-of-scope
          </div>
        </div>

        <div
          onClick={() => onNavigateSection('evidence')}
          style={{
            padding: '16px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            cursor: 'pointer',
          }}
        >
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Evidence & Observations</div>
          <div style={{ fontSize: '24px', fontWeight: 700, margin: '4px 0' }}>{overview.observation_count}</div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Canonical telemetry items</div>
        </div>

        <div
          onClick={() => onNavigateSection('hypotheses')}
          style={{
            padding: '16px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            cursor: 'pointer',
          }}
        >
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Active Hypotheses</div>
          <div style={{ fontSize: '24px', fontWeight: 700, margin: '4px 0' }}>{overview.hypothesis_count}</div>
          <div style={{ fontSize: '11px', color: 'var(--badge-red-text)' }}>
            {overview.evidence_gap_count} evidence gap(s)
          </div>
        </div>

        <div
          onClick={() => onNavigateSection('experiments')}
          style={{
            padding: '16px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            cursor: 'pointer',
          }}
        >
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Controlled Experiments</div>
          <div style={{ fontSize: '24px', fontWeight: 700, margin: '4px 0' }}>{overview.experiment_count}</div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Safe PoC & reproduction tests</div>
        </div>

        <div
          onClick={() => onNavigateSection('findings_review')}
          style={{
            padding: '16px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            cursor: 'pointer',
          }}
        >
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Human-Verified Findings</div>
          <div style={{ fontSize: '24px', fontWeight: 700, margin: '4px 0', color: 'var(--badge-green-text)' }}>
            {overview.verified_finding_count} / {overview.finding_count}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>13-point verified findings</div>
        </div>
      </div>

      {/* Two Column Layout: Workflow Lifecycle Checklist & Assessment Metadata */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '20px' }}>
        {/* Workflow Lifecycle Checklist */}
        <div style={{
          padding: '20px',
          borderRadius: 'var(--radius-lg)',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
        }}>
          <h4 style={{ fontSize: '15px', fontWeight: 600, marginBottom: '6px' }}>
            Assessment Lifecycle Progression
          </h4>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
            Authoritative milestone gates required for human verification and publication
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {checklistItems.map((item, idx) => (
              <div
                key={idx}
                onClick={() => onNavigateSection(item.targetSection)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 14px',
                  borderRadius: 'var(--radius-md)',
                  background: item.completed ? 'var(--badge-green-bg)' : 'var(--bg-surface-muted)',
                  border: `1px solid ${item.completed ? 'var(--badge-green-border)' : 'var(--border-subtle)'}`,
                  cursor: 'pointer',
                  transition: 'opacity 0.15s ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ fontSize: '14px' }}>
                    {item.completed ? '✅' : '⏳'}
                  </span>
                  <span style={{
                    fontSize: '13px',
                    fontWeight: 500,
                    color: item.completed ? 'var(--badge-green-text)' : 'var(--text-primary)',
                  }}>
                    {item.label}
                  </span>
                </div>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                  {item.completed ? 'Complete' : 'Pending →'}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Assessment Details Panel */}
        <div style={{
          padding: '20px',
          borderRadius: 'var(--radius-lg)',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
        }}>
          <h4 style={{ fontSize: '15px', fontWeight: 600 }}>Assessment Governance</h4>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Organization:</span>
              <strong>{overview.organization}</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Created By:</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>{overview.created_by}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Created At:</span>
              <span>{new Date(overview.created_at).toLocaleDateString()}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Authorization ID:</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                {overview.authorization_id || 'NOT BOUND'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Scope Policy ID:</span>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                {overview.scope_policy_id || 'NOT DEFINED'}
              </span>
            </div>
          </div>

          <div style={{ marginTop: 'auto', borderTop: '1px solid var(--border-subtle)', paddingTop: '14px', display: 'flex', gap: '10px' }}>
            <button
              onClick={() => onNavigateSection('reports')}
              style={{
                flex: 1,
                padding: '8px 12px',
                borderRadius: 'var(--radius-md)',
                background: 'var(--accent-primary)',
                color: 'var(--text-inverse)',
                fontSize: '12px',
                fontWeight: 600,
              }}
            >
              📄 Preview Report
            </button>
            <button
              onClick={onRefresh}
              title="Refresh overview metrics"
              style={{
                padding: '8px 12px',
                borderRadius: 'var(--radius-md)',
                background: 'var(--bg-surface-muted)',
                border: '1px solid var(--border-subtle)',
                fontSize: '12px',
              }}
            >
              🔄 Refresh
            </button>
            <button
              onClick={() => onNavigateSection('activity_audit')}
              style={{
                padding: '8px 12px',
                borderRadius: 'var(--radius-md)',
                background: 'var(--bg-surface-muted)',
                border: '1px solid var(--border-subtle)',
                fontSize: '12px',
              }}
            >
              📜 Audit History
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
