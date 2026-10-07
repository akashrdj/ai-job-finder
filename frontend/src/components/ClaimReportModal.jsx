import React from 'react'
import { X, ShieldCheck, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'

export default function ClaimReportModal({ draft, onClose }) {
  if (!draft) return null

  const report = draft.claim_validation_report || {}
  const claims = report.claims_breakdown || []
  const isPassed = draft.claim_validation_status === 'PASSED'

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '800px' }}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {isPassed ? (
              <ShieldCheck size={26} color="var(--success-text)" />
            ) : (
              <AlertTriangle size={26} color="var(--warning-text)" />
            )}
            <div>
              <h2 className="modal-title">Anti-Hallucination Claim Validation Trace</h2>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                {isPassed ? 'All claims deterministically verified against your stored profile.' : 'Some claims could not be verified against your profile.'}
              </p>
            </div>
          </div>
          <button className="btn-secondary" onClick={onClose} style={{ padding: '4px 8px' }}>
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          {/* Summary metrics */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', marginBottom: '20px' }}>
            <div style={{ background: 'var(--bg-surface-subtle)', padding: '12px', borderRadius: 'var(--radius-md)', textAlign: 'center', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Total Claims Checked</div>
              <div style={{ fontSize: '1.4rem', fontWeight: '800' }}>{report.total_claims_checked || 0}</div>
            </div>
            <div style={{ background: 'var(--success-bg)', padding: '12px', borderRadius: 'var(--radius-md)', textAlign: 'center', border: '1px solid var(--success-border)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--success-text)', textTransform: 'uppercase' }}>Verified Profile Facts</div>
              <div style={{ fontSize: '1.4rem', fontWeight: '800', color: 'var(--success-text)' }}>{report.verified_claims_count || 0}</div>
            </div>
            <div style={{ background: (report.flagged_claims_count > 0 ? 'var(--warning-bg)' : 'var(--bg-surface-subtle)'), padding: '12px', borderRadius: 'var(--radius-md)', textAlign: 'center', border: '1px solid var(--border-subtle)' }}>
              <div style={{ fontSize: '0.75rem', color: (report.flagged_claims_count > 0 ? 'var(--warning-text)' : 'var(--text-muted)'), textTransform: 'uppercase' }}>Unverified / Flagged</div>
              <div style={{ fontSize: '1.4rem', fontWeight: '800', color: (report.flagged_claims_count > 0 ? 'var(--warning-text)' : 'var(--text-muted)') }}>{report.flagged_claims_count || 0}</div>
            </div>
          </div>

          {/* Claims breakdown list */}
          <h4 style={{ fontSize: '0.85rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '10px' }}>
            Extracted Factual Assertions & Verification Source:
          </h4>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {claims.map((c, idx) => {
              const verified = c.status === 'VERIFIED'
              return (
                <div 
                  key={idx} 
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px',
                    padding: '10px 14px',
                    borderRadius: 'var(--radius-sm)',
                    background: verified ? 'var(--bg-surface-subtle)' : 'var(--warning-bg)',
                    border: `1px solid ${verified ? 'var(--border-subtle)' : 'var(--warning-border)'}`
                  }}
                >
                  {verified ? (
                    <CheckCircle2 size={18} color="var(--success-text)" style={{ marginTop: '2px', flexShrink: 0 }} />
                  ) : (
                    <XCircle size={18} color="var(--warning-text)" style={{ marginTop: '2px', flexShrink: 0 }} />
                  )}
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ fontSize: '0.9rem' }}>{c.entity}</strong>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{c.claim_type}</span>
                    </div>
                    <div style={{ fontSize: '0.8rem', color: verified ? 'var(--text-secondary)' : 'var(--warning-text)', marginTop: '2px' }}>
                      Source: {c.source_fact}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
