import React, { useState, useEffect } from 'react'
import {
  Briefcase, Sparkles, RefreshCw, Layers, User, Search, Filter, ShieldCheck,
  CheckCircle2, Clock, Globe
} from 'lucide-react'

import DraftReviewCard from './components/DraftReviewCard'
import ResumeDiffModal from './components/ResumeDiffModal'
import CoverLetterModal from './components/CoverLetterModal'
import ClaimReportModal from './components/ClaimReportModal'
import ProfileEditor from './components/ProfileEditor'
import JobsExplorer from './components/JobsExplorer'

export default function App() {
  const [activeTab, setActiveTab] = useState('queue') // 'queue', 'jobs', 'profile'
  const [drafts, setDrafts] = useState([])
  const [jobs, setJobs] = useState([])
  const [profile, setProfile] = useState(null)
  const [pipelineStatus, setPipelineStatus] = useState(null)
  
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)

  // Filters for review queue
  const [queueFilter, setQueueFilter] = useState('pending') // 'pending', 'applied', 'dismissed', 'all'
  const [minScoreFilter, setMinScoreFilter] = useState(0)
  const [searchQuery, setSearchQuery] = useState('')

  // Modals state
  const [selectedResumeDiff, setSelectedResumeDiff] = useState(null)
  const [selectedCoverLetter, setSelectedCoverLetter] = useState(null)
  const [selectedClaimReport, setSelectedClaimReport] = useState(null)

  const loadAllData = async () => {
    setLoading(true)
    try {
      const [draftsRes, jobsRes, profileRes, statusRes] = await Promise.all([
        fetch('/api/drafts').then(r => r.json()),
        fetch('/api/jobs?limit=100').then(r => r.json()),
        fetch('/api/profile').then(r => r.json()),
        fetch('/api/ingest/status').then(r => r.json())
      ])

      setDrafts(Array.isArray(draftsRes) ? draftsRes : [])
      setJobs(Array.isArray(jobsRes) ? jobsRes : [])
      setProfile(profileRes)
      setPipelineStatus(statusRes)
    } catch (err) {
      console.error('Error loading data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAllData()
  }, [])

  const handleSyncNow = async () => {
    setSyncing(true)
    try {
      await fetch('/api/ingest/run', { method: 'POST' })
      // Poll after 3 seconds to get fresh results
      setTimeout(async () => {
        await loadAllData()
        setSyncing(false)
      }, 3500)
    } catch (e) {
      console.error(e)
      setSyncing(false)
    }
  }

  const handleUpdateDraftAction = async (draftId, action) => {
    try {
      const res = await fetch(`/api/drafts/${draftId}/action`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_action: action })
      })
      const updated = await res.json()
      setDrafts(prev => prev.map(d => (d.id === draftId ? updated : d)))
    } catch (e) {
      console.error('Failed to update draft action:', e)
    }
  }

  const handleSaveProfile = async (newProfile) => {
    try {
      const res = await fetch('/api/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newProfile)
      })
      const saved = await res.json()
      setProfile(saved)
    } catch (e) {
      console.error('Failed to save profile:', e)
    }
  }

  // Filtered drafts in Review Queue
  const filteredDrafts = drafts.filter(d => {
    const matchesAction = queueFilter === 'all' || d.user_action === queueFilter
    const matchesScore = (d.match_score?.score || 0) >= minScoreFilter
    const matchesSearch = !searchQuery || 
      d.job?.title?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      d.job?.company?.toLowerCase().includes(searchQuery.toLowerCase())
    return matchesAction && matchesScore && matchesSearch
  })

  const pendingCount = drafts.filter(d => d.user_action === 'pending').length
  const appliedCount = drafts.filter(d => d.user_action === 'applied').length

  return (
    <div className="app-container">
      {/* Header Bar */}
      <header className="header-bar">
        <div className="brand-section">
          <div className="brand-icon">
            <Sparkles size={24} />
          </div>
          <div>
            <h1 className="brand-title">AI Job Finder & Application Drafter</h1>
            <p className="brand-subtitle">
              Fact-Grounded Job Matching • 4 Curated Profiles Matrix • Zero Auto-Submission Guardrail
            </p>
          </div>
        </div>

        <div className="header-controls">
          <div className="status-pill">
            <span className="status-dot"></span>
            <span>Scheduler Active (Every 15m)</span>
          </div>

          <button 
            className="btn-primary" 
            onClick={handleSyncNow} 
            disabled={syncing}
          >
            <RefreshCw size={16} className={syncing ? 'animate-spin' : ''} />
            {syncing ? 'Fetching & Matching...' : 'Sync Jobs Now'}
          </button>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav className="nav-tabs">
        <button 
          className={`tab-button ${activeTab === 'queue' ? 'active' : ''}`}
          onClick={() => setActiveTab('queue')}
        >
          <Layers size={18} />
          <span>Review Queue</span>
          <span className="tab-badge">{pendingCount} Pending</span>
        </button>

        <button 
          className={`tab-button ${activeTab === 'jobs' ? 'active' : ''}`}
          onClick={() => setActiveTab('jobs')}
        >
          <Search size={18} />
          <span>All Ingested Jobs</span>
          <span className="tab-badge">{jobs.length} Total</span>
        </button>

        <button 
          className={`tab-button ${activeTab === 'profile' ? 'active' : ''}`}
          onClick={() => setActiveTab('profile')}
        >
          <User size={18} />
          <span>My Profile & 4 Matrix Variants</span>
        </button>
      </nav>

      {/* Main Tab Content */}
      <main>
        {activeTab === 'queue' && (
          <div>
            {/* Toolbar for Queue */}
            <div className="toolbar">
              <div className="toolbar-group">
                <input
                  type="text"
                  className="search-input"
                  placeholder="Search review queue..."
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                />

                <select 
                  className="filter-select"
                  value={queueFilter}
                  onChange={e => setQueueFilter(e.target.value)}
                >
                  <option value="pending">Pending Review ({pendingCount})</option>
                  <option value="applied">Applied ({appliedCount})</option>
                  <option value="dismissed">Dismissed</option>
                  <option value="all">All Drafts ({drafts.length})</option>
                </select>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  <span>Min Fit Score: <strong>{minScoreFilter}%</strong></span>
                  <input
                    type="range"
                    min="0"
                    max="90"
                    step="5"
                    value={minScoreFilter}
                    onChange={e => setMinScoreFilter(parseInt(e.target.value))}
                    style={{ cursor: 'pointer' }}
                  />
                </div>
              </div>

              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Showing <strong>{filteredDrafts.length}</strong> drafted applications
              </div>
            </div>

            {/* Draft Cards List */}
            <div className="cards-grid">
              {filteredDrafts.length === 0 ? (
                <div className="empty-state">
                  <Briefcase size={40} className="empty-state-icon" />
                  <h3>No applications drafted in this view</h3>
                  <p>Click "Sync Jobs Now" to fetch the latest fresher / 0-1 YOE postings and generate tailored drafts.</p>
                </div>
              ) : (
                filteredDrafts.map(draft => (
                  <DraftReviewCard
                    key={draft.id}
                    draft={draft}
                    onOpenResumeDiff={(d) => setSelectedResumeDiff(d)}
                    onOpenCoverLetter={(d) => setSelectedCoverLetter(d)}
                    onOpenClaimReport={(d) => setSelectedClaimReport(d)}
                    onUpdateAction={handleUpdateDraftAction}
                  />
                ))
              )}
            </div>
          </div>
        )}

        {activeTab === 'jobs' && (
          <JobsExplorer jobs={jobs} />
        )}

        {activeTab === 'profile' && (
          <ProfileEditor profile={profile} onSaveProfile={handleSaveProfile} />
        )}
      </main>

      {/* Modals */}
      {selectedResumeDiff && (
        <ResumeDiffModal
          draft={selectedResumeDiff}
          profile={profile}
          onClose={() => setSelectedResumeDiff(null)}
        />
      )}

      {selectedCoverLetter && (
        <CoverLetterModal
          draft={selectedCoverLetter}
          onClose={() => setSelectedCoverLetter(null)}
          onOpenClaimReport={() => {
            setSelectedClaimReport(selectedCoverLetter)
            setSelectedCoverLetter(null)
          }}
        />
      )}

      {selectedClaimReport && (
        <ClaimReportModal
          draft={selectedClaimReport}
          onClose={() => setSelectedClaimReport(null)}
        />
      )}
    </div>
  )
}
