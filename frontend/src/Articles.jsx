import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from './api'

const PAGE = 50

const CAT_LABELS = {
  '':                 'Összes',
  'releváns':         'Releváns',
  'felülvizsgálandó': 'Felülvizsgálandó',
  'zaj':              'Zaj',
}

const TIER_LABELS = {
  '':                  'Minden tier',
  'tier1_specifikus':  'Tier 1',
  'tier2_kozepes':     'Tier 2',
  'tier3_generikus':   'Tier 3',
}

function useDebouncedValue(val, delay = 300) {
  const [debounced, setDebounced] = useState(val)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(val), delay)
    return () => clearTimeout(t)
  }, [val, delay])
  return debounced
}

function CategoryBadge({ category }) {
  const cls = category === 'releváns' ? 'badge-relevant'
    : category === 'felülvizsgálandó' ? 'badge-review' : 'badge-noise'
  const label = category === 'releváns' ? 'REL'
    : category === 'felülvizsgálandó' ? 'REV' : 'ZAJ'
  return <span className={`badge ${cls}`}>{label}</span>
}

function TierBadge({ tier }) {
  const cls = tier === 'tier1_specifikus' ? 'badge-tier1'
    : tier === 'tier2_kozepes' ? 'badge-tier2' : 'badge-tier3'
  const label = tier === 'tier1_specifikus' ? 'T1'
    : tier === 'tier2_kozepes' ? 'T2' : 'T3'
  return <span className={`badge ${cls}`}>{label}</span>
}

function ArticleRow({ article, open, onToggle }) {
  const kws = Array.isArray(article.matched_keywords)
    ? article.matched_keywords : []

  return (
    <>
      <div className={`article-row ${open ? 'open' : ''}`} onClick={onToggle}>
        <div className="article-cell center">
          <CategoryBadge category={article.category} />
        </div>
        <div className="article-cell title" title={article.title}>
          {article.title}
        </div>
        <div className="article-cell dim" title={article.source}>
          {article.source}
        </div>
        <div className="article-cell score center">
          {article.score}
        </div>
        <div className="article-cell center">
          <TierBadge tier={article.best_tier} />
        </div>
        <div className="article-cell dim right">
          {article.published_date_iso || article.published_date || '—'}
        </div>
      </div>

      {open && (
        <div style={{
          gridColumn: '1 / -1',
          padding: '12px 14px',
          background: 'var(--bg-elevated)',
          borderBottom: '1px solid var(--border)',
        }}>
          {article.excerpt && (
            <p style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.6, marginBottom: 8 }}>
              {article.excerpt}
            </p>
          )}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 11, color: 'var(--text-dim)' }}>
            <a href={article.url} target="_blank" rel="noopener noreferrer"
               style={{ color: 'var(--blue)', textDecoration: 'none' }}>
              ↗ Forrás megnyitása
            </a>
            <span>Score: <b style={{ color: 'var(--cyan)' }}>{article.score}</b></span>
            <span style={{ color: 'var(--text-dim)', fontStyle: 'italic', fontSize: 11 }}>
              {article.score_reason}
            </span>
            {kws.length > 0 && (
              <span>Kulcsszavak: {kws.map((kw, i) => (
                <span key={i} style={{ color: 'var(--blue)', marginLeft: 4 }}>{kw}</span>
              ))}</span>
            )}
          </div>
          {article.feedback_decision && (
            <div style={{ marginTop: 8, fontSize: 11 }}>
              <span style={{ color: 'var(--text-dim)' }}>Reviewer: </span>
              <span style={{ color: article.feedback_decision === 'releváns' ? 'var(--green)' : 'var(--red)' }}>
                {article.feedback_decision}
              </span>
              {article.reviewer_note && (
                <span style={{ color: 'var(--text-dim)', marginLeft: 8 }}>– {article.reviewer_note}</span>
              )}
            </div>
          )}
        </div>
      )}
    </>
  )
}

export default function Articles({ runId }) {
  const [articles, setArticles] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(false)
  const [openId, setOpenId] = useState(null)

  const [category, setCategory] = useState('')
  const [tier, setTier] = useState('')
  const [scoreMin, setScoreMin] = useState('')
  const [search, setSearch] = useState('')

  const debouncedSearch = useDebouncedValue(search, 400)

  const load = useCallback(async () => {
    setLoading(true)
    setOpenId(null)
    try {
      const data = await api.articles.list({
        ...(runId   ? { run_id: runId }       : {}),
        ...(category ? { category }            : {}),
        ...(tier     ? { best_tier: tier }     : {}),
        ...(scoreMin ? { score_min: scoreMin } : {}),
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
        limit: PAGE,
        offset: page * PAGE,
      })
      setArticles(data.items)
      setTotal(data.total)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [runId, category, tier, scoreMin, debouncedSearch, page])

  useEffect(() => { setPage(0) }, [category, tier, scoreMin, debouncedSearch, runId])
  useEffect(() => { load() }, [load])

  const totalPages = Math.ceil(total / PAGE)

  return (
    <div className="articles-layout">
      {/* Filter bar */}
      <div className="filter-bar">
        <span className="filter-label">Szűrő:</span>
        <select className="filter-select" value={category} onChange={e => setCategory(e.target.value)}>
          {Object.entries(CAT_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select className="filter-select" value={tier} onChange={e => setTier(e.target.value)}>
          {Object.entries(TIER_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <input
          className="filter-input"
          type="number"
          placeholder="Min score"
          value={scoreMin}
          onChange={e => setScoreMin(e.target.value)}
          style={{ width: 90 }}
        />
        <input
          className="filter-input wide"
          placeholder="FTS keresés  (pl: TV2 OR IKO)"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        {loading && <span style={{ color: 'var(--text-dim)', fontSize: 11 }}>⟳ betöltés...</span>}
        {!loading && (
          <span style={{ marginLeft: 'auto', color: 'var(--text-dim)', fontSize: 11 }}>
            {total} cikk
          </span>
        )}
      </div>

      {/* Table */}
      <div className="articles-table">
        <div className="article-row header">
          <div className="article-cell header center">Kat.</div>
          <div className="article-cell header">Cím</div>
          <div className="article-cell header">Forrás</div>
          <div className="article-cell header center">Score</div>
          <div className="article-cell header center">Tier</div>
          <div className="article-cell header right">Dátum</div>
        </div>

        {articles.length === 0 && !loading && (
          <div className="empty-state" style={{ minHeight: 200 }}>
            <span style={{ fontSize: 24 }}>◻</span>
            <span>Nincs találat a szűrőkkel</span>
          </div>
        )}

        {articles.map(a => (
          <ArticleRow
            key={`${a.article_id}:${a.run_id}`}
            article={a}
            open={openId === a.article_id}
            onToggle={() => setOpenId(openId === a.article_id ? null : a.article_id)}
          />
        ))}
      </div>

      {/* Pagination */}
      <div className="pagination">
        <span>{page * PAGE + 1}–{Math.min((page + 1) * PAGE, total)} / {total}</span>
        <div className="pagination-controls">
          <button className="btn btn-ghost" disabled={page === 0} onClick={() => setPage(0)}>«</button>
          <button className="btn btn-ghost" disabled={page === 0} onClick={() => setPage(p => p - 1)}>‹</button>
          <span style={{ padding: '4px 10px', color: 'var(--text-muted)' }}>
            {page + 1} / {totalPages || 1}
          </span>
          <button className="btn btn-ghost" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>›</button>
          <button className="btn btn-ghost" disabled={page >= totalPages - 1} onClick={() => setPage(totalPages - 1)}>»</button>
        </div>
      </div>
    </div>
  )
}
