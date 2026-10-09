import React, { useState, useEffect } from 'react';
import { fetchAssessmentActivity } from '../../../api';
import type { AssessmentActivity } from '../../../types';

interface ActivityAuditTabProps {
  assessmentId: string;
}

export const ActivityAuditTab: React.FC<ActivityAuditTabProps> = ({ assessmentId }) => {
  const [activities, setActivities] = useState<AssessmentActivity[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState('ALL');

  useEffect(() => {
    loadActivity();
  }, [assessmentId]);

  const loadActivity = async () => {
    setLoading(true);
    try {
      const data = await fetchAssessmentActivity(assessmentId, 100);
      setActivities(data);
    } catch (err) {
      console.error('Failed to load activity timeline:', err);
    } finally {
      setLoading(false);
    }
  };

  const filtered = activities.filter((a) => {
    return filterType === 'ALL' || a.event_type === filterType;
  });

  const getEventBadge = (type: string) => {
    if (type.includes('VERIFIED')) return { bg: 'var(--badge-green-bg)', text: 'var(--badge-green-text)' };
    if (type.includes('AUTHORIZATION')) return { bg: 'var(--badge-blue-bg)', text: 'var(--badge-blue-text)' };
    if (type.includes('EXPERIMENT')) return { bg: 'var(--badge-amber-bg)', text: 'var(--badge-amber-text)' };
    return { bg: 'var(--bg-surface-muted)', text: 'var(--text-secondary)' };
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{
        padding: '16px 20px',
        borderRadius: 'var(--radius-lg)',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <div>
          <h4 style={{ fontSize: '15px', fontWeight: 600 }}>Immutable Activity & Audit Timeline</h4>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            Cryptographically chained events and state changes recorded by the AssessmentAuditLogger
          </p>
        </div>
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          style={{ padding: '6px 12px', fontSize: '13px', borderRadius: 'var(--radius-md)', background: 'var(--bg-surface)' }}
        >
          <option value="ALL">All Event Types</option>
          <option value="ASSESSMENT_CREATED">ASSESSMENT_CREATED</option>
          <option value="AUTHORIZATION_ACCEPTED">AUTHORIZATION_ACCEPTED</option>
          <option value="SCOPE_DEFINED">SCOPE_DEFINED</option>
          <option value="OBSERVATION_IMPORTED">OBSERVATION_IMPORTED</option>
          <option value="HYPOTHESIS_CREATED">HYPOTHESIS_CREATED</option>
          <option value="EXPERIMENT_PROPOSED">EXPERIMENT_PROPOSED</option>
          <option value="FINDING_VERIFIED">FINDING_VERIFIED</option>
          <option value="REPORT_GENERATED">REPORT_GENERATED</option>
          <option value="REPORT_EXPORTED">REPORT_EXPORTED</option>
        </select>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
          Loading audit events...
        </div>
      ) : filtered.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: '40px',
          background: 'var(--bg-surface)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border-subtle)',
          color: 'var(--text-muted)',
          fontSize: '13px',
        }}>
          No audit records matching criteria.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {filtered.map((item) => {
            const badge = getEventBadge(item.event_type);
            return (
              <div
                key={item.event_id}
                style={{
                  padding: '12px 18px',
                  borderRadius: 'var(--radius-md)',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '6px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{
                      padding: '2px 8px',
                      borderRadius: '4px',
                      fontSize: '11px',
                      fontWeight: 700,
                      background: badge.bg,
                      color: badge.text,
                    }}>
                      {item.event_type}
                    </span>
                    <span style={{ fontWeight: 600, fontSize: '13px' }}>
                      {item.summary}
                    </span>
                  </div>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                    {item.event_id}
                  </span>
                </div>

                <div style={{ display: 'flex', gap: '16px', fontSize: '11px', color: 'var(--text-muted)' }}>
                  <span>Actor: <strong>{item.actor}</strong></span>
                  <span>Component: <strong>{item.component}</strong></span>
                  <span>Auth State: <strong>{item.authorization_state}</strong></span>
                  <span>Scope: <strong>{item.scope_state}</strong></span>
                  <span>Timestamp: <strong>{new Date(item.timestamp).toLocaleString()}</strong></span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
