import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from './api'
import { buildSimulation, playSimulation } from './terminalUtils'

function parseScoreReason(reason) {
  if (!reason) return []
  return reason.split(' | ').map((part, i) => {
    part = part.trim()
    if (part.startsWith('src=')) {
      const t = part.slice(4)
      const labels = { tabloid: 'bulvár forrás', media: 'médiaipari forrás', other: 'egyéb forrás' }
      return { id: i, type: 'src', label: labels[t] || t }
    }
    const ctxM = part.match(/^ctx\(([^)]+)\)\+(\d+)$/)
    if (ctxM) return { id: i, type: 'ctx', words: ctxM[1], pts: +ctxM[2] }
    const kwM = part.match(/^(.+?)\(([^)]+)\)\+(\d+)$/)
    if (kwM) {
      const flags = kwM[2]
      return {
        id: i, type: 'kw',
        kw: kwM[1].trim(),
        isFP: flags.includes('FP'),
        tier: (flags.match(/T\d/) || [''])[0],
        pts: +kwM[3],
      }
    }
    return { id: i, type: 'raw', text: part }
  })
}

function ScoreBreakdown({ reason }) {
  if (!reason) return null
  return (
    <div className="score-breakdown">
      {parseScoreReason(reason).map(p => {
        if (p.type === 'src')
          return <span key={p.id} className="sb-item sb-src">{p.label}</span>
        if (p.type === 'ctx')
          return <span key={p.id} className="sb-item sb-ctx">+{p.pts} kontextus: {p.words.replace(/,/g, ', ')}</span>
        if (p.type === 'kw')
          return p.isFP
            ? <span key={p.id} className="sb-item sb-fp">{p.kw} — hamis pozitív {p.tier && `[${p.tier}]`} (+{p.pts})</span>
            : <span key={p.id} className="sb-item sb-hit">+{p.pts} {p.kw} {p.tier && `[${p.tier}]`}</span>
        return <span key={p.id} className="sb-item sb-raw">{p.text}</span>
      })}
    </div>
  )
}

function useInterval(fn, ms, active = true) {
  const ref = useRef(fn)
  useEffect(() => { ref.current = fn })
  useEffect(() => {
    if (!active || ms == null) return
    const id = setInterval(() => ref.current(), ms)
    return () => clearInterval(id)
  }, [ms, active])
}

