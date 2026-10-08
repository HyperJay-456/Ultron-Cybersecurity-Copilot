import React, { useState, useMemo, useRef } from 'react';
import type { ChatMessage, ResponseChunk, ResponseVersion } from '../types';
import {
  continueResponse,
  exportResponse,
  performResponseAction,
  regenerateResponse,
  stopResponseGeneration,
  fetchResponseChunks,
  fetchResponseVersions,
} from '../api';

interface LargeResponseViewProps {
  message: ChatMessage;
  onSendFollowUp?: (prompt: string) => void;
  onUpdateMessageContent?: (messageId: string, newContent: string) => void;
}

export const LargeResponseView: React.FC<LargeResponseViewProps> = ({
  message,
  onSendFollowUp,
  onUpdateMessageContent,
}) => {
  const [copiedAll, setCopiedAll] = useState(false);
  const [copiedSection, setCopiedSection] = useState<string | null>(null);
  const [copiedCodeBlock, setCopiedCodeBlock] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchActive, setSearchActive] = useState(false);
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});
  const [showMetadata, setShowMetadata] = useState(false);
  const [showVersions, setShowVersions] = useState(false);
  const [showChunks, setShowChunks] = useState(false);
  const [chunks, setChunks] = useState<ResponseChunk[]>([]);
  const [versions, setVersions] = useState<ResponseVersion[]>([]);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);

  const content = message.content || '';
  const responseId = message.response_id;
  const isGenerating = message.status === 'GENERATING' || message.status === 'CONTINUING';
  const isTokenLimit = message.status === 'TOKEN_LIMIT';

  // Parse markdown-like technical sections safely
  const parsedSections = useMemo(() => {
    const rawLines = content.split('\n');
    const sections: Array<{ title: string; lines: string[]; id: string }> = [];
    let currentTitle = 'Overview';
    let currentLines: string[] = [];

    const sectionRegex = /^#{1,4}\s+(.+)$/;

    for (const line of rawLines) {
      const match = line.match(sectionRegex);
      if (match) {
        if (currentLines.length > 0) {
          sections.push({
            title: currentTitle,
            lines: [...currentLines],
            id: currentTitle.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
          });
          currentLines = [];
        }
        currentTitle = match[1].trim();
      } else {
        currentLines.push(line);
      }
    }

    if (currentLines.length > 0 || sections.length === 0) {
      sections.push({
        title: currentTitle,
        lines: currentLines,
        id: currentTitle.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
      });
    }

    return sections;
  }, [content]);

  // Safe search highlighting counter
  const matchCount = useMemo(() => {
    if (!searchQuery.trim()) return 0;
    try {
      const escaped = searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const matches = content.match(new RegExp(escaped, 'gi'));
      return matches ? matches.length : 0;
    } catch {
      return 0;
    }
  }, [content, searchQuery]);

  const handleCopyAll = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedAll(true);
      setTimeout(() => setCopiedAll(false), 2000);
    } catch {
      // Fallback
      setStatusMessage('Copy failed');
    }
  };

  const handleCopySection = async (title: string, sectionText: string) => {
    try {
      await navigator.clipboard.writeText(sectionText);
      setCopiedSection(title);
      setTimeout(() => setCopiedSection(null), 2000);
    } catch {
      setStatusMessage('Copy section failed');
    }
  };

  const handleCopyCode = async (index: number, code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCodeBlock(index);
      setTimeout(() => setCopiedCodeBlock(null), 2000);
    } catch {
      setStatusMessage('Copy code failed');
    }
  };

  const handleDownload = async (format: 'markdown' | 'txt') => {
    try {
      let exportText = content;
      if (responseId) {
        const res = await exportResponse(responseId, format);
        exportText = res.content;
      }
      const blob = new Blob([exportText], { type: format === 'markdown' ? 'text/markdown' : 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `response_${responseId || message.id}.${format === 'markdown' ? 'md' : 'txt'}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setStatusMessage(`Download failed: ${err.message}`);
    }
  };

  const handleStop = async () => {
    if (!responseId) return;
    try {
      setLoadingAction('stop');
      await stopResponseGeneration(responseId);
      setStatusMessage('Generation stopped');
    } catch (err: any) {
      setStatusMessage(`Stop failed: ${err.message}`);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleContinue = async () => {
    if (!responseId) return;
    try {
      setLoadingAction('continue');
      setStatusMessage('Continuing answer...');
      const session = await continueResponse(responseId);
      if (onUpdateMessageContent) {
        onUpdateMessageContent(message.id, session.final_content);
      }
      setStatusMessage('Continuation merged');
    } catch (err: any) {
      setStatusMessage(`Continue failed: ${err.message}`);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleRegenerate = async () => {
    if (!responseId) return;
    try {
      setLoadingAction('regenerate');
      setStatusMessage('Regenerating answer...');
      const session = await regenerateResponse(responseId);
      if (onUpdateMessageContent) {
        onUpdateMessageContent(message.id, session.final_content);
      }
      setStatusMessage(`Regenerated (Version ${session.active_version})`);
    } catch (err: any) {
      setStatusMessage(`Regenerate failed: ${err.message}`);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleAnswerAction = async (action: string) => {
    if (!responseId) return;
    try {
      setLoadingAction(action);
      setStatusMessage(`Executing ${action}...`);
      const session = await performResponseAction(responseId, action);
      if (onSendFollowUp) {
        onSendFollowUp(session.final_content);
      }
      setStatusMessage(`${action} completed`);
    } catch (err: any) {
      setStatusMessage(`Action failed: ${err.message}`);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleToggleChunks = async () => {
    if (!showChunks && responseId) {
      try {
        const chunkList = await fetchResponseChunks(responseId);
        setChunks(chunkList);
      } catch (e) {
        console.error(e);
      }
    }
    setShowChunks(!showChunks);
  };

  const handleToggleVersions = async () => {
    if (!showVersions && responseId) {
      try {
        const verList = await fetchResponseVersions(responseId);
        setVersions(verList);
      } catch (e) {
        console.error(e);
      }
    }
    setShowVersions(!showVersions);
  };

  const toggleSectionCollapse = (id: string) => {
    setCollapsedSections((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // Safe block renderer for text & code blocks
  const renderFormattedLines = (lines: string[]) => {
    const elements: React.ReactNode[] = [];
    let inCode = false;
    let codeLang = '';
    let codeLines: string[] = [];
    let codeIndex = 0;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      if (line.startsWith('```')) {
        if (!inCode) {
          inCode = true;
          codeLang = line.replace('```', '').trim() || 'plaintext';
          codeLines = [];
        } else {
          inCode = false;
          const currentCode = codeLines.join('\n');
          const idx = codeIndex++;
          elements.push(
            <div
              key={`code-${i}`}
              style={{
                margin: '14px 0',
                backgroundColor: '#1E1E1E',
                borderRadius: '8px',
                border: '1px solid #333333',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '6px 12px',
                  backgroundColor: '#2D2D2D',
                  color: '#999999',
                  fontSize: '11px',
                  fontFamily: 'monospace',
                }}
              >
                <span>{codeLang.toUpperCase()}</span>
                <button
                  onClick={() => handleCopyCode(idx, currentCode)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: copiedCodeBlock === idx ? '#4ADE80' : '#CCCCCC',
                    cursor: 'pointer',
                    fontSize: '11px',
                  }}
                >
                  {copiedCodeBlock === idx ? '✓ Copied' : 'Copy code'}
                </button>
              </div>
              <pre
                style={{
                  margin: 0,
                  padding: '12px 16px',
                  color: '#D4D4D4',
                  fontSize: '13px',
                  fontFamily: '"JetBrains Mono", Consolas, Menlo, monospace',
                  overflowX: 'auto',
                  lineHeight: 1.5,
                  whiteSpace: 'pre',
                }}
              >
                <code>{currentCode}</code>
              </pre>
            </div>
          );
        }
        continue;
      }

      if (inCode) {
        codeLines.push(line);
        continue;
      }

      // Check table row
      if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
        elements.push(
          <div
            key={`tbl-${i}`}
            style={{
              overflowX: 'auto',
              fontFamily: 'monospace',
              fontSize: '12.5px',
              backgroundColor: 'var(--bg-surface-muted)',
              padding: '2px 8px',
              borderRadius: '2px',
              marginBottom: '2px',
            }}
          >
            {line}
          </div>
        );
        continue;
      }

      // Highlight search matches safely
      if (searchQuery.trim() && line.toLowerCase().includes(searchQuery.toLowerCase())) {
        const parts = line.split(new RegExp(`(${searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'));
        elements.push(
          <p key={`p-${i}`} style={{ margin: '6px 0', lineHeight: 1.6 }}>
            {parts.map((p, pIdx) =>
              p.toLowerCase() === searchQuery.toLowerCase() ? (
                <mark key={pIdx} style={{ backgroundColor: '#FEF08A', color: '#1F2937', padding: '1px 3px', borderRadius: '2px' }}>
                  {p}
                </mark>
              ) : (
                <span key={pIdx}>{p}</span>
              )
            )}
          </p>
        );
      } else {
        elements.push(
          <p key={`p-${i}`} style={{ margin: '6px 0', lineHeight: 1.6, wordBreak: 'break-word' }}>
            {line}
          </p>
        );
      }
    }

    if (inCode && codeLines.length > 0) {
      // Unclosed code block indicator
      const currentCode = codeLines.join('\n');
      elements.push(
        <div
          key="unclosed-code"
          style={{
            margin: '14px 0',
            backgroundColor: '#1E1E1E',
            borderRadius: '8px',
            border: '1px dashed #EAB308',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '6px 12px',
              backgroundColor: '#3730A3',
              color: '#FDE047',
              fontSize: '11px',
              fontFamily: 'monospace',
            }}
          >
            {codeLang.toUpperCase()} (INCOMPLETE STREAMING CODE BLOCK)
          </div>
          <pre
            style={{
              margin: 0,
              padding: '12px 16px',
              color: '#D4D4D4',
              fontSize: '13px',
              fontFamily: 'monospace',
              overflowX: 'auto',
            }}
          >
            <code>{currentCode}</code>
          </pre>
        </div>
      );
    }

    return elements;
  };

  return (
    <div
      ref={containerRef}
      className="large-response-container"
      style={{
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--bg-surface)',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        boxShadow: '0 1px 3px rgba(0,0,0,0.02)',
      }}
    >
      {/* Top Sticky Action Toolbar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '8px 16px',
          backgroundColor: 'var(--bg-surface-muted)',
          borderBottom: '1px solid var(--border-subtle)',
          position: 'sticky',
          top: 0,
          zIndex: 10,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Research Analysis
          </span>
          {message.status && (
            <span
              style={{
                fontSize: '11px',
                padding: '2px 7px',
                borderRadius: '4px',
                backgroundColor:
                  message.status === 'COMPLETED'
                    ? '#DCFCE7'
                    : message.status === 'TOKEN_LIMIT'
                    ? '#FEF3C7'
                    : message.status === 'USER_STOPPED'
                    ? '#FEE2E2'
                    : '#EFF6FF',
                color:
                  message.status === 'COMPLETED'
                    ? '#166534'
                    : message.status === 'TOKEN_LIMIT'
                    ? '#92400E'
                    : message.status === 'USER_STOPPED'
                    ? '#991B1B'
                    : '#1E40AF',
                fontWeight: 500,
              }}
            >
              {message.status}
            </span>
          )}
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          {isGenerating && (
            <button
              onClick={handleStop}
              disabled={loadingAction === 'stop'}
              style={{
                padding: '4px 10px',
                fontSize: '11.5px',
                backgroundColor: '#EF4444',
                color: '#FFFFFF',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 500,
              }}
            >
              ■ Stop Generating
            </button>
          )}

          {isTokenLimit && (
            <button
              onClick={handleContinue}
              disabled={loadingAction === 'continue'}
              style={{
                padding: '4px 10px',
                fontSize: '11.5px',
                backgroundColor: '#2563EB',
                color: '#FFFFFF',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer',
                fontWeight: 500,
              }}
            >
              ▶ Continue
            </button>
          )}

          <button
            onClick={handleCopyAll}
            style={{
              padding: '4px 9px',
              fontSize: '11.5px',
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '4px',
              cursor: 'pointer',
              color: 'var(--text-secondary)',
            }}
          >
            {copiedAll ? '✓ Copied' : 'Copy'}
          </button>

          <button
            onClick={() => handleDownload('markdown')}
            title="Download response as Markdown"
            style={{
              padding: '4px 9px',
              fontSize: '11.5px',
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '4px',
              cursor: 'pointer',
              color: 'var(--text-secondary)',
            }}
          >
            MD ↓
          </button>

          <button
            onClick={() => handleDownload('txt')}
            title="Download response as Plain Text"
            style={{
              padding: '4px 9px',
              fontSize: '11.5px',
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '4px',
              cursor: 'pointer',
              color: 'var(--text-secondary)',
            }}
          >
            TXT ↓
          </button>

          <button
            onClick={() => setSearchActive(!searchActive)}
            style={{
              padding: '4px 9px',
              fontSize: '11.5px',
              backgroundColor: searchActive ? 'var(--bg-surface-hover)' : 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '4px',
              cursor: 'pointer',
              color: 'var(--text-secondary)',
            }}
          >
            🔍
          </button>

          <button
            onClick={handleRegenerate}
            disabled={loadingAction === 'regenerate'}
            title="Regenerate this answer"
            style={{
              padding: '4px 9px',
              fontSize: '11.5px',
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '4px',
              cursor: 'pointer',
              color: 'var(--text-secondary)',
            }}
          >
            ↻
          </button>

          <button
            onClick={() => setShowMetadata(!showMetadata)}
            title="View model diagnostic metadata"
            style={{
              padding: '4px 8px',
              fontSize: '11px',
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '4px',
              cursor: 'pointer',
              color: 'var(--text-muted)',
            }}
          >
            ℹ
          </button>
        </div>
      </div>

      {/* Find in Answer Bar */}
      {searchActive && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '8px 16px',
            backgroundColor: '#FEF9C3',
            borderBottom: '1px solid #FDE047',
          }}
        >
          <span style={{ fontSize: '12px', color: '#854D0E', fontWeight: 500 }}>Find in answer:</span>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search keywords..."
            style={{
              padding: '3px 8px',
              fontSize: '12px',
              border: '1px solid #FACC15',
              borderRadius: '4px',
              outline: 'none',
              width: '200px',
            }}
          />
          <span style={{ fontSize: '11.5px', color: '#A16207' }}>
            {matchCount} {matchCount === 1 ? 'match' : 'matches'}
          </span>
          <button
            onClick={() => {
              setSearchQuery('');
              setSearchActive(false);
            }}
            style={{
              marginLeft: 'auto',
              border: 'none',
              background: 'none',
              cursor: 'pointer',
              fontSize: '12px',
              color: '#854D0E',
            }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Status banner */}
      {statusMessage && (
        <div
          style={{
            padding: '6px 16px',
            backgroundColor: '#EFF6FF',
            color: '#1D4ED8',
            fontSize: '12px',
            borderBottom: '1px solid #DBEAFE',
          }}
        >
          {statusMessage}
        </div>
      )}

      {/* Diagnostic Metadata Drawer */}
      {showMetadata && (
        <div
          style={{
            padding: '12px 16px',
            backgroundColor: '#F8FAFC',
            borderBottom: '1px solid var(--border-subtle)',
            fontSize: '12px',
            color: 'var(--text-secondary)',
            display: 'flex',
            flexWrap: 'wrap',
            gap: '16px',
          }}
        >
          <div>
            <strong>Model:</strong> {message.model_name || 'qwen2.5-coder:7b'}
          </div>
          <div>
            <strong>Response ID:</strong> {responseId || 'N/A'}
          </div>
          <div>
            <strong>Status:</strong> {message.status || 'COMPLETED'}
          </div>
          {responseId && (
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={handleToggleChunks}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#2563EB',
                  textDecoration: 'underline',
                  cursor: 'pointer',
                  fontSize: '12px',
                }}
              >
                {showChunks ? 'Hide Chunks' : 'View Chunks'}
              </button>
              <button
                onClick={handleToggleVersions}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#2563EB',
                  textDecoration: 'underline',
                  cursor: 'pointer',
                  fontSize: '12px',
                }}
              >
                {showVersions ? 'Hide Versions' : 'View Versions'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Chunks View */}
      {showChunks && chunks.length > 0 && (
        <div
          style={{
            padding: '10px 16px',
            backgroundColor: '#F1F5F9',
            borderBottom: '1px solid #CBD5E1',
            fontSize: '11.5px',
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: '6px' }}>Chunk Lineage & Diagnostics:</div>
          {chunks.map((c) => (
            <div
              key={c.chunk_id}
              style={{
                marginBottom: '4px',
                padding: '4px 8px',
                backgroundColor: '#FFFFFF',
                borderRadius: '4px',
                border: '1px solid #E2E8F0',
              }}
            >
              Chunk #{c.sequence_number} | Tokens: {c.token_count} | Stop: <code>{c.stop_reason}</code> | Time:{' '}
              {c.generation_time}s | Hash: <code>{c.content_hash.slice(0, 8)}...</code>
            </div>
          ))}
        </div>
      )}

      {/* Versions View */}
      {showVersions && versions.length > 0 && (
        <div
          style={{
            padding: '10px 16px',
            backgroundColor: '#F1F5F9',
            borderBottom: '1px solid #CBD5E1',
            fontSize: '11.5px',
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: '6px' }}>Generation History:</div>
          {versions.map((v) => (
            <div
              key={v.version_id}
              style={{
                marginBottom: '4px',
                padding: '4px 8px',
                backgroundColor: '#FFFFFF',
                borderRadius: '4px',
                border: '1px solid #E2E8F0',
                display: 'flex',
                justifyContent: 'space-between',
              }}
            >
              <span>
                Version #{v.version_number} ({v.model}) - {v.status}
              </span>
              <span>{new Date(v.created_at).toLocaleTimeString()}</span>
            </div>
          ))}
        </div>
      )}

      {/* Main Content Body with Vertical Scroll & Collapsible Sections */}
      <div
        style={{
          padding: '20px 24px',
          maxHeight: 'none',
          overflowY: 'visible',
          fontSize: '14.5px',
          color: 'var(--text-primary)',
        }}
      >
        {parsedSections.map((sec, sIdx) => {
          const isCollapsed = collapsedSections[sec.id] || false;
          const sectionText = sec.lines.join('\n');
          return (
            <div key={sec.id || sIdx} style={{ marginBottom: '18px' }}>
              {sec.title !== 'Overview' && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '6px 0',
                    borderBottom: '1px solid var(--border-subtle)',
                    marginBottom: '10px',
                  }}
                >
                  <h4
                    onClick={() => toggleSectionCollapse(sec.id)}
                    style={{
                      margin: 0,
                      fontSize: '15px',
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
                  >
                    <span>{isCollapsed ? '▶' : '▼'}</span>
                    {sec.title}
                  </h4>
                  <button
                    onClick={() => handleCopySection(sec.title, sectionText)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: copiedSection === sec.title ? '#16A34A' : 'var(--text-muted)',
                      cursor: 'pointer',
                      fontSize: '11px',
                    }}
                  >
                    {copiedSection === sec.title ? '✓ Copied' : 'Copy section'}
                  </button>
                </div>
              )}

              {!isCollapsed && <div>{renderFormattedLines(sec.lines)}</div>}
            </div>
          );
        })}
      </div>

      {/* Answer Actions & Research Follow-Up Pills */}
      <div
        style={{
          padding: '12px 20px',
          backgroundColor: 'var(--bg-surface-muted)',
          borderTop: '1px solid var(--border-subtle)',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '11.5px', fontWeight: 600, color: 'var(--text-secondary)' }}>Actions:</span>
          {['Explain', 'Summarize', 'Expand', 'Compare', 'Checklist', 'Indicators', 'Evidence', 'Report'].map((act) => (
            <button
              key={act}
              onClick={() => handleAnswerAction(act.toLowerCase())}
              disabled={Boolean(loadingAction)}
              style={{
                padding: '3px 8px',
                fontSize: '11.5px',
                borderRadius: '4px',
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
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
              {act}
            </button>
          ))}
        </div>

        {onSendFollowUp && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '11.5px', fontWeight: 600, color: 'var(--text-secondary)' }}>Follow-up:</span>
            {[
              'Explain this deeper',
              'Give an example',
              'Show defensive version',
              'Compare approaches',
              'Explain prerequisites',
              'Summarize this',
            ].map((promptText) => (
              <button
                key={promptText}
                onClick={() => onSendFollowUp(promptText)}
                style={{
                  padding: '2px 8px',
                  fontSize: '11px',
                  borderRadius: '12px',
                  backgroundColor: 'var(--bg-surface)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = 'var(--text-primary)';
                  e.currentTarget.style.borderColor = 'var(--text-secondary)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = 'var(--text-muted)';
                  e.currentTarget.style.borderColor = 'var(--border-subtle)';
                }}
              >
                + {promptText}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
