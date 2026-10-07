import React, { useState } from 'react'
import {
  ExternalLink, FileText, Mail, ShieldCheck, AlertTriangle, Users, Copy, Check,
  ChevronDown, ChevronUp, CheckCircle, RefreshCw, Archive
} from 'lucide-react'
import GapAnalysisPanel from './GapAnalysisPanel'

export default function DraftReviewCard({
  draft,
  onOpenResumeDiff,
  onOpenCoverLetter,
  onOpenClaimReport,
  onUpdateAction,
  onRegenerate
}) {
  const [showRationale, setShowRationale] = useState(false)
  const [showOutreach, setShowOutreach] = useState(false)
  const [copiedPitch, setCopiedPitch] = useState(false)
  const [copiedEmail, setCopiedEmail] = useState(false)

  const job = draft.job || {}
  const matchScore = draft.match_score || {}
  const score = matchScore.score || 0
  const outreach = draft.outreach_kit || {}

  const scoreClass = score >= 80 ? 'score-high' : score >= 60 ? 'score-med' : 'score-low'
  const isPassed = draft.claim_validation_status === 'PASSED'
  const isApplied = draft.user_action === 'applied'
  const isDismissed = draft.user_action === 'dismissed'

  const copyToClipboard = (text, type) => {
    navigator.clipboard.writeText(text)
    if (type === 'pitch') {
      setCopiedPitch(true)
      setTimeout(() => setCopiedPitch(false), 2000)
    } else {
      setCopiedEmail(true)
      setTimeout(() => setCopiedEmail(false), 2000)
    }
  }

  return (
    <div className={`job-card ${isApplied ? 'applied' : ''} ${isDismissed ? 'dismissed' : ''}`}>
      {/* Header Row */}
      <div className="card-header">
        <div className="card-title-group">
          <h3 className="job-title">{job.title}</h3>
          <div className="job-meta">
            <span className="meta-item" style={{ fontWeight: '600', color: 'var(--text-primary)' }}>
              🏢 {job.company}
            </span>
            <span className="meta-item">📍 {job.location || 'Location Not Specified'}</span>
            {job.is_remote && <span className="tag verified">🌐 Remote</span>}
            <span className="meta-item">Source: {job.source_name}</span>
          </div>

          <div className="tag-list">
            <span className="tag variant">
              Profile: {matchScore.selected_variant?.toUpperCase() || 'SDE'}
            </span>
            <span 
              className={`tag ${isPassed ? 'verified' : 'flagged'}`}
              style={{ cursor: 'pointer' }}
              onClick={() => onOpenClaimReport(draft)}
            >
              {isPassed ? <ShieldCheck size={12} style={{ display: 'inline', marginRight: '4px' }} /> : <AlertTriangle size={12} style={{ display: 'inline', marginRight: '4px' }} />}
              {isPassed ? 'Zero Hallucinations (Verified)' : 'Claims Flagged'}
            </span>
            {(matchScore.matched_skills || []).slice(0, 4).map((s, idx) => (
              <span key={idx} className="tag">✓ {s}</span>
            ))}
          </div>
        </div>

        {/* Score Badge */}
        <div className={`score-badge ${scoreClass}`}>
          <div>{score}</div>
          <div className="score-label">Fit Score</div>
        </div>
      </div>

      {/* Rationale Toggle */}
      {matchScore.rationale && (
        <div style={{ marginBottom: '12px' }}>
          <button 
            className="btn-secondary" 
            onClick={() => setShowRationale(!showRationale)}
            style={{ padding: '4px 10px', fontSize: '0.78rem' }}
          >
            {showRationale ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            {showRationale ? 'Hide Match Rationale' : 'Why this matched (ATS Breakdown)'}
          </button>
          
          {showRationale && (
            <div className="rationale-box" style={{ marginTop: '8px' }}>
              <div style={{ whiteSpace: 'pre-line' }}>{matchScore.rationale}</div>
            </div>
          )}
        </div>
      )}

      {/* Resume Gap Analysis Panel */}
      <GapAnalysisPanel
        matchId={matchScore.id}
        matchedSkills={matchScore.matched_skills || []}
        missingRequirements={matchScore.missing_requirements || []}
        existingGapReport={matchScore.gap_report || null}
      />

      {/* Referral & Outreach Box */}
      {showOutreach && (
        <div className="outreach-box">
          <div className="outreach-title">
            <Users size={18} color="var(--accent-primary)" />
            <span>Referral & Cold Outreach Kit for {job.company}</span>
          </div>

          <div className="outreach-grid">
            {/* 1-Click LinkedIn Searches */}
            <div className="outreach-card">
              <div className="outreach-card-title">🔍 1-Click LinkedIn Search Links</div>
              <div className="link-button-group">
                {outreach.linkedin_search_links?.search_recruiters && (
                  <a href={outreach.linkedin_search_links.search_recruiters} target="_blank" rel="noopener noreferrer" className="external-search-link">
                    <ExternalLink size={13} /> Find Recruiters at {job.company}
                  </a>
                )}
                {outreach.linkedin_search_links?.search_engineering_managers && (
                  <a href={outreach.linkedin_search_links.search_engineering_managers} target="_blank" rel="noopener noreferrer" className="external-search-link">
                    <ExternalLink size={13} /> Find Engineering Managers at {job.company}
                  </a>
                )}
                {outreach.linkedin_search_links?.search_alumni && (
                  <a href={outreach.linkedin_search_links.search_alumni} target="_blank" rel="noopener noreferrer" className="external-search-link">
                    <ExternalLink size={13} /> Find College Alumni at {job.company}
                  </a>
                )}
              </div>
            </div>

            {/* Email Patterns & Contacts */}
            <div className="outreach-card">
              <div className="outreach-card-title">📧 Company Email Syntax</div>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                Standard Syntax: <code>{outreach.email_patterns?.[0] || `first.last@${outreach.domain_guess}`}</code>
              </div>
              {outreach.verified_contacts?.length > 0 ? (
                <div style={{ fontSize: '0.75rem' }}>
                  <strong>Verified Contacts:</strong>
                  {outreach.verified_contacts.map((c, i) => (
                    <div key={i} style={{ marginTop: '4px' }}>
                      {c.name} ({c.position}): <code>{c.email}</code>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Add Hunter.io API key in backend .env to auto-fetch verified recruiter inboxes.
                </div>
              )}
            </div>

            {/* LinkedIn Short DM */}
            <div className="outreach-card" style={{ gridColumn: '1 / -1' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <div className="outreach-card-title">✉️ Tailored LinkedIn Referral Note (&lt;300 chars)</div>
                <button 
                  className="btn-secondary" 
                  onClick={() => copyToClipboard(outreach.linkedin_pitch, 'pitch')}
                  style={{ padding: '2px 8px', fontSize: '0.75rem' }}
                >
                  {copiedPitch ? <Check size={12} /> : <Copy size={12} />}
                  {copiedPitch ? 'Copied' : 'Copy Pitch'}
                </button>
              </div>
              <div className="copy-box">{outreach.linkedin_pitch}</div>
            </div>
          </div>
        </div>
      )}

      {/* Card Action Buttons */}
      <div className="card-actions">
        <div className="actions-left">
          {/* Direct Apply Button */}
          <a 
            href={job.url} 
            target="_blank" 
            rel="noopener noreferrer" 
            className="btn-apply"
            title="Opens the official company application page in a new tab"
          >
            <ExternalLink size={15} /> Apply on Company Portal
          </a>

          {/* View Cover Letter */}
          <button className="btn-secondary" onClick={() => onOpenCoverLetter(draft)}>
            <Mail size={15} /> Cover Letter
          </button>

          {/* View Resume Diff */}
          <button className="btn-secondary" onClick={() => onOpenResumeDiff(draft)}>
            <FileText size={15} /> Resume Diff
          </button>

          {/* Toggle Outreach Kit */}
          <button className="btn-secondary" onClick={() => setShowOutreach(!showOutreach)}>
            <Users size={15} /> {showOutreach ? 'Close Referral Kit' : 'Referral & HR Contacts'}
          </button>
        </div>

        <div className="actions-right">
          {isApplied ? (
            <span className="tag verified" style={{ padding: '6px 12px', fontSize: '0.82rem' }}>
              ✓ Applied Manually
            </span>
          ) : (
            <button 
              className="btn-secondary"
              onClick={() => onUpdateAction(draft.id, 'applied')}
              style={{ color: 'var(--success-text)', borderColor: 'var(--success-border)' }}
            >
              <CheckCircle size={15} /> Mark Applied
            </button>
          )}

          {!isDismissed ? (
            <button 
              className="btn-secondary"
              onClick={() => onUpdateAction(draft.id, 'dismissed')}
              style={{ color: 'var(--text-muted)' }}
              title="Dismiss job from active queue"
            >
              <Archive size={15} /> Dismiss
            </button>
          ) : (
            <button 
              className="btn-secondary"
              onClick={() => onUpdateAction(draft.id, 'pending')}
            >
              Restore
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
