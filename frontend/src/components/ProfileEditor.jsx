import React, { useState, useEffect } from 'react'
import { Save, User, Briefcase, Code, Sparkles, Check } from 'lucide-react'

export default function ProfileEditor({ profile, onSaveProfile }) {
  const [formData, setFormData] = useState(null)
  const [activeVariantTab, setActiveVariantTab] = useState('backend')
  const [saveSuccess, setSaveSuccess] = useState(false)

  useEffect(() => {
    if (profile) {
      setFormData(JSON.parse(JSON.stringify(profile)))
    }
  }, [profile])

  if (!formData) return <div>Loading profile...</div>

  const handleBasicChange = (field, val) => {
    setFormData(prev => ({ ...prev, [field]: val }))
  }

  const handleSkillsChange = (val) => {
    const list = val.split(',').map(s => s.trim()).filter(Boolean)
    setFormData(prev => ({ ...prev, skills: list }))
  }

  const handlePreferencesChange = (field, val) => {
    setFormData(prev => ({
      ...prev,
      preferences: {
        ...prev.preferences,
        [field]: val
      }
    }))
  }

  const handleVariantChange = (variantKey, field, val) => {
    setFormData(prev => ({
      ...prev,
      curated_variants: {
        ...prev.curated_variants,
        [variantKey]: {
          ...prev.curated_variants[variantKey],
          [field]: val
        }
      }
    }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    await onSaveProfile(formData)
    setSaveSuccess(true)
    setTimeout(() => setSaveSuccess(false), 2500)
  }

  const currentVariant = formData.curated_variants?.[activeVariantTab] || {}

  return (
    <form onSubmit={handleSubmit}>
      {/* Top Banner with Save */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '1.2rem', fontWeight: '700' }}>Candidate Profile & Curated Variants Matrix</h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            Manage your authentic resume facts, 4 tailored introduction matrices, and ATS search preferences.
          </p>
        </div>
        <button type="submit" className="btn-primary">
          {saveSuccess ? <Check size={16} /> : <Save size={16} />}
          {saveSuccess ? 'Saved Successfully!' : 'Save Profile Changes'}
        </button>
      </div>

      {/* Basic Contact Info */}
      <div className="job-card" style={{ marginBottom: '20px' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: '700', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <User size={18} color="var(--accent-primary)" /> Basic Candidate Details
        </h3>
        
        <div className="form-grid">
          <div className="form-group">
            <label className="form-label">Full Name</label>
            <input 
              type="text" 
              className="form-input" 
              value={formData.full_name || ''} 
              onChange={e => handleBasicChange('full_name', e.target.value)} 
            />
          </div>
          <div className="form-group">
            <label className="form-label">Email Address</label>
            <input 
              type="email" 
              className="form-input" 
              value={formData.email || ''} 
              onChange={e => handleBasicChange('email', e.target.value)} 
            />
          </div>
          <div className="form-group">
            <label className="form-label">Phone</label>
            <input 
              type="text" 
              className="form-input" 
              value={formData.phone || ''} 
              onChange={e => handleBasicChange('phone', e.target.value)} 
            />
          </div>
          <div className="form-group">
            <label className="form-label">Location / City</label>
            <input 
              type="text" 
              className="form-input" 
              value={formData.location || ''} 
              onChange={e => handleBasicChange('location', e.target.value)} 
            />
          </div>
          <div className="form-group">
            <label className="form-label">GitHub URL</label>
            <input 
              type="text" 
              className="form-input" 
              value={formData.github_url || ''} 
              onChange={e => handleBasicChange('github_url', e.target.value)} 
            />
          </div>
          <div className="form-group">
            <label className="form-label">LinkedIn URL</label>
            <input 
              type="text" 
              className="form-input" 
              value={formData.linkedin_url || ''} 
              onChange={e => handleBasicChange('linkedin_url', e.target.value)} 
            />
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Verified Technical Skills (Comma separated)</label>
          <input 
            type="text" 
            className="form-input" 
            value={(formData.skills || []).join(', ')} 
            onChange={e => handleSkillsChange(e.target.value)} 
          />
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            These skills form the ground truth knowledge base for anti-hallucination verification.
          </span>
        </div>
      </div>

      {/* 4 Curated Profiles Matrix */}
      <div className="job-card" style={{ marginBottom: '20px' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: '700', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Sparkles size={18} color="#c084fc" /> 4 Curated Profiles Matrix (High ATS Alignment & Zero AI Bogus Claims)
        </h3>

        <div className="nav-tabs" style={{ marginBottom: '16px' }}>
          {['backend', 'sde', 'genai_ml', 'fullstack'].map(key => (
            <button
              key={key}
              type="button"
              className={`tab-button ${activeVariantTab === key ? 'active' : ''}`}
              onClick={() => setActiveVariantTab(key)}
            >
              {key === 'backend' && '⚡ Backend Engineer'}
              {key === 'sde' && '💻 General SDE / Fresher'}
              {key === 'genai_ml' && '🤖 GenAI & ML Engineer'}
              {key === 'fullstack' && '🌐 Full-Stack Engineer'}
            </button>
          ))}
        </div>

        <div className="variant-card">
          <div className="form-group">
            <label className="form-label">Profile Title</label>
            <input 
              type="text" 
              className="form-input" 
              value={currentVariant.title || ''} 
              onChange={e => handleVariantChange(activeVariantTab, 'title', e.target.value)} 
            />
          </div>

          <div className="form-group">
            <label className="form-label">Tailored Professional Summary</label>
            <textarea 
              className="form-textarea" 
              rows={4}
              value={currentVariant.summary || ''} 
              onChange={e => handleVariantChange(activeVariantTab, 'summary', e.target.value)} 
            />
          </div>

          <div className="form-group">
            <label className="form-label">Cover Letter Template</label>
            <textarea 
              className="form-textarea" 
              rows={7}
              style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}
              value={currentVariant.cover_letter_template || ''} 
              onChange={e => handleVariantChange(activeVariantTab, 'cover_letter_template', e.target.value)} 
            />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Variables available: <code>&#123;&#123; company &#125;&#125;</code>, <code>&#123;&#123; role &#125;&#125;</code>, <code>&#123;&#123; top_skills &#125;&#125;</code>, <code>&#123;&#123; top_project_bullet &#125;&#125;</code>, <code>&#123;&#123; candidate_name &#125;&#125;</code>
            </span>
          </div>
        </div>
      </div>

      {/* Search Preferences & Filters */}
      <div className="job-card" style={{ marginBottom: '20px' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: '700', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Briefcase size={18} color="var(--accent-primary)" /> Job Hunting Preferences & Hard Filters
        </h3>

        <div className="form-grid">
          <div className="form-group">
            <label className="form-label">Maximum Experience (YOE)</label>
            <input 
              type="number" 
              className="form-input" 
              value={formData.preferences?.max_yoe ?? 1} 
              onChange={e => handlePreferencesChange('max_yoe', parseInt(e.target.value) || 0)} 
            />
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Set to 1 for 0-1 YOE / Fresher roles (automatically filters out Senior/Staff/5+ YOE).
            </span>
          </div>

          <div className="form-group">
            <label className="form-label">Remote Only Filter</label>
            <select 
              className="filter-select"
              value={formData.preferences?.remote_only ? 'true' : 'false'}
              onChange={e => handlePreferencesChange('remote_only', e.target.value === 'true')}
            >
              <option value="false">All Locations (Remote + Onsite)</option>
              <option value="true">Strictly Remote Only</option>
            </select>
          </div>

          <div className="form-group" style={{ gridColumn: '1 / -1' }}>
            <label className="form-label">Preferred Locations (Comma separated)</label>
            <input 
              type="text" 
              className="form-input" 
              value={(formData.preferences?.preferred_locations || []).join(', ')} 
              onChange={e => handlePreferencesChange('preferred_locations', e.target.value.split(',').map(s => s.trim()).filter(Boolean))} 
            />
          </div>

          <div className="form-group" style={{ gridColumn: '1 / -1' }}>
            <label className="form-label">Excluded Companies / Blacklist (Comma separated)</label>
            <input 
              type="text" 
              className="form-input" 
              placeholder="e.g. BadCorp, SpamCompany"
              value={(formData.preferences?.excluded_companies || []).join(', ')} 
              onChange={e => handlePreferencesChange('excluded_companies', e.target.value.split(',').map(s => s.trim()).filter(Boolean))} 
            />
          </div>
        </div>
      </div>
    </form>
  )
}
