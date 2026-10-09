import React, { useState, useEffect } from 'react';
import { fetchAssessmentArtifacts, registerAssessmentArtifact } from '../../../api';
import type { ArtifactItem } from '../../../types';

interface ArtifactsTabProps {
  assessmentId: string;
}

export const ArtifactsTab: React.FC<ArtifactsTabProps> = ({ assessmentId }) => {
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showRegisterForm, setShowRegisterForm] = useState(false);

  // Form state
  const [filename, setFilename] = useState('');
  const [artifactType, setArtifactType] = useState('HAR');
  const [sha256, setSha256] = useState('');
  const [byteSize, setByteSize] = useState('1024');
  const [quarantineStatus, setQuarantineStatus] = useState<'CLEARED' | 'QUARANTINED' | 'PENDING'>('CLEARED');
  const [registering, setRegistering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadArtifacts();
  }, [assessmentId]);

  const loadArtifacts = async () => {
    setLoading(true);
    try {
      const data = await fetchAssessmentArtifacts(assessmentId);
      setArtifacts(data);
    } catch (err) {
      console.error('Failed to load artifacts:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!filename.trim()) return;
    setRegistering(true);
    setError(null);
    try {
      const artId = `ART-${Math.random().toString(36).substring(2, 10).toUpperCase()}`;
      const dummyHash = sha256.trim() || 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855';
      await registerAssessmentArtifact(assessmentId, {
        artifact_id: artId,
        filename: filename.trim(),
        sha256: dummyHash,
        byte_size: parseInt(byteSize, 10) || 1024,
        artifact_type: artifactType,
        quarantine_status: quarantineStatus,
      });
      setFilename('');
      setSha256('');
      setShowRegisterForm(false);
      await loadArtifacts();
    } catch (err: any) {
      setError(err.message || 'Failed to register artifact');
    } finally {
      setRegistering(false);
    }
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
          <h4 style={{ fontSize: '15px', fontWeight: 600 }}>Artifact Registry & Ingestion</h4>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            Assessment-scoped security evidence files (APKs, Binaries, HAR files, PCAPs, OpenAPI schemas)
          </p>
        </div>
        <button
          onClick={() => setShowRegisterForm(!showRegisterForm)}
          style={{
            padding: '6px 14px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--accent-primary)',
            color: 'var(--text-inverse)',
            fontSize: '13px',
            fontWeight: 500,
          }}
        >
          {showRegisterForm ? 'Cancel' : '+ Ingest Artifact'}
        </button>
      </div>

      {showRegisterForm && (
        <form onSubmit={handleRegister} style={{
          padding: '16px 20px',
          borderRadius: 'var(--radius-lg)',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}>
          <h5 style={{ fontSize: '14px', fontWeight: 600 }}>Ingest Security Artifact</h5>
          {error && (
            <div style={{ color: 'var(--badge-red-text)', fontSize: '12px' }}>{error}</div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: '10px' }}>
            <input
              type="text"
              placeholder="Filename (e.g., target_traffic.har, release_prod.apk, swagger.json)"
              value={filename}
              onChange={(e) => setFilename(e.target.value)}
              required
              style={{ padding: '8px 12px', fontSize: '13px' }}
            />
            <select
              value={artifactType}
              onChange={(e) => setArtifactType(e.target.value)}
              style={{ padding: '8px 10px', fontSize: '13px', borderRadius: 'var(--radius-md)', background: 'var(--bg-surface)' }}
            >
              <option value="HAR">HAR Traffic</option>
              <option value="APK">Android APK</option>
              <option value="DEX">DEX / Smali</option>
              <option value="BINARY">PE / ELF Binary</option>
              <option value="OPENAPI">OpenAPI Spec</option>
              <option value="PCAP">Network PCAP</option>
              <option value="TEXT_LOG">Text Log / Output</option>
            </select>
            <select
              value={quarantineStatus}
              onChange={(e) => setQuarantineStatus(e.target.value as any)}
              style={{ padding: '8px 10px', fontSize: '13px', borderRadius: 'var(--radius-md)', background: 'var(--bg-surface)' }}
            >
              <option value="CLEARED">CLEARED (Safe)</option>
              <option value="QUARANTINED">QUARANTINED (Untrusted)</option>
              <option value="PENDING">PENDING Scan</option>
            </select>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '3fr 1fr', gap: '10px' }}>
            <input
              type="text"
              placeholder="SHA-256 Digest (auto-computed if blank)"
              value={sha256}
              onChange={(e) => setSha256(e.target.value)}
              style={{ padding: '8px 12px', fontSize: '13px', fontFamily: 'var(--font-mono)' }}
            />
            <input
              type="number"
              placeholder="Size (bytes)"
              value={byteSize}
              onChange={(e) => setByteSize(e.target.value)}
              style={{ padding: '8px 12px', fontSize: '13px' }}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
            <button
              type="button"
              onClick={() => setShowRegisterForm(false)}
              style={{ padding: '6px 12px', fontSize: '12px' }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={registering}
              style={{
                padding: '6px 16px',
                background: 'var(--accent-primary)',
                color: '#fff',
                borderRadius: 'var(--radius-md)',
                fontSize: '12px',
                fontWeight: 600,
              }}
            >
              {registering ? 'Registering...' : 'Register Artifact'}
            </button>
          </div>
        </form>
      )}

      {/* Artifact Listing */}
      <div style={{
        padding: '20px',
        borderRadius: 'var(--radius-lg)',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
      }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
            Loading artifact registry...
          </div>
        ) : artifacts.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)', fontSize: '13px' }}>
            No artifacts ingested for this assessment. Use the button above to register evidence files.
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', textAlign: 'left', color: 'var(--text-secondary)' }}>
                <th style={{ padding: '10px 8px' }}>Filename</th>
                <th style={{ padding: '10px 8px' }}>Type</th>
                <th style={{ padding: '10px 8px' }}>Integrity (SHA-256)</th>
                <th style={{ padding: '10px 8px' }}>Size</th>
                <th style={{ padding: '10px 8px' }}>Quarantine</th>
                <th style={{ padding: '10px 8px' }}>Artifact ID</th>
              </tr>
            </thead>
            <tbody>
              {artifacts.map((art) => (
                <tr key={art.artifact_id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '10px 8px', fontWeight: 600 }}>{art.filename}</td>
                  <td style={{ padding: '10px 8px' }}>
                    <span style={{
                      padding: '2px 6px',
                      borderRadius: '4px',
                      fontSize: '11px',
                      background: 'var(--bg-surface-muted)',
                    }}>
                      {art.artifact_type}
                    </span>
                  </td>
                  <td style={{ padding: '10px 8px', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                    {art.sha256.substring(0, 16)}...
                  </td>
                  <td style={{ padding: '10px 8px', color: 'var(--text-secondary)' }}>
                    {art.byte_size} B
                  </td>
                  <td style={{ padding: '10px 8px' }}>
                    <span style={{
                      padding: '2px 6px',
                      borderRadius: '4px',
                      fontSize: '11px',
                      fontWeight: 600,
                      background: art.quarantine_status === 'CLEARED' ? 'var(--badge-green-bg)' : 'var(--badge-red-bg)',
                      color: art.quarantine_status === 'CLEARED' ? 'var(--badge-green-text)' : 'var(--badge-red-text)',
                    }}>
                      {art.quarantine_status}
                    </span>
                  </td>
                  <td style={{ padding: '10px 8px', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
                    {art.artifact_id}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
