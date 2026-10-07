import React, { useState } from "react"
import { Copy, Check, Lightbulb, XCircle, CheckCircle2, TrendingUp } from "lucide-react"

export default function GapAnalysisPanel({ matchId, matchedSkills = [], missingRequirements = [], existingGapReport = null }) {
  const [loading, setLoading] = useState(false)
  const [gapReport, setGapReport] = useState(existingGapReport)
  const [copiedKeyword, setCopiedKeyword] = useState(null)
  const [error, setError] = useState(null)

  const runAnalysis = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/matches/${matchId}/analyze-gap`, { method: "POST" })
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const data = await res.json()
      setGapReport(data.gap_report)
    } catch (e) {
      setError("Gap analysis failed. Check that the backend is running.")
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const copyKeyword = (kw) => {
    navigator.clipboard.writeText(kw)
    setCopiedKeyword(kw)
    setTimeout(() => setCopiedKeyword(null), 1500)
  }

  const hasMissingTech = gapReport?.missing_technical_keywords?.length > 0
  const hasMissingSoft = gapReport?.missing_soft_skills?.length > 0
  const hasTips = gapReport?.resume_tips?.length > 0

  return (
    <div style={{
      marginTop: "12px",
      borderTop: "1px solid var(--border-subtle)",
      paddingTop: "12px",
    }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "10px", flexWrap: "wrap" }}>
        <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: "5px" }}>
          <TrendingUp size={14} /> Resume Gap Analysis
        </span>

        {!gapReport && (
          <button
            onClick={runAnalysis}
            disabled={loading}
            style={{
              padding: "4px 12px", borderRadius: "6px", fontSize: "0.78rem", fontWeight: 700,
              background: loading ? "rgba(139,92,246,0.15)" : "rgba(139,92,246,0.2)",
              color: "#a78bfa", border: "1px solid rgba(139,92,246,0.4)",
              cursor: loading ? "not-allowed" : "pointer",
              display: "flex", alignItems: "center", gap: "5px", transition: "all 0.15s"
            }}
          >
            {loading ? (
              <>
                <span style={{ display: "inline-block", animation: "spin 1s linear infinite", fontSize: "0.9rem" }}>⟳</span>
                Gemini is analyzing...
              </>
            ) : "✦ Analyze Resume Gap"}
          </button>
        )}

        {gapReport && (
          <button
            onClick={runAnalysis}
            disabled={loading}
            style={{
              padding: "3px 8px", borderRadius: "5px", fontSize: "0.72rem", fontWeight: 600,
              background: "transparent", color: "var(--text-muted)",
              border: "1px solid var(--border-subtle)", cursor: "pointer"
            }}
          >
            {loading ? "Re-analyzing..." : "↻ Re-run"}
          </button>
        )}
      </div>

      {error && (
        <div style={{ fontSize: "0.78rem", color: "#f87171", marginBottom: "8px" }}>{error}</div>
      )}

      {/* Matched skills (always visible if present) */}
      {matchedSkills.length > 0 && (
        <div style={{ marginBottom: "10px" }}>
          <div style={{ fontSize: "0.74rem", fontWeight: 700, color: "#4ade80", marginBottom: "5px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            ✅ Your Matched Skills ({matchedSkills.length})
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "5px" }}>
            {matchedSkills.map((skill, i) => (
              <span key={i} style={{
                padding: "2px 10px", borderRadius: "20px", fontSize: "0.74rem", fontWeight: 600,
                background: "rgba(74, 222, 128, 0.12)", color: "#4ade80",
                border: "1px solid rgba(74, 222, 128, 0.3)"
              }}>
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Fast rule-based missing (always visible) */}
      {missingRequirements.length > 0 && !gapReport && (
        <div style={{ marginBottom: "10px" }}>
          <div style={{ fontSize: "0.74rem", fontWeight: 700, color: "#f87171", marginBottom: "5px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            🔴 Detected Gaps (Rule-Based · {missingRequirements.length})
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "5px" }}>
            {missingRequirements.map((req, i) => (
              <button
                key={i}
                onClick={() => copyKeyword(req)}
                title="Click to copy"
                style={{
                  padding: "2px 10px", borderRadius: "20px", fontSize: "0.74rem", fontWeight: 600,
                  background: "rgba(248, 113, 113, 0.1)", color: "#f87171",
                  border: "1px solid rgba(248, 113, 113, 0.35)",
                  cursor: "pointer", display: "flex", alignItems: "center", gap: "4px",
                  transition: "all 0.15s"
                }}
              >
                {copiedKeyword === req ? <Check size={10} /> : <Copy size={10} />}
                {req}
              </button>
            ))}
          </div>
          <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "4px" }}>
            Click any keyword to copy → add to your resume
          </p>
        </div>
      )}

      {/* AI-powered gap report */}
      {gapReport && (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>

          {/* Overall summary */}
          {gapReport.overall_gap_summary && (
            <div style={{
              padding: "8px 12px", borderRadius: "8px", fontSize: "0.78rem",
              background: "rgba(167,139,250,0.08)", border: "1px solid rgba(167,139,250,0.25)",
              color: "#c4b5fd", fontStyle: "italic"
            }}>
              {gapReport.overall_gap_summary}
            </div>
          )}

          {/* Missing technical keywords */}
          {hasMissingTech && (
            <div>
              <div style={{ fontSize: "0.74rem", fontWeight: 700, color: "#f87171", marginBottom: "5px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                🔴 Missing Technical Keywords ({gapReport.missing_technical_keywords.length}) — add these to your resume
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "5px" }}>
                {gapReport.missing_technical_keywords.map((kw, i) => (
                  <button
                    key={i}
                    onClick={() => copyKeyword(kw)}
                    title="Click to copy"
                    style={{
                      padding: "3px 10px", borderRadius: "20px", fontSize: "0.75rem", fontWeight: 600,
                      background: "rgba(248, 113, 113, 0.12)", color: "#f87171",
                      border: "1px solid rgba(248, 113, 113, 0.4)",
                      cursor: "pointer", display: "flex", alignItems: "center", gap: "4px",
                      transition: "all 0.15s"
                    }}
                  >
                    {copiedKeyword === kw ? <Check size={10} /> : <Copy size={10} />}
                    {kw}
                  </button>
                ))}
              </div>
              <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "4px" }}>
                Click any keyword to copy → add to your resume or cover letter
              </p>
            </div>
          )}

          {/* Missing soft skills */}
          {hasMissingSoft && (
            <div>
              <div style={{ fontSize: "0.74rem", fontWeight: 700, color: "#fb923c", marginBottom: "5px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                🟠 Soft Skills Gap
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "5px" }}>
                {gapReport.missing_soft_skills.map((sk, i) => (
                  <span key={i} style={{
                    padding: "2px 10px", borderRadius: "20px", fontSize: "0.74rem", fontWeight: 600,
                    background: "rgba(251,146,60,0.1)", color: "#fb923c",
                    border: "1px solid rgba(251,146,60,0.3)"
                  }}>
                    {sk}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Resume tips */}
          {hasTips && (
            <div style={{
              padding: "10px 14px", borderRadius: "8px",
              background: "rgba(96,165,250,0.07)", border: "1px solid rgba(96,165,250,0.2)"
            }}>
              <div style={{ fontSize: "0.74rem", fontWeight: 700, color: "#60a5fa", marginBottom: "6px", display: "flex", alignItems: "center", gap: "5px" }}>
                <Lightbulb size={13} /> AI Resume Tips for This Role
              </div>
              <ul style={{ margin: 0, paddingLeft: "16px", display: "flex", flexDirection: "column", gap: "4px" }}>
                {gapReport.resume_tips.map((tip, i) => (
                  <li key={i} style={{ fontSize: "0.78rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                    {tip}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!hasMissingTech && !hasMissingSoft && !hasTips && (
            <div style={{ fontSize: "0.78rem", color: "#4ade80", display: "flex", alignItems: "center", gap: "6px" }}>
              <CheckCircle2 size={14} /> Strong match — no major gaps detected!
            </div>
          )}
        </div>
      )}
    </div>
  )
}
