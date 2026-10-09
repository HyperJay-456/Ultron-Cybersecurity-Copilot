import React, { useState, useEffect } from 'react';
import {
  fetchAssessmentAssets,
  createAssessmentAsset,
  validateAssessmentScope,
} from '../../../api';
import type { AssetItem } from '../../../types';

interface ScopeAssetsTabProps {
  assessmentId: string;
  onRefreshOverview: () => void;
}

export const ScopeAssetsTab: React.FC<ScopeAssetsTabProps> = ({
  assessmentId,
  onRefreshOverview,
}) => {
  const [assets, setAssets] = useState<AssetItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterScope, setFilterScope] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState('');

  // Target Scope Validation State
  const [testTarget, setTestTarget] = useState('');
  const [validationResult, setValidationResult] = useState<any | null>(null);
  const [testingScope, setTestingScope] = useState(false);

  // Add Asset Form State
  const [showAddForm, setShowAddForm] = useState(false);
  const [newIdentifier, setNewIdentifier] = useState('');
  const [newType, setNewType] = useState('DOMAIN');
  const [newScopeStatus, setNewScopeStatus] = useState('IN_SCOPE');
  const [newTags, setNewTags] = useState('');
  const [savingAsset, setSavingAsset] = useState(false);
  const [assetError, setAssetError] = useState<string | null>(null);

  useEffect(() => {
    loadAssets();
  }, [assessmentId]);

  const loadAssets = async () => {
    setLoading(true);
    try {
      const data = await fetchAssessmentAssets(assessmentId);
      setAssets(data);
    } catch (err) {
      console.error('Failed to load assets:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleTestScope = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testTarget.trim()) return;
    setTestingScope(true);
    setValidationResult(null);
    try {
      const res = await validateAssessmentScope(assessmentId, testTarget.trim());
      setValidationResult(res.validation || res);
    } catch (err: any) {
      setValidationResult({ is_in_scope: false, evaluation_reason: err.message || 'Validation failed' });
    } finally {
      setTestingScope(false);
    }
  };

  const handleAddAsset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newIdentifier.trim()) return;
    setSavingAsset(true);
    setAssetError(null);
    try {
      const tagsArray = newTags.split(',').map((t) => t.trim()).filter(Boolean);
      await createAssessmentAsset(assessmentId, {
        canonical_identifier: newIdentifier.trim(),
        asset_type: newType,
        scope_status: newScopeStatus,
        tags: tagsArray,
      });
      setNewIdentifier('');
      setNewTags('');
      setShowAddForm(false);
      await loadAssets();
      onRefreshOverview();
    } catch (err: any) {
      setAssetError(err.message || 'Failed to add asset');
    } finally {
      setSavingAsset(false);
    }
  };

  const filteredAssets = assets.filter((a) => {
    const matchesSearch =
      a.canonical_identifier.toLowerCase().includes(searchTerm.toLowerCase()) ||
      a.tags.some((t) => t.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesScope = filterScope === 'ALL' || a.scope_status === filterScope;
    return matchesSearch && matchesScope;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Top Banner: ScopeGate Real-Time Validation Tool */}
      <div style={{
        padding: '16px 20px',
        borderRadius: 'var(--radius-lg)',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h4 style={{ fontSize: '14px', fontWeight: 600 }}>ScopeGate Target Validator</h4>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Deterministic preflight check ensuring all interactions remain within authorized bounds.
            </p>
          </div>
          <span style={{
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
            padding: '3px 8px',
            background: 'var(--bg-surface-muted)',
            borderRadius: '4px',
          }}>
            RULE M13-03: Scope cannot be expanded silently
          </span>
        </div>

        <form onSubmit={handleTestScope} style={{ display: 'flex', gap: '10px' }}>
          <input
            type="text"
            placeholder="Enter target URL, host, or IP (e.g., https://api.example.com/v1/user)..."
            value={testTarget}
            onChange={(e) => setTestTarget(e.target.value)}
            style={{ flex: 1, padding: '8px 12px', fontSize: '13px' }}
          />
          <button
            type="submit"
            disabled={testingScope || !testTarget.trim()}
            style={{
              padding: '8px 16px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--accent-primary)',
              color: 'var(--text-inverse)',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            {testingScope ? 'Checking...' : 'Check Scope'}
          </button>
        </form>

        {validationResult && (
          <div style={{
            padding: '10px 14px',
            borderRadius: 'var(--radius-md)',
            background: validationResult.is_in_scope ? 'var(--badge-green-bg)' : 'var(--badge-red-bg)',
            color: validationResult.is_in_scope ? 'var(--badge-green-text)' : 'var(--badge-red-text)',
            border: `1px solid ${validationResult.is_in_scope ? 'var(--badge-green-border)' : 'var(--badge-red-border)'}`,
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>{validationResult.is_in_scope ? '✅ IN SCOPE' : '🛑 OUT OF SCOPE'}</span>
              <span>— {validationResult.evaluation_reason}</span>
            </div>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
              Target: {validationResult.target}
            </span>
          </div>
        )}
      </div>

      {/* Asset Inventory Section */}
      <div style={{
        padding: '20px',
        borderRadius: 'var(--radius-lg)',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        gap: '14px',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h4 style={{ fontSize: '15px', fontWeight: 600 }}>Asset Inventory</h4>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
              Canonical targets, domains, mobile packages, and source repositories
            </p>
          </div>
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            style={{
              padding: '6px 14px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--accent-primary)',
              color: 'var(--text-inverse)',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            {showAddForm ? 'Cancel' : '+ Add Asset'}
          </button>
        </div>

        {/* Add Asset Inline Form */}
        {showAddForm && (
          <form onSubmit={handleAddAsset} style={{
            padding: '16px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-surface-muted)',
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
          }}>
            <div style={{ fontWeight: 600, fontSize: '13px' }}>Register Target Asset</div>
            {assetError && (
              <div style={{ color: 'var(--badge-red-text)', fontSize: '12px' }}>{assetError}</div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: '10px' }}>
              <input
                type="text"
                placeholder="Identifier (e.g., example.com, 192.168.1.1, com.app.target)"
                value={newIdentifier}
                onChange={(e) => setNewIdentifier(e.target.value)}
                required
                style={{ padding: '8px 12px', fontSize: '13px' }}
              />
              <select
                value={newType}
                onChange={(e) => setNewType(e.target.value)}
                style={{ padding: '8px 10px', fontSize: '13px', borderRadius: 'var(--radius-md)', background: 'var(--bg-surface)' }}
              >
                <option value="DOMAIN">DOMAIN</option>
                <option value="HOST_IP">HOST_IP</option>
                <option value="IP_RANGE">IP_RANGE</option>
                <option value="URL_ENDPOINT">URL_ENDPOINT</option>
                <option value="MOBILE_APP">MOBILE_APP</option>
                <option value="SOURCE_REPO">SOURCE_REPO</option>
                <option value="BINARY">BINARY</option>
              </select>
              <select
                value={newScopeStatus}
                onChange={(e) => setNewScopeStatus(e.target.value)}
                style={{ padding: '8px 10px', fontSize: '13px', borderRadius: 'var(--radius-md)', background: 'var(--bg-surface)' }}
              >
                <option value="IN_SCOPE">IN_SCOPE</option>
                <option value="OUT_OF_SCOPE">OUT_OF_SCOPE</option>
                <option value="UNKNOWN">UNKNOWN</option>
              </select>
            </div>
            <input
              type="text"
              placeholder="Tags (comma-separated, e.g., prod, api, v2)"
              value={newTags}
              onChange={(e) => setNewTags(e.target.value)}
              style={{ padding: '8px 12px', fontSize: '13px' }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                style={{ padding: '6px 12px', fontSize: '12px', background: 'var(--bg-surface)' }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={savingAsset}
                style={{
                  padding: '6px 14px',
                  background: 'var(--accent-primary)',
                  color: '#fff',
                  borderRadius: 'var(--radius-md)',
                  fontSize: '12px',
                  fontWeight: 600,
                }}
              >
                {savingAsset ? 'Saving...' : 'Save Asset'}
              </button>
            </div>
          </form>
        )}

        {/* Filters */}
        <div style={{ display: 'flex', gap: '10px' }}>
          <input
            type="text"
            placeholder="Search assets..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{ flex: 1, padding: '6px 12px', fontSize: '13px' }}
          />
          <select
            value={filterScope}
            onChange={(e) => setFilterScope(e.target.value)}
            style={{
              padding: '6px 10px',
              fontSize: '13px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-surface)',
            }}
          >
            <option value="ALL">All Scope Statuses</option>
            <option value="IN_SCOPE">IN_SCOPE Only</option>
            <option value="OUT_OF_SCOPE">OUT_OF_SCOPE Only</option>
            <option value="UNKNOWN">UNKNOWN Only</option>
          </select>
        </div>

        {/* Asset Table */}
        {loading ? (
          <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
            Loading asset graph...
          </div>
        ) : filteredAssets.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)', fontSize: '13px' }}>
            No assets match current criteria.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'left', color: 'var(--text-secondary)' }}>
                  <th style={{ padding: '10px 8px' }}>Identifier</th>
                  <th style={{ padding: '10px 8px' }}>Type</th>
                  <th style={{ padding: '10px 8px' }}>Scope Status</th>
                  <th style={{ padding: '10px 8px' }}>Tags</th>
                  <th style={{ padding: '10px 8px' }}>Discovery</th>
                  <th style={{ padding: '10px 8px' }}>Asset ID</th>
                </tr>
              </thead>
              <tbody>
                {filteredAssets.map((asset) => {
                  const isInScope = asset.scope_status === 'IN_SCOPE';
                  return (
                    <tr
                      key={asset.asset_id}
                      style={{ borderBottom: '1px solid var(--border-subtle)' }}
                    >
                      <td style={{ padding: '10px 8px', fontWeight: 600 }}>
                        {asset.canonical_identifier}
                      </td>
                      <td style={{ padding: '10px 8px' }}>
                        <span style={{
                          fontSize: '11px',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          background: 'var(--bg-surface-muted)',
                        }}>
                          {asset.asset_type}
                        </span>
                      </td>
                      <td style={{ padding: '10px 8px' }}>
                        <span style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          padding: '2px 8px',
                          borderRadius: '4px',
                          background: isInScope ? 'var(--badge-green-bg)' : 'var(--badge-red-bg)',
                          color: isInScope ? 'var(--badge-green-text)' : 'var(--badge-red-text)',
                        }}>
                          {asset.scope_status}
                        </span>
                      </td>
                      <td style={{ padding: '10px 8px' }}>
                        {asset.tags.map((t, idx) => (
                          <span
                            key={idx}
                            style={{
                              fontSize: '10px',
                              background: 'var(--bg-surface-muted)',
                              padding: '2px 4px',
                              borderRadius: '4px',
                              marginRight: '4px',
                            }}
                          >
                            {t}
                          </span>
                        ))}
                      </td>
                      <td style={{ padding: '10px 8px', color: 'var(--text-muted)', fontSize: '12px' }}>
                        {asset.discovery_method || 'MANUAL'}
                      </td>
                      <td style={{ padding: '10px 8px', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                        {asset.asset_id}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
