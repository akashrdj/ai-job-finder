import React, { useState, useEffect, useMemo } from 'react'
import {
  ExternalLink, Search, ChevronDown, ChevronRight,
  Wifi, Building2, MapPin, Briefcase, Globe, Clock, BadgeCheck, RefreshCw
} from 'lucide-react'

const SOURCE_LABELS = {
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  remoteok: 'RemoteOK',
  workday: 'Workday CXS',
  scraper_fallback: 'Web Scraper'
}

const SOURCE_COLORS = {
  greenhouse: '#4ADE80',
  lever: '#60A5FA',
  remoteok: '#F472B6',
  workday: '#A78BFA',
  scraper_fallback: '#FB923C'
}

function WorkTypeBadge({ isRemote }) {
  return isRemote ? (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      padding: '2px 10px', borderRadius: '20px', fontSize: '0.72rem', fontWeight: 700,
      background: 'rgba(74, 222, 128, 0.15)', color: '#4ADE80',
      border: '1px solid rgba(74, 222, 128, 0.35)'
    }}>
      <Wifi size={10} /> WFH / Remote
    </span>
  ) : (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      padding: '2px 10px', borderRadius: '20px', fontSize: '0.72rem', fontWeight: 700,
      background: 'rgba(251, 146, 60, 0.15)', color: '#FB923C',
      border: '1px solid rgba(251, 146, 60, 0.35)'
    }}>
      <Building2 size={10} /> On-Site
    </span>
  )
}

function JobRow({ job }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
      gap: '16px', padding: '14px 20px',
      borderBottom: '1px solid var(--border-subtle)',
      transition: 'background 0.15s ease',
      cursor: 'default'
    }}
      onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.03)'}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Title row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '6px' }}>
          <span style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--text-primary)' }}>
            {job.title}
          </span>
          <WorkTypeBadge isRemote={job.is_remote} />
          <span style={{
            padding: '1px 8px', borderRadius: '4px', fontSize: '0.68rem',
            background: SOURCE_COLORS[job.source_name] + '22',
            color: SOURCE_COLORS[job.source_name],
            border: `1px solid ${SOURCE_COLORS[job.source_name]}44`,
            fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em'
          }}>
            {SOURCE_LABELS[job.source_name] || job.source_name}
          </span>
        </div>

        {/* Location + Date */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <MapPin size={11} />
            {job.location || 'India / Location TBC'}
          </span>
          {job.posted_date && (
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Clock size={11} />
              {new Date(job.posted_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
            </span>
          )}
          {(job.salary_min || job.salary_max) && (
            <span style={{ color: '#4ADE80', fontWeight: 600 }}>
              {job.salary_min ? `$${Math.round(job.salary_min / 1000)}k` : ''}
              {job.salary_min && job.salary_max ? ' – ' : ''}
              {job.salary_max ? `$${Math.round(job.salary_max / 1000)}k` : ''}
              {' '}{job.salary_currency}
            </span>
          )}
        </div>

        {/* Description snippet */}
        {job.description_snippet && (
          <p style={{
            marginTop: '6px', fontSize: '0.78rem', color: 'var(--text-muted)',
            lineHeight: 1.5, maxWidth: '680px',
            display: '-webkit-box', WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical', overflow: 'hidden'
          }}>
            {job.description_snippet}
          </p>
        )}
      </div>

      {/* Apply Button */}
      <a
        href={job.url}
        target="_blank"
        rel="noopener noreferrer"
        onClick={e => e.stopPropagation()}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: '6px',
          padding: '8px 16px', borderRadius: '8px', fontSize: '0.82rem', fontWeight: 700,
          background: 'var(--accent)', color: '#fff',
          textDecoration: 'none', whiteSpace: 'nowrap', flexShrink: 0,
          border: '1px solid transparent',
          transition: 'opacity 0.15s ease',
        }}
        onMouseEnter={e => e.currentTarget.style.opacity = '0.85'}
        onMouseLeave={e => e.currentTarget.style.opacity = '1'}
      >
        <ExternalLink size={13} /> Apply Now →
      </a>
    </div>
  )
}

function CompanyAccordion({ group, defaultOpen = false }) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  const { company, jobs, wfh_count, onsite_count } = group

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden',
      marginBottom: '10px',
      transition: 'box-shadow 0.2s ease'
    }}>
      {/* Company Header — click to expand */}
      <button
        onClick={() => setIsOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: '14px',
          padding: '16px 20px', background: 'none', border: 'none',
          cursor: 'pointer', textAlign: 'left',
          borderBottom: isOpen ? '1px solid var(--border-subtle)' : 'none'
        }}
      >
        {/* Chevron */}
        <span style={{ color: 'var(--text-secondary)', flexShrink: 0 }}>
          {isOpen ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </span>

        {/* Company name */}
        <span style={{ fontWeight: 700, fontSize: '1.0rem', color: 'var(--text-primary)', flex: 1 }}>
          {company}
        </span>

        {/* Counters */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: '5px',
            padding: '3px 12px', borderRadius: '20px', fontSize: '0.75rem', fontWeight: 700,
            background: 'rgba(74, 222, 128, 0.12)', color: '#4ADE80',
            border: '1px solid rgba(74, 222, 128, 0.3)'
          }}>
            <Wifi size={10} /> {wfh_count} WFH
          </span>
          <span style={{
            display: 'inline-flex', alignItems: 'center', gap: '5px',
            padding: '3px 12px', borderRadius: '20px', fontSize: '0.75rem', fontWeight: 700,
            background: 'rgba(251, 146, 60, 0.12)', color: '#FB923C',
            border: '1px solid rgba(251, 146, 60, 0.3)'
          }}>
            <Building2 size={10} /> {onsite_count} On-Site
          </span>
          <span style={{
            padding: '3px 12px', borderRadius: '20px', fontSize: '0.75rem', fontWeight: 700,
            background: 'rgba(255,255,255,0.07)', color: 'var(--text-secondary)',
            border: '1px solid var(--border-subtle)'
          }}>
            {jobs.length} role{jobs.length !== 1 ? 's' : ''}
          </span>
        </div>
      </button>

      {/* Jobs list — hidden until expanded */}
      {isOpen && (
        <div>
          {jobs.map(job => (
            <JobRow key={job.id} job={job} />
          ))}
        </div>
      )}
    </div>
  )
}