export default function App() {
  const [health, setHealth]                   = useState(null)
  const [keywords, setKeywords]               = useState([])
  const [currentLine, setCurrentLine]         = useState(null)
  const [running, setRunning]                 = useState(false)
  const [currentRun, setCurrentRun]           = useState(null)
  const [allRuns, setAllRuns]                 = useState([])
  const [articles, setArticles]               = useState([])
  const [summary, setSummary]                 = useState(null)
  const [reviewDecisions, setReviewDecisions] = useState({})
  const [expandedRows, setExpandedRows]       = useState(new Set())
  const [bulkMode, setBulkMode]               = useState(false)
  const [selected, setSelected]               = useState(new Set())
  const [kwPanelOpen, setKwPanelOpen]         = useState(false)
  const [allKeywords, setAllKeywords]         = useState([])
  const [newKwText, setNewKwText]             = useState('')
  const [newKwTier, setNewKwTier]             = useState('tier2_kozepes')
  const [timeWindow, setTimeWindow]           = useState(168)  // 168 = heti, 24 = napi
  const [activeProfile, setActiveProfile]     = useState('iko')

  const cancelSim   = useRef(null)
  const activeRunId = useRef(null)
  const errorTimer  = useRef(null)

  const showError = useCallback((msg, level = 'error') => {
    if (errorTimer.current) clearTimeout(errorTimer.current)
    setCurrentLine({ id: Date.now(), level, msg })
    errorTimer.current = setTimeout(() => setCurrentLine(null), 5000)
  }, [])

  const loadResults = useCallback((runId) => {
    let attempts = 0
    const tryFetch = () => {
      Promise.all([
        api.articles.list({ run_id: runId, limit: 200 }),
        api.runs.summary(runId),
      ]).then(([artData, sumData]) => {
        setArticles(artData.items ?? [])
        setSummary(sumData)
      }).catch(() => {
        if (++attempts < 4) setTimeout(tryFetch, 1500)
      })
    }
    tryFetch()
  }, [])

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: 'error' }))
  }, [])

  useEffect(() => {
    api.keywords.list({ active_only: true, profile: activeProfile }).then(setKeywords).catch(() => {
      setTimeout(() => api.keywords.list({ active_only: true, profile: activeProfile }).then(setKeywords).catch(() => {}), 1000)
    })
    setCurrentRun(null)
    setAllRuns([])
    setArticles([])
    setSummary(null)
    const defaultWindow = activeProfile === 'napi' ? 24 : 168
    setTimeWindow(defaultWindow)
    api.runs.list({ limit: 20, status: 'completed', keyword_profile: activeProfile })
      .then(d => {
        const runs = d.items ?? []
        setAllRuns(runs)
        if (runs.length > 0) {
          const match = runs.find(r => r.time_window_hours === defaultWindow) ?? runs[0]
          setCurrentRun(match)
        }
      })
      .catch(() => {})
  }, [activeProfile])

  // Ha a felhasználó Heti/Napi togglet vált, auto-select a megfelelő futásra
  useEffect(() => {
    if (!allRuns.length) return
    const match = allRuns.find(r => r.time_window_hours === timeWindow)
    if (match && match.run_id !== currentRun?.run_id) {
      setCurrentRun(match)
      setSummary(null)
      setArticles([])
    }
  }, [timeWindow]) // eslint-disable-line react-hooks/exhaustive-deps

  const runId = currentRun?.run_id
  useEffect(() => {
    if (!runId || running) return
    loadResults(runId)
  }, [runId, running, loadResults])

  useEffect(() => {
    const initial = {}
    for (const a of articles) {
      if (a.feedback_decision) initial[a.article_id] = a.feedback_decision
    }
    setReviewDecisions(initial)
  }, [articles])

  useInterval(async () => {
    if (!activeRunId.current) return
    try {
      const run = await api.runs.get(activeRunId.current)
      if (run.status === 'completed' || run.status === 'failed') {
        cancelSim.current?.()
        activeRunId.current = null
        setCurrentLine(null)
        setRunning(false)
        if (run.status === 'completed') {
          setCurrentRun(run)
          setAllRuns(prev => [run, ...prev.filter(r => r.run_id !== run.run_id)])
          loadResults(run.run_id)
        } else {
          showError(`✗ Pipeline hiba: ${run.error_msg || 'ismeretlen hiba'}`)
        }
      }
    } catch (e) { console.error('poll', e) }
  }, 1800, running)

  const triggerRun = useCallback(async () => {
    if (running) return
    if (errorTimer.current) clearTimeout(errorTimer.current)
    setRunning(true)
    setCurrentLine(null)
    setSummary(null)
    setArticles([])
    try {
      const run = await api.runs.trigger({ triggered_by: 'ui', time_window_hours: timeWindow, keyword_profile: activeProfile })
      activeRunId.current = run.run_id
      cancelSim.current = playSimulation(
        buildSimulation(keywords),
        line => setCurrentLine(line),
        () => {},
      )
    } catch (e) {
      setRunning(false)
      showError(`✗  ${e.message}`, e.status === 409 ? 'warn' : 'error')
    }
  }, [running, keywords, showError, timeWindow, activeProfile])

  const handleReview = useCallback(async (articleId, decision) => {
    try {
      await api.feedback.submit(articleId, { decision, reviewer_id: 'ui' })
      setReviewDecisions(prev => ({ ...prev, [articleId]: decision }))
    } catch {
      showError('✗ Döntés mentése sikertelen')
    }
  }, [showError])

  const handleUnreview = useCallback(async (articleId) => {
    try {
      await api.feedback.remove(articleId)
      setReviewDecisions(prev => { const n = { ...prev }; delete n[articleId]; return n })
    } catch {
      showError('✗ Visszavonás sikertelen')
    }
  }, [showError])

  const toggleExpand = useCallback((id) => {
    setExpandedRows(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleSelect = useCallback((id) => {
    setSelected(prev => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }, [])

  const selectAll = useCallback(() => {
    setSelected(new Set(articles.filter(a => a.category === 'felülvizsgálandó').map(a => a.article_id)))
  }, [articles])

  const handleBulk = useCallback(async (decision) => {
    const ids = [...selected]
    if (!ids.length) return
    try {
      await api.feedback.bulk(
        { items: ids.map(id => ({ article_id: id, decision })), reviewer_id: 'ui' },
        currentRun?.run_id,
      )
      setReviewDecisions(prev => {
        const n = { ...prev }
        for (const id of ids) n[id] = decision
        return n
      })
      setSelected(new Set())
      setBulkMode(false)
    } catch {
      showError('✗ Tömeges döntés mentése sikertelen')
    }
  }, [selected, currentRun, showError])

  const downloadPdf = useCallback(async () => {
    if (!currentRun) return
    try {
      const r = await fetch(`/api/v1/runs/${currentRun.run_id}/pdf`)
      if (!r.ok) throw new Error(r.statusText)
      const blob = await r.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ikon-${currentRun.run_id}.pdf`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch {
      showError('✗ PDF letöltési hiba')
    }
  }, [currentRun, showError])

  const openKwPanel = useCallback(async () => {
    setKwPanelOpen(true)
    try {
      const d = await api.keywords.list({ profile: activeProfile })
      setAllKeywords(d.items ?? [])
    } catch {
      showError('✗ Kulcsszavak betöltése sikertelen')
    }
  }, [showError, activeProfile])

  const toggleKwActive = useCallback(async (kw) => {
    const newActive = !kw.is_active
    try {
      await api.keywords.patch(kw.id, { is_active: newActive })
      setAllKeywords(prev => prev.map(k => k.id === kw.id ? { ...k, is_active: newActive } : k))
    } catch {
      showError('✗ Kulcsszó módosítása sikertelen')
    }
  }, [showError])

  const addKeyword = useCallback(async () => {
    const kw = newKwText.trim()
    if (!kw) return
    try {
      const created = await api.keywords.create({ keyword: kw, tier: newKwTier, profile: activeProfile })
      setAllKeywords(prev => [...prev, created])
      setNewKwText('')
    } catch (e) {
      showError(e.status === 409 ? '✗ Ez a kulcsszó már létezik' : '✗ Hozzáadás sikertelen')
    }
  }, [newKwText, newKwTier, showError, activeProfile])

  const tier1 = keywords.filter(k => k.tier === 'tier1_specifikus')
  const tier2 = keywords.filter(k => k.tier === 'tier2_kozepes')
  const tier3 = keywords.filter(k => k.tier === 'tier3_generikus')

  const relArticles = articles.filter(a => a.category === 'releváns')
  const revArticles = articles.filter(a => a.category === 'felülvizsgálandó')
  const revApproved = revArticles.filter(a => reviewDecisions[a.article_id] === 'releváns')
  const revRejected = revArticles.filter(a => reviewDecisions[a.article_id] === 'nem_releváns')
  const pdfArticles = [...relArticles, ...revApproved].sort((a, b) => b.score - a.score)

  const PROFILES = [
    { id: 'iko',   label: 'IKO' },
    { id: 'napi',  label: 'NAPI' },
  ]

  return (
    <div className="app">
      <div className="page-content">

        {/* ── Profile tabs ── */}
        <div className="profile-tabs">
          {PROFILES.map(p => (
            <button
              key={p.id}
              className={`profile-tab${activeProfile === p.id ? ' profile-tab-active' : ''}`}
              onClick={() => { if (!running) setActiveProfile(p.id) }}
              disabled={running}
            >{p.label}</button>
          ))}
        </div>

        {/* ── Hero ── */}
        <section className="hero">
          <div className="hero-top">
            <div className="time-window-toggle">
              <button
                className={`tw-btn${timeWindow === 168 ? ' tw-active' : ''}`}
                onClick={() => setTimeWindow(168)}
                disabled={running}
                title={allRuns.some(r => r.time_window_hours === 168) ? '' : 'Nincs heti futás – indíts egyet'}
              >Heti</button>
              <button
                className={`tw-btn${timeWindow === 24 ? ' tw-active' : ''}`}
                onClick={() => setTimeWindow(24)}
                disabled={running}
                title={allRuns.some(r => r.time_window_hours === 24) ? '' : 'Nincs napi futás – indíts egyet'}
              >Napi</button>
            </div>
            <button className="btn-run" onClick={triggerRun} disabled={running}>
              {running ? '⟳  Futás folyamatban…' : '▶  Futás indítása'}
            </button>
            {currentRun && !running && pdfArticles.length > 0 && (
              <button className="btn-pdf btn-pdf-hero" onClick={downloadPdf}>↓ PDF</button>
            )}
            {allRuns.length > 0 && !running && (
              <select
                className="run-selector"
                value={currentRun?.run_id || ''}
                onChange={e => {
                  const run = allRuns.find(r => r.run_id === e.target.value)
                  if (run) { setCurrentRun(run); setSummary(null); setArticles([]) }
                }}
              >
                {allRuns.map(r => (
                  <option key={r.run_id} value={r.run_id}>
                    {r.run_id}  ·  {r.relevant} rel / {r.review} rev
                  </option>
                ))}
              </select>
            )}
            <div className={`status-dot ${health == null ? 'loading' : health.status === 'ok' ? 'ok' : 'error'}`}
                 title={health?.status === 'ok' ? `API v${health.schema_version || '?'}` : 'API hiba'}
                 style={{ marginLeft: 'auto', flexShrink: 0 }} />
          </div>
        </section>

        {/* ── Keywords ── */}
        <section className="kw-section">
          <div className="section-label">
            Aktív kulcsszavak
            <span className="section-label-count">{keywords.length}</span>
            <button className="btn-kw-manage" onClick={kwPanelOpen ? () => setKwPanelOpen(false) : openKwPanel}>
              {kwPanelOpen ? '✕ Bezár' : '⚙ Kezel'}
            </button>
          </div>
          {[['tier1_specifikus', tier1, 'kw-t1', 'T1'],
            ['tier2_kozepes',   tier2, 'kw-t2', 'T2'],
            ['tier3_generikus', tier3, 'kw-t3', 'T3']].map(([, list, cls, label]) =>
            list.length > 0 && (
              <div key={label} className="kw-row">
                <span className={`kw-tier ${cls}`}>{label}</span>
                <div className="kw-tags">
                  {list.map(k => <span key={k.keyword} className={`kw-tag ${cls}`}>{k.keyword}</span>)}
                </div>
              </div>
            )
          )}

          {/* ── Keyword management panel ── */}
          {kwPanelOpen && (
            <div className="kw-panel">
              <div className="kw-panel-list">
                {['tier1_specifikus', 'tier2_kozepes', 'tier3_generikus'].map(tier => {
                  const tierKws = allKeywords.filter(k => k.tier === tier)
                  if (!tierKws.length) return null
                  const cls = tier === 'tier1_specifikus' ? 'kw-t1' : tier === 'tier2_kozepes' ? 'kw-t2' : 'kw-t3'
                  const lbl = tier === 'tier1_specifikus' ? 'T1' : tier === 'tier2_kozepes' ? 'T2' : 'T3'
                  return (
                    <div key={tier} className="kw-panel-group">
                      <div className={`kw-tier ${cls}`} style={{ marginBottom: 6 }}>{lbl}</div>
                      {tierKws.map(kw => (
                        <div key={kw.id} className={`kw-panel-row${kw.is_active ? '' : ' kw-row-inactive'}`}>
                          <span className="kw-panel-word">{kw.keyword}</span>
                          <label className="toggle-switch">
                            <input type="checkbox" checked={!!kw.is_active} onChange={() => toggleKwActive(kw)} />
                            <span className="toggle-slider" />
                          </label>
                        </div>
                      ))}
                    </div>
                  )
                })}
              </div>
              <div className="kw-panel-add">
                <input
                  className="kw-add-input"
                  placeholder="Új kulcsszó…"
                  value={newKwText}
                  onChange={e => setNewKwText(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addKeyword()}
                />
                <select className="kw-add-tier" value={newKwTier} onChange={e => setNewKwTier(e.target.value)}>
                  <option value="tier1_specifikus">T1</option>
                  <option value="tier2_kozepes">T2</option>
                  <option value="tier3_generikus">T3</option>
                </select>
                <button className="btn-kw-add" onClick={addKeyword}>+ Hozzáad</button>
              </div>
            </div>
          )}
        </section>

        {/* ── Running marquee ── */}
        {(running || currentLine) && (
          <section className="run-marquee">
            {running && <span className="terminal-cursor" />}
            {currentLine && (
              <div className="marquee-line" key={currentLine.id}>
                <span className={`log-${currentLine.level}`}>{currentLine.msg}</span>
              </div>
            )}
          </section>
        )}

        {/* ── Results ── */}
        {currentRun && summary && !running && (
          <section className="results-section">
            <div className="section-label">Eredmények</div>

            {/* Metrics */}
            <div className="metrics-row">
              {[
                { val: currentRun.relevant,     label: 'Releváns', cls: 'metric-relevant' },
                { val: currentRun.review,        label: 'Review',   cls: 'metric-review'   },
                { val: currentRun.noise,         label: 'Zaj',      cls: 'metric-noise'    },
                { val: currentRun.total_raw,     label: 'Nyers',    cls: ''                },
                { val: currentRun.total_unique,  label: 'Egyedi',   cls: ''                },
              ].map(m => (
                <div key={m.label} className={`metric-card ${m.cls}`}>
                  <div className="metric-val">{m.val}</div>
                  <div className="metric-lbl">{m.label}</div>
                </div>
              ))}
            </div>

            {/* Source distribution */}
            {summary.source_distribution?.length > 0 && (
              <div className="source-dist">
                {summary.source_distribution.slice(0, 10).map(s => {
                  const max = summary.source_distribution[0]?.cnt || 1
                  return (
                    <div key={s.source} className="src-bar-row">
                      <span className="src-bar-label">{s.source}</span>
                      <div className="src-bar-track">
                        <div className="src-bar-fill" style={{ width: `${(s.cnt / max) * 100}%` }} />
                      </div>
                      <span className="src-bar-cnt">{s.cnt}</span>
                    </div>
                  )
                })}
              </div>
            )}

            {/* ── Curator queue: REV cikkek ── */}
            {revArticles.length > 0 && (
              <div className="curator-block">
                <div className="section-label">
                  Felülvizsgálandó
                  <span className="section-label-count">{revArticles.length}</span>
                  {!bulkMode && revApproved.length > 0 && (
                    <span className="review-progress">{revApproved.length} jóváhagyva</span>
                  )}
                  {!bulkMode && revRejected.length > 0 && (
                    <span className="rejected-count">{revRejected.length} visszautasítva</span>
                  )}
                  {bulkMode ? (
                    <>
                      <span className="bulk-count">{selected.size} kijelölve</span>
                      <button className="btn-bulk-action btn-bulk-all" onClick={selectAll}>Mindet</button>
                      <button className="btn-bulk-action btn-bulk-rel" onClick={() => handleBulk('releváns')} disabled={!selected.size}>Releváns</button>
                      <button className="btn-bulk-action btn-bulk-rej" onClick={() => handleBulk('nem_releváns')} disabled={!selected.size}>Elutasít</button>
                      <button className="btn-bulk-toggle" onClick={() => { setBulkMode(false); setSelected(new Set()) }}>✕ Kilép</button>
                    </>
                  ) : (
                    <button className="btn-bulk-toggle" onClick={() => setBulkMode(true)}>Kijelöl</button>
                  )}
                </div>
                <div className="queue-list">
                  {revArticles.map(a => {
                    const dec = reviewDecisions[a.article_id]
                    const isApproved = dec === 'releváns'
                    const isRejected = dec === 'nem_releváns'
                    const isSelected = bulkMode && selected.has(a.article_id)
                    const isExpanded = expandedRows.has(a.article_id)
                    return (
                      <div
                        key={a.article_id}
                        className={`queue-item${bulkMode
                          ? isSelected ? ' queue-item-bulk-selected' : ''
                          : isApproved ? ' queue-item-checked' : isRejected ? ' queue-item-rejected' : ''}`}
                        onClick={() => bulkMode
                          ? toggleSelect(a.article_id)
                          : isApproved ? handleUnreview(a.article_id) : handleReview(a.article_id, 'releváns')}
                      >
                        <div className={`queue-check${bulkMode
                          ? isSelected ? ' selected' : ''
                          : isApproved ? ' checked' : isRejected ? ' rejected' : ''}`} />
                        <span
                          className="queue-score"
                          title={a.score_reason || ''}
                          onClick={e => { e.stopPropagation(); toggleExpand(a.article_id) }}
                          style={{ cursor: 'help' }}
                        >{a.score}</span>
                        <div className="queue-body">
                          <a
                            href={a.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="queue-title"
                            onClick={e => e.stopPropagation()}
                          >{a.title}</a>
                          <span className="queue-meta">
                            {a.source} · {a.published_date_iso?.slice(5) ?? ''}
                            {a.matched_keywords?.length > 0 && (
                              <span className="queue-kws">
                                {' · '}{a.matched_keywords.slice(0, 3).join(', ')}
                              </span>
                            )}
                          </span>
                          {isExpanded && a.score_reason && (
                            <ScoreBreakdown reason={a.score_reason} />
                          )}
                        </div>
                        {!bulkMode && (
                          <button
                            className="btn-reject-queue"
                            title={isRejected ? 'Visszavon' : 'Nem releváns'}
                            onClick={e => {
                              e.stopPropagation()
                              isRejected ? handleUnreview(a.article_id) : handleReview(a.article_id, 'nem_releváns')
                            }}
                          >✕</button>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* ── Releváns pile → PDF ── */}
            {pdfArticles.length > 0 && (
              <div className="pdf-block">
                <div className="section-label">
                  {revArticles.length > 0 ? 'Releváns — PDF' : 'Releváns'}
                  <span className="section-label-count">{pdfArticles.length}</span>
                  <button className="btn-pdf" onClick={downloadPdf}>↓ PDF</button>
                </div>

                <div className="articles-list">
                  {pdfArticles.map(a => {
                    const isApprovedRev = a.category === 'felülvizsgálandó'
                    const isExpanded = expandedRows.has(a.article_id)
                    return (
                      <div key={a.article_id} className="art-row art-rel">
                        <span
                          className="art-score"
                          title={a.score_reason || ''}
                          onClick={() => toggleExpand(a.article_id)}
                          style={{ cursor: 'help' }}
                        >{a.score}</span>
                        {isApprovedRev ? (
                          <button
                            className="art-cat art-cat-decided badge-completed"
                            onClick={() => handleUnreview(a.article_id)}
                            title="Visszavon"
                          >✓</button>
                        ) : (
                          <span className="art-cat badge-completed">REL</span>
                        )}
                        <span className="art-source">{a.source}</span>
                        <div className="art-title-wrap">
                          <a
                            href={a.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="art-title"
                          >{a.title}</a>
                          {isExpanded && a.score_reason && (
                            <div className="art-score-reason"><ScoreBreakdown reason={a.score_reason} /></div>
                          )}
                        </div>
                        <span className="art-date">{a.published_date_iso?.slice(0, 10) ?? ''}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

          </section>
        )}
      </div>
    </div>
  )
}
