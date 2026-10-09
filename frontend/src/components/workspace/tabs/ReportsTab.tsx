import React, { useState, useEffect } from 'react';
import { generateAssessmentReport, exportAssessmentReport } from '../../../api';

interface ReportsTabProps {
  assessmentId: string;
}

export const ReportsTab: React.FC<ReportsTabProps> = ({ assessmentId }) => {
  const [reportMarkdown, setReportMarkdown] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    handleGenerate();
  }, [assessmentId]);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await generateAssessmentReport(assessmentId);
      setReportMarkdown(res.report_markdown || '');
    } catch (err: any) {
      setError(err.message || 'Report generation failed');
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async (format: string = 'markdown') => {
    setExporting(true);
    try {
      const res = await exportAssessmentReport(assessmentId, format);
      const content = res.content || reportMarkdown || '';
      const blob = new Blob([content], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${assessmentId}_security_assessment_report.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(`Export failed: ${err.message || 'Unknown error'}`);
    } finally {
      setExporting(false);
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
          <h4 style={{ fontSize: '15px', fontWeight: 600 }}>Production Assessment Report Center</h4>
          <p style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            Traceable reporting over validated scope, target evidence, and human-verified findings
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <button
            onClick={handleGenerate}
            disabled={loading}
            style={{
              padding: '6px 14px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-surface)',
              fontSize: '13px',
              fontWeight: 500,
            }}
          >
            {loading ? 'Compiling...' : 'Regenerate Draft'}
          </button>
          <button
            onClick={() => handleExport('markdown')}
            disabled={exporting || !reportMarkdown}
            style={{
              padding: '6px 16px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--accent-primary)',
              color: 'var(--text-inverse)',
              fontSize: '13px',
              fontWeight: 600,
            }}
          >
            {exporting ? 'Exporting...' : 'Export Markdown (.md)'}
          </button>
        </div>
      </div>

      {/* Redaction Vault & Invariant Notice */}
      <div style={{
        padding: '10px 14px',
        borderRadius: 'var(--radius-md)',
        background: 'var(--bg-surface-muted)',
        border: '1px solid var(--border-subtle)',
        fontSize: '12px',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        color: 'var(--text-secondary)',
      }}>
        <span>🔒</span>
        <span>
          <strong>Redaction Vault Active:</strong> Credentials, session cookies, and private API keys are redacted. Unverified candidate findings are marked with clear epistemic disclaimers.
        </span>
      </div>

      {/* Report Preview */}
      <div style={{
        padding: '24px',
        borderRadius: 'var(--radius-lg)',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        minHeight: '400px',
      }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>
            Assembling assessment report from canonical findings and scope records...
          </div>
        ) : error ? (
          <div style={{
            padding: '16px',
            background: 'var(--badge-amber-bg)',
            color: 'var(--badge-amber-text)',
            borderRadius: 'var(--radius-md)',
            fontSize: '13px',
          }}>
            ⚠️ {error}
          </div>
        ) : reportMarkdown ? (
          <pre style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
            lineHeight: 1.6,
            whiteSpace: 'pre-wrap',
            color: 'var(--text-primary)',
          }}>
            {reportMarkdown}
          </pre>
        ) : (
          <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)' }}>
            No report generated yet. Click Regenerate Draft.
          </div>
        )}
      </div>
    </div>
  );
};
