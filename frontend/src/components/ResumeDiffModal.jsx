import React from 'react'
import { X, CheckCircle2, ArrowRight } from 'lucide-react'

export default function ResumeDiffModal({ draft, profile, onClose }) {
  if (!draft) return null

  const tailoredResume = draft.resume_variant || {}
  const targetRole = tailoredResume.target_role || draft.job?.title
  const targetCompany = tailoredResume.target_company || draft.job?.company
  const tailoredSkills = tailoredResume.skills || []
  const baseSkills = profile?.skills || []

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '900px' }}>
        <div className="modal-header">
          <div>
            <h2 className="modal-title">📄 Tailored Resume Diff & Alignment</h2>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              Targeting: <strong>{targetRole}</strong> at <strong>{targetCompany}</strong>
            </p>
          </div>
          <button className="btn-secondary" onClick={onClose} style={{ padding: '4px 8px' }}>
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          {/* Summary Alignment */}
          <div style={{ marginBottom: '20px' }}>
            <h4 style={{ fontSize: '0.85rem', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '8px' }}>
              Selected Focus Summary ({draft.match_score?.selected_variant?.toUpperCase()})
            </h4>
            <div style={{ background: 'var(--bg-surface-subtle)', padding: '12px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
              {tailoredResume.professional_summary}
            </div>
          </div>

          {/* Side by Side Diff */}
          <div className="diff-grid">
            {/* Left: Base Profile */}
            <div className="diff-col">
              <div className="diff-col-title">Base Profile (Verified Pool)</div>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '8px' }}>
                Skills ({baseSkills.length}):
              </p>
              <div className="tag-list" style={{ marginBottom: '16px' }}>
                {baseSkills.map((s, idx) => (
                  <span key={idx} className="tag">{s}</span>
                ))}
              </div>

              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '8px' }}>
                Projects ({profile?.projects?.length || 0}):
              </p>
              {(profile?.projects || []).map((p, idx) => (
                <div key={idx} style={{ marginBottom: '10px', fontSize: '0.82rem' }}>
                  <strong>{p.name}</strong>
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>{p.tech_stack?.join(', ')}</div>
                </div>
              ))}
            </div>

            {/* Right: Tailored Alignment */}
            <div className="diff-col" style={{ borderColor: 'var(--border-strong)' }}>
              <div className="diff-col-title" style={{ color: 'var(--accent-primary)' }}>
                Tailored for Job (ATS Keywords Prioritized)
              </div>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '8px' }}>
                Re-ranked Skills (Matched First):
              </p>
              <div className="tag-list" style={{ marginBottom: '16px' }}>
                {tailoredSkills.map((s, idx) => {
                  const isMatched = draft.match_score?.matched_skills?.includes(s)
                  return (
                    <span key={idx} className={`tag ${isMatched ? 'verified' : ''}`}>
                      {isMatched ? '✓ ' : ''}{s}
                    </span>
                  )
                })}
              </div>

              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '8px' }}>
                Re-ordered Project Priority:
              </p>
              {(tailoredResume.projects || []).map((p, idx) => (
                <div key={idx} style={{ marginBottom: '10px', fontSize: '0.82rem', background: 'var(--bg-surface-elevated)', padding: '8px', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <strong>{idx + 1}. {p.name}</strong>
                    <span style={{ fontSize: '0.75rem', color: 'var(--success-text)' }}>Prioritized Match</span>
                  </div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', marginTop: '4px' }}>
                    Stack: {p.tech_stack?.join(', ')}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-primary" onClick={() => {
            navigator.clipboard.writeText(JSON.stringify(tailoredResume, null, 2))
            alert("Tailored Resume JSON copied to clipboard!")
          }}>
            Copy Tailored Resume Data
          </button>
          <button className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
