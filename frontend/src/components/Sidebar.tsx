import React, { useState } from 'react';
import type { InvestigationSummary } from '../types';

interface SidebarProps {
  investigations: InvestigationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewInvestigation: () => void;
  onLoadDemo: () => void;
  onOpenSystemStatus: () => void;
  systemStatusReady: boolean;
  onOpenWorkspace?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  investigations,
  activeId,
  onSelect,
  onNewInvestigation,
  onLoadDemo,
  onOpenSystemStatus,
  systemStatusReady,
  onOpenWorkspace,
}) => {
  const [search, setSearch] = useState('');

  const filtered = investigations.filter(
    (inv) =>
      inv.name.toLowerCase().includes(search.toLowerCase()) ||
      inv.target_host.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <aside
      style={{
        width: '260px',
        backgroundColor: 'var(--bg-sidebar)',
        borderRight: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        flexShrink: 0,
        userSelect: 'none',
      }}
    >
      {/* Platform Branding */}
      <div style={{ padding: '20px 18px 14px 18px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div
              style={{
                width: '24px',
                height: '24px',
                borderRadius: '6px',
                backgroundColor: 'var(--accent-primary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#FFF',
                fontSize: '13px',
                fontWeight: 600,
              }}
            >
              B
            </div>
            <span style={{ fontSize: '14.5px', fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '-0.01em' }}>
              Bug Bounty AI
            </span>
          </div>
          <span style={{ fontSize: '10.5px', color: 'var(--text-muted)', backgroundColor: 'var(--bg-surface-muted)', padding: '2px 6px', borderRadius: '4px' }}>
            Local
          </span>
        </div>

        {/* Workspace Switcher Button */}
        {onOpenWorkspace && (
          <button
            onClick={onOpenWorkspace}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              marginBottom: '10px',
              padding: '8px 12px',
              backgroundColor: 'var(--accent-primary)',
              color: '#FFFFFF',
              borderRadius: 'var(--radius-md)',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            <span>Assessment Workspace</span>
          </button>
        )}

        {/* New Investigation Button */}
        <button
          onClick={onNewInvestigation}
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            padding: '8px 14px',
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            fontSize: '13px',
            fontWeight: 500,
            color: 'var(--text-primary)',
            boxShadow: 'var(--shadow-subtle)',
            transition: 'background-color 0.15s ease',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)')}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'var(--bg-surface)')}
        >
          <span style={{ fontSize: '15px', lineHeight: 1 }}>+</span>
          <span>New investigation</span>
        </button>

        {/* Subtle Load Demo Fixture Button */}
        <button
          onClick={onLoadDemo}
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            marginTop: '8px',
            padding: '6px 12px',
            backgroundColor: 'transparent',
            border: '1px dashed var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            fontSize: '11.5px',
            color: 'var(--text-secondary)',
            transition: 'all 0.15s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)';
            e.currentTarget.style.color = 'var(--text-primary)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
            e.currentTarget.style.color = 'var(--text-secondary)';
          }}
        >
          <span>▶</span>
          <span>Load demo fixture</span>
        </button>
      </div>

      {/* Search Filter */}
      <div style={{ padding: '0 18px 12px 18px' }}>
        <input
          type="text"
          placeholder="Search investigations..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            width: '100%',
            padding: '6px 10px',
            fontSize: '12.5px',
            backgroundColor: 'var(--bg-surface)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-subtle)',
          }}
        />
      </div>

      {/* Recent Investigations List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 10px' }}>
        <div style={{ padding: '4px 8px', fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.04em' }}>
          RECENT
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', marginTop: '4px' }}>
          {filtered.length > 0 ? (
            filtered.map((inv) => {
              const isActive = inv.id === activeId;
              return (
                <div
                  key={inv.id}
                  onClick={() => onSelect(inv.id)}
                  style={{
                    padding: '8px 10px',
                    borderRadius: 'var(--radius-md)',
                    backgroundColor: isActive ? 'var(--bg-surface-active)' : 'transparent',
                    cursor: 'pointer',
                    transition: 'background-color 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)';
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', overflow: 'hidden' }}>
                    {inv.is_demo && (
                      <span
                        style={{
                          fontSize: '8.5px',
                          fontWeight: 600,
                          color: 'var(--text-secondary)',
                          backgroundColor: 'var(--bg-surface-muted)',
                          padding: '1px 4px',
                          borderRadius: '3px',
                          marginRight: '6px',
                          flexShrink: 0,
                        }}
                      >
                        DEMO
                      </span>
                    )}
                    <span
                      style={{
                        fontSize: '13px',
                        fontWeight: isActive ? 500 : 400,
                        color: 'var(--text-primary)',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {inv.name}
                    </span>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px', fontFamily: 'var(--font-mono)' }}>
                    {inv.target_host}
                  </div>
                </div>
              );
            })
          ) : (
            <div style={{ padding: '24px 12px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
              No investigations yet.
            </div>
          )}
        </div>
      </div>

      {/* Sidebar Footer with System Status */}
      <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border-subtle)', backgroundColor: 'var(--bg-sidebar)' }}>
        <button
          onClick={onOpenSystemStatus}
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '7px 10px',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            fontSize: '12px',
            color: 'var(--text-secondary)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-surface-hover)';
            e.currentTarget.style.color = 'var(--text-primary)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-surface)';
            e.currentTarget.style.color = 'var(--text-secondary)';
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                backgroundColor: systemStatusReady ? '#2D6A4F' : '#9A6B1F',
              }}
            />
            <span>System status</span>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>→</span>
        </button>
      </div>
    </aside>
  );
};
