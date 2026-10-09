import React, { useState } from 'react';

interface MemoryKnowledgeTabProps {
  assessmentId: string;
}

export const MemoryKnowledgeTab: React.FC<MemoryKnowledgeTabProps> = ({ assessmentId }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNamespace, setSelectedNamespace] = useState<string>('ALL');

  const namespaces = [
    {
      id: 'ASSESSMENT_LOCAL',
      name: 'Assessment Local',
      description: 'Private research memory strictly bounded to this assessment container.',
      count: 3,
      badge: 'Isolated',
    },
    {
      id: 'USER_RESEARCH',
      name: 'User Research',
      description: 'Researcher-specific heuristics and personal analytical observations.',
      count: 8,
      badge: 'Private',
    },
    {
      id: 'SHARED_RESEARCH',
      name: 'Shared Research',
      description: 'Human-promoted, peer-reviewed reusable attack patterns and PoCs.',
      count: 14,
      badge: 'Governed',
    },
    {
      id: 'GLOBAL_KNOWLEDGE',
      name: 'Global Standards (M9 RAG)',
      description: 'Authoritative cybersecurity references (OWASP ASVS, CWE, CAPEC, NIST).',
      count: 120,
      badge: 'External Reference',
    },
  ];

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
          <h4 style={{ fontSize: '15px', fontWeight: 600 }}>Research Memory & Knowledge Context</h4>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            M12 Multi-tier research memory engine with namespace isolation for assessment {assessmentId}
          </p>
        </div>
        <div style={{
          padding: '4px 10px',
          borderRadius: 'var(--radius-sm)',
          fontSize: '11px',
          background: 'var(--badge-blue-bg)',
          color: 'var(--badge-blue-text)',
        }}>
          Namespace Isolation Enforced (M12 Engine)
        </div>
      </div>

      {/* Namespace Cards Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: '14px',
      }}>
        {namespaces.map((ns) => (
          <div
            key={ns.id}
            onClick={() => setSelectedNamespace(ns.id)}
            style={{
              padding: '16px',
              borderRadius: 'var(--radius-md)',
              background: selectedNamespace === ns.id ? 'var(--bg-surface-muted)' : 'var(--bg-surface)',
              border: selectedNamespace === ns.id ? '2px solid var(--border-focus)' : '1px solid var(--border-subtle)',
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 600, fontSize: '13px' }}>{ns.name}</span>
              <span style={{
                fontSize: '10px',
                padding: '2px 6px',
                borderRadius: '4px',
                background: 'var(--bg-surface-muted)',
              }}>
                {ns.badge}
              </span>
            </div>
            <p style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
              {ns.description}
            </p>
            <div style={{ marginTop: 'auto', fontSize: '11px', color: 'var(--text-muted)' }}>
              Items: <strong>{ns.count}</strong>
            </div>
          </div>
        ))}
      </div>

      {/* Memory Search Bar */}
      <div style={{
        padding: '20px',
        borderRadius: 'var(--radius-lg)',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
      }}>
        <h5 style={{ fontSize: '14px', fontWeight: 600 }}>Hybrid Memory & Knowledge Retrieval</h5>
        <div style={{ display: 'flex', gap: '10px' }}>
          <input
            type="text"
            placeholder="Search research patterns, negative controls, and prior verified techniques..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ flex: 1, padding: '8px 12px', fontSize: '13px' }}
          />
          <button
            style={{
              padding: '8px 16px',
              background: 'var(--accent-primary)',
              color: '#fff',
              borderRadius: 'var(--radius-md)',
              fontSize: '13px',
              fontWeight: 600,
            }}
          >
            Retrieve
          </button>
        </div>

        <div style={{
          fontSize: '12px',
          color: 'var(--text-muted)',
          background: 'var(--bg-surface-muted)',
          padding: '12px 16px',
          borderRadius: 'var(--radius-sm)',
        }}>
          💡 <strong>Invariant M13-09:</strong> Recalled memory serves as contextual heuristic and research inspiration. It cannot authorize target testing or substitute for canonical target observation.
        </div>
      </div>
    </div>
  );
};
