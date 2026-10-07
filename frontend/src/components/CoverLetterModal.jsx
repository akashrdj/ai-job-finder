import React, { useState } from 'react'
import { X, Copy, Check, ShieldCheck, AlertTriangle } from 'lucide-react'

export default function CoverLetterModal({ draft, onClose, onOpenClaimReport }) {
  const [copied, setCopied] = useState(false)
  if (!draft) return null

  const handleCopy = () => {
    navigator.clipboard.writeText(draft.cover_letter)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const isVerified = draft.claim_validation_status === 'PASSED'

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '750px' }}>
        <div className="modal-header">
          <div>
            <h2 className="modal-title">✉️ Tailored Cover Letter</h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                {draft.job?.title} at <strong>{draft.job?.company}</strong>
              </span>
              <button 
                onClick={onOpenClaimReport}
                className={`tag ${isVerified ? 'verified' : 'flagged'}`} 
                style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
              >
                {isVerified ? <ShieldCheck size={12} /> : <AlertTriangle size={12} />}
                {isVerified ? '100% Verified Profile Facts' : 'Review Flagged Claims'}
              </button>
            </div>
          </div>
          <button className="btn-secondary" onClick={onClose} style={{ padding: '4px 8px' }}>
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          <div style={{
            background: 'var(--bg-surface-subtle)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: '20px',
            fontFamily: 'var(--font-sans)',
            fontSize: '0.95rem',
            lineHeight: '1.7',
            whiteSpace: 'pre-wrap',
            color: 'var(--text-primary)'
          }}>
            {draft.cover_letter}
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-primary" onClick={handleCopy}>
            {copied ? <Check size={16} /> : <Copy size={16} />}
            {copied ? 'Copied to Clipboard!' : 'Copy Cover Letter'}
          </button>
          <button className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