export default function JobsExplorer({ jobs }) {
  const [search, setSearch] = useState('')
  const [workTypeFilter, setWorkTypeFilter] = useState('all') // 'all' | 'wfh' | 'onsite'
  const [sourceFilter, setSourceFilter] = useState('all')
  const [grouped, setGrouped] = useState([])
  const [loading, setLoading] = useState(false)

  // Fetch grouped data from /api/jobs/grouped
  const fetchGrouped = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (workTypeFilter !== 'all') params.append('work_type', workTypeFilter)
      if (sourceFilter !== 'all') params.append('source', sourceFilter)
      if (search) params.append('search', search)
      const res = await fetch(`/api/jobs/grouped?${params.toString()}`)
      const data = await res.json()
      setGrouped(Array.isArray(data) ? data : [])
    } catch (e) {
      console.error('Failed to fetch grouped jobs:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchGrouped()
  }, [workTypeFilter, sourceFilter, search])

  const totalJobs = useMemo(() => grouped.reduce((s, g) => s + g.jobs.length, 0), [grouped])
  const totalWFH = useMemo(() => grouped.reduce((s, g) => s + g.wfh_count, 0), [grouped])
  const totalOnsite = useMemo(() => grouped.reduce((s, g) => s + g.onsite_count, 0), [grouped])

  return (
    <div>
      {/* ── Top stats bar ────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap'
      }}>
        {[
          { label: 'Total Roles', value: totalJobs, color: 'var(--accent)', icon: <Briefcase size={14} /> },
          { label: 'WFH / Remote', value: totalWFH, color: '#4ADE80', icon: <Wifi size={14} /> },
          { label: 'On-Site', value: totalOnsite, color: '#FB923C', icon: <Building2 size={14} /> },
          { label: 'Companies', value: grouped.length, color: '#60A5FA', icon: <Globe size={14} /> },
        ].map(stat => (
          <div key={stat.label} style={{
            flex: '1', minWidth: '140px',
            padding: '14px 18px',
            background: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-lg)',
            display: 'flex', alignItems: 'center', gap: '10px'
          }}>
            <span style={{ color: stat.color }}>{stat.icon}</span>
            <div>
              <div style={{ fontSize: '1.3rem', fontWeight: 800, color: stat.color }}>{stat.value}</div>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>{stat.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ── Toolbar ──────────────────────────────────────────────────── */}
      <div className="toolbar" style={{ marginBottom: '16px' }}>
        <div className="toolbar-group">
          {/* Search */}
          <div style={{ position: 'relative' }}>
            <Search size={14} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input
              type="text"
              className="search-input"
              placeholder="Search by role or company..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ paddingLeft: '36px' }}
            />
          </div>

          {/* Source filter */}
          <select className="filter-select" value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}>
            <option value="all">All Sources</option>
            <option value="greenhouse">Greenhouse</option>
            <option value="lever">Lever</option>
            <option value="remoteok">RemoteOK</option>
            <option value="workday">Workday CXS</option>
            <option value="scraper_fallback">Web Scraper</option>
          </select>
        </div>

        {/* Work Type Toggle */}
        <div style={{ display: 'flex', gap: '6px' }}>
          {[
            { key: 'all', label: '🌐 All Jobs' },
            { key: 'wfh', label: '🏠 WFH / Remote' },
            { key: 'onsite', label: '🏢 On-Site' },
          ].map(opt => (
            <button
              key={opt.key}
              onClick={() => setWorkTypeFilter(opt.key)}
              style={{
                padding: '7px 16px', borderRadius: '8px', border: '1px solid',
                fontSize: '0.82rem', fontWeight: 600, cursor: 'pointer',
                transition: 'all 0.15s ease',
                background: workTypeFilter === opt.key ? 'var(--accent)' : 'var(--bg-card)',
                borderColor: workTypeFilter === opt.key ? 'var(--accent)' : 'var(--border-subtle)',
                color: workTypeFilter === opt.key ? '#fff' : 'var(--text-secondary)',
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Company Accordion List ─────────────────────────────────── */}
      {loading ? (
        <div className="empty-state">
          <RefreshCw size={30} className="empty-state-icon animate-spin" />
          <p>Fetching grouped jobs...</p>
        </div>
      ) : grouped.length === 0 ? (
        <div className="empty-state">
          <Building2 size={36} className="empty-state-icon" />
          <h3>No jobs found</h3>
          <p>Click "Sync Jobs Now" in the header to fetch live India + remote tech roles.</p>
        </div>
      ) : (
        <div>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '14px' }}>
            Showing <strong style={{ color: 'var(--text-primary)' }}>{grouped.length}</strong> companies
            · <strong style={{ color: '#4ADE80' }}>{totalWFH} WFH</strong>
            · <strong style={{ color: '#FB923C' }}>{totalOnsite} On-Site</strong>
            · <strong style={{ color: 'var(--accent)' }}>{totalJobs} total roles</strong>
            · sorted A–Z
          </p>
          {grouped.map((group, idx) => (
            <CompanyAccordion key={group.company} group={group} defaultOpen={idx < 2} />
          ))}
        </div>
      )}
    </div>
  )
}
