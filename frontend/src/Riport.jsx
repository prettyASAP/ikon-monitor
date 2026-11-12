import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from './api'
import './riport.css'

const PROFILE = 'napi'
const AI_TAG = 'ai:kizárva'

function statusOf(a) {
  if (a.feedback_decision === 'releváns') return 'riport'
  if (a.feedback_decision === 'nem_releváns') return 'ki'
  if (a.category === 'releváns') return 'riport'
  if (a.category === 'felülvizsgálandó') return 'dontes'
  if ((a.score_reason || '').includes(AI_TAG)) return 'ai'
  return null
}

const NAME_START = /^[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]{2,}$/
const NAME_NEXT = /^[A-ZÁÉÍÓÖŐÚÜŰ][a-záéíóöőúüű]{2,}/
const SUFFIX = /(nak|nek|val|vel|ral|rel|ról|ről|tól|től|ban|ben|ba|be|ra|re|t)$/

function names(t) {
  const w = t.replace(/[„”"“:–—,!?()]/g, ' ').split(/\s+/).filter(Boolean)
  const out = []
  for (let i = 0; i + 1 < w.length; i++) {
    if (NAME_START.test(w[i]) && NAME_NEXT.test(w[i + 1])) out.push(w[i] + ' ' + w[i + 1].replace(SUFFIX, ''))
  }
  return out
}

// Ugyanarról szóló cikkek egy sorba: azonos címkezdet vagy a címben elsőként szereplő név alapján.
function groups(list) {
  const g = [], key = {}
  for (const a of list) {
    const t = 't:' + a.title.toLowerCase().replace(/[^a-záéíóöőúüű0-9]/g, '').slice(0, 40)
    const k = names(a.title)[0]
    const hit = key[t] ?? (k !== undefined ? key[k] : undefined)
    if (hit !== undefined) { g[hit].push(a); key[t] = hit; continue }
    const idx = g.push([a]) - 1
    key[t] = idx
    if (k !== undefined) key[k] = idx
  }
  return g
}

const utc = s => new Date(/Z|[+-]\d\d:?\d\d$/.test(s) ? s : s + 'Z')
const sameDay = (a, b) => a.toDateString() === b.toDateString()

function whenLabel(a) {
  const d = (a.published_date || '').split('.').filter(Boolean)
  const date = d.length === 3 ? `${d[1]}. ${d[2]}.` : ''
  return [a.source, [date, a.published_time].filter(Boolean).join(' ')].filter(Boolean).join(' · ')
}

// A napi gyűjtés az előző nap 9:00-tól tart, hétfőn a péntek 9:00-tól (a szerver számolja).
function periodLabel(run) {
  if (!run) return ''
  const end = utc(run.started_at)
  const start = run.window_start ? utc(run.window_start) : new Date(end - run.time_window_hours * 3600e3)
  const fmt = d => (sameDay(d, new Date()) ? 'ma' : d.toLocaleDateString('hu-HU', { weekday: 'long' })) + ' ' +
    d.toLocaleTimeString('hu-HU', { hour: '2-digit', minute: '2-digit' })
  return `${fmt(start)} és ${fmt(end)} között`
}

export default function Riport({ onOpenSettings }) {
  const [run, setRun] = useState(null)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [collecting, setCollecting] = useState(false)
  const [aiOpen, setAiOpen] = useState(false)
  const [openGroups, setOpenGroups] = useState(new Set())
  const [toast, setToast] = useState(null)
  const toastTimer = useRef(null)
  const saveQueue = useRef(Promise.resolve())
  const loadSeq = useRef(0)
  const saveCount = useRef(0)

  useEffect(() => {
    try { document.documentElement.setAttribute('data-theme', localStorage.getItem('ikon-theme') === 'dark' ? 'dark' : 'light') } catch { /* nincs tároló */ }
  }, [])

  const showToast = useCallback((msg, opts = {}) => {
    clearTimeout(toastTimer.current)
    setToast({ msg, ...opts })
    toastTimer.current = setTimeout(() => setToast(null), opts.error ? 8000 : 5000)
  }, [])

  const load = useCallback(async () => {
    // Csak a legutolsó lekérés eredménye kerülhet a képernyőre.
    const seq = ++loadSeq.current
    const stale = () => seq !== loadSeq.current
    const savesAtStart = saveCount.current
    setLoading(true)
    setLoadError(null)
    try {
      await saveQueue.current
      let runs = [], latest = null
      for (let offset = 0; !latest; offset += 100) {
        const page = await api.runs.list({ limit: 100, offset, keyword_profile: PROFILE })
        if (offset === 0) runs = page.items ?? []
        latest = (page.items ?? []).find(r => r.status === 'completed') ?? null
        if (!page.has_more) break
      }
      if (stale()) return
      setCollecting(runs.some(r => r.status === 'running'))
      if (!latest) { setRun(null); setItems([]); return }
      const fetchAll = async (category) => {
        const out = []
        for (let offset = 0; ; offset += 500) {
          const page = await api.articles.list({ run_id: latest.run_id, category, limit: 500, offset })
          out.push(...(page.items ?? []))
          if (!page.has_more) return out
        }
      }
      const lists = await Promise.all(['releváns', 'felülvizsgálandó', 'zaj'].map(fetchAll))
      const seen = new Set()
      const all = []
      for (const a of lists.flat()) {
        if (seen.has(a.article_id)) continue
        seen.add(a.article_id)
        if (statusOf(a)) all.push(a)
      }
      all.sort((x, y) => (y.score ?? 0) - (x.score ?? 0))
      // Ha betöltés közben döntés született, a lekért adat elavult: megvárjuk a mentést és újrakérjük.
      await saveQueue.current
      if (stale()) return
      if (saveCount.current !== savesAtStart) { load(); return }
      setRun(latest)
      setItems(all)
    } catch (e) {
      if (!stale()) setLoadError('Nem sikerült betölteni a riportot. Ellenőrizd a kapcsolatot, és próbáld újra.')
    } finally {
      if (!stale()) setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!collecting) return
    const h = setInterval(async () => {
      try {
        const runs = (await api.runs.list({ limit: 5, keyword_profile: PROFILE })).items ?? []
        if (!runs.some(r => r.status === 'running')) {
          setCollecting(false)
          const done = runs[0]
          if (done?.status === 'failed') showToast('A gyűjtés hibával leállt. Próbáld újra később.', { error: true })
          else showToast('Elkészült a friss gyűjtés')
          load()
        }
      } catch { /* a következő körben újrapróbálja */ }
    }, 4000)
    return () => clearInterval(h)
  }, [collecting, load, showToast])

  // Döntés mentése: a felület azonnal vált, hiba esetén visszaáll.
  // A futásazonosító a döntés pillanatáé, hogy a visszavonás akkor is ugyanazt a futást célozza, ha közben új töltődött be.
  const apply = useCallback(async (changes, msg, runId = run?.run_id) => {
    const prev = changes.map(c => ({ id: c.id, fb: items.find(a => a.article_id === c.id)?.feedback_decision ?? null }))
    const setFb = list => setItems(cur => cur.map(a => {
      const c = list.find(x => x.id === a.article_id)
      return c ? { ...a, feedback_decision: c.fb } : a
    }))
    setFb(changes)
    saveCount.current += 1
    if (msg) showToast(msg, { undo: { changes: prev, runId } })
    // Sorban mentünk, hogy egy gyors Visszavon ne előzze meg az előző mentést.
    const job = saveQueue.current.then(async () => {
      for (const c of changes) {
        if (c.fb) await api.feedback.submit(c.id, { decision: c.fb, reviewer_id: 'ui' }, runId)
        else await api.feedback.remove(c.id, runId).catch(e => { if (e.status !== 404) throw e })
      }
    })
    saveQueue.current = job.catch(() => {})
    try {
      await job
    } catch {
      // Nem a saját induló állapotunkra állunk vissza, mert közben későbbi döntés is születhetett: a szerver a mérvadó.
      showToast('Nem sikerült menteni a döntést. Ellenőrizd a kapcsolatot, és próbáld újra.', { error: true })
      load()
    }
  }, [items, run, showToast, load])

  const undo = () => {
    if (!toast?.undo) return
    apply(toast.undo.changes, null, toast.undo.runId)
    setToast(null)
  }

  const startCollect = async () => {
    try {
      await api.runs.trigger({ triggered_by: 'ui', keyword_profile: PROFILE, window: 'munkanap' })
      setCollecting(true)
      showToast('Elindult a gyűjtés, kb. 1-2 perc')
    } catch (e) {
      if (e.status !== 409) { showToast('Nem sikerült elindítani a gyűjtést', { error: true }); return }
      // A szerver bármely profil futó gyűjtésére 409-et ad; csak a sajátunkat figyeljük.
      const runs = (await api.runs.list({ limit: 5, keyword_profile: PROFILE }).catch(() => ({}))).items ?? []
      if (runs.some(r => r.status === 'running')) { setCollecting(true); showToast('Már fut egy gyűjtés') }
      else showToast('Most egy másik gyűjtés fut a Beállításokban. Pár perc múlva próbáld újra.', { error: true })
    }
  }

  const downloadPdf = async () => {
    if (!run) return
    try {
      await saveQueue.current
      const r = await fetch(`/api/v1/runs/${run.run_id}/pdf`)
      if (!r.ok) throw new Error(r.statusText)
      const url = URL.createObjectURL(await r.blob())
      const a = document.createElement('a')
      a.href = url
      a.download = `IKO-Sajtoelemzes-${utc(run.started_at).toLocaleDateString('sv-SE', { timeZone: 'Europe/Budapest' })}.pdf`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch {
      showToast('Nem sikerült letölteni a PDF-et', { error: true })
    }
  }

  const withStatus = items.map(a => ({ ...a, st: statusOf(a) }))
  const riport = withStatus.filter(a => a.st === 'riport')
  const dontes = withStatus.filter(a => a.st === 'dontes')
  const ai = withStatus.filter(a => a.st === 'ai')
  const ki = withStatus.filter(a => a.st === 'ki')
  const isToday = run && sameDay(utc(run.started_at), new Date())
  const heading = !run ? 'Riport' : isToday ? 'Mai riport' : `Riport · ${utc(run.started_at).toLocaleDateString('hu-HU', { month: 'long', day: 'numeric' })}`
  const short = t => (t.length > 55 ? t.slice(0, 55) + '…' : t)

  const toRiport = a => apply([{ id: a.article_id, fb: 'releváns' }], `Bekerült a riportba: ${short(a.title)}`)
  const toKi = a => apply([{ id: a.article_id, fb: 'nem_releváns' }], `Kivetted: ${short(a.title)}`)

  const titleLink = (a, cls = 'rp-title') => (
    <a className={cls} href={a.url} target="_blank" rel="noopener noreferrer" title="Megnyitja az eredeti cikket új lapon">{a.title}</a>
  )
  const kiRow = a => (
    <div className="rp-row" key={a.article_id}>
      <div className="rp-body">{titleLink(a, 'rp-title small')}<div className="rp-when">{whenLabel(a)}</div></div>
      <button className="rp-secondary" onClick={() => toRiport(a)} title="Visszateszi a hírt a riportba">Visszateszem</button>
    </div>
  )

  return (
    <div className="rp">
      <div className="rp-wrap">
        <div className="rp-top">
          <span><b>IKON Monitor</b> · sajtófigyelés</span>
          <div className="rp-top-actions">
            <button className="rp-ghost" onClick={onOpenSettings} title="Kulcsszavak kezelése, kézi cikkfelvétel és a korábbi futások részletes nézete">Beállítások</button>
          </div>
        </div>

        <div className="rp-hero">
          <div>
            <h1>{heading}</h1>
            <div className="rp-sub">{loading || loadError ? ' ' : run ? `${riport.length} hír a riportban` : 'Ehhez az időszakhoz még nincs gyűjtés'}</div>
          </div>
          <div className="rp-hero-actions">
            <button className="rp-big" onClick={startCollect} disabled={collecting} title="Új gyűjtést indít az előző nap 9:00-tól (hétfőn péntek 9:00-tól), kb. 1-2 perc">{collecting ? 'Gyűjtés folyamatban…' : 'Frissítés'}</button>
            <button className="rp-primary" onClick={downloadPdf} disabled={!run || riport.length === 0 || !!loadError} title="Letölti a riportban lévő híreket ügyfélnek küldhető PDF-ként">PDF letöltése</button>
          </div>
        </div>

        <div className="rp-meta-row">
          <span>{run ? `Időszak: ${periodLabel(run)}` : ''}</span>
        </div>

        {loadError && <div className="rp-notice"><span>{loadError}</span><button className="rp-secondary" onClick={() => load()} title="Újra betölti a riportot">Újra</button></div>}

        {loading && !items.length ? <div className="rp-empty">Betöltés…</div> : loadError ? null : !run ? (
          <div className="rp-panel"><div className="rp-empty">
            <p>Indíts egy gyűjtést, és pár perc múlva itt lesz a riport.</p>
            <p style={{ marginTop: 12 }}><button className="rp-primary" onClick={startCollect} disabled={collecting} title="Új gyűjtést indít a kiválasztott időszakra">{collecting ? 'Gyűjtés folyamatban…' : 'Gyűjtés indítása'}</button></p>
          </div></div>
        ) : (<>
          {dontes.length > 0 ? (<>
            <p className="rp-label rp-label-warn">Döntésre vár · {dontes.length} hír</p>
            <div className="rp-panel rp-panel-warn">{dontes.map(a => (
              <div className="rp-row rp-row-zoned" key={a.article_id}>
                <div className="rp-body">
                  {titleLink(a)}<div className="rp-when">{whenLabel(a)}</div>
                  {a.excerpt && <div className="rp-lead">{a.excerpt}</div>}
                </div>
                <div className="rp-zones">
                  <button className="rp-zone rp-zone-ok" onClick={() => toRiport(a)} title="Beteszi a hírt a riportba"><span aria-hidden="true">✓</span>Riportba</button>
                  <button className="rp-zone rp-zone-x" onClick={() => toKi(a)} title="Kihagyja a hírt, nem kerül a riportba"><span aria-hidden="true">×</span>Kihagyom</button>
                </div>
              </div>
            ))}</div>
          </>) : <p className="rp-quiet">Minden hírről döntöttél.</p>}

          <p className="rp-quiet">
            {ai.length} hírt kiszűrtünk, mert nem a magyar médiapiacról szól{ki.length ? `, ${ki.length} hírt te vettél ki` : ''}.{' '}
            {(ai.length + ki.length) > 0 && <button className="rp-link" onClick={() => setAiOpen(o => !o)} title="Megmutatja a kiszűrt és kivett híreket, hogy egyet-egyet visszatehess">{aiOpen ? 'Elrejtem' : 'Megnézem'}</button>}
          </p>
          {aiOpen && (ai.length + ki.length) > 0 && (
            <div className="rp-panel">
              {ki.length > 0 && <div className="rp-row" style={{ padding: '10px 16px' }}><span className="rp-label" style={{ margin: 0 }}>Te vetted ki</span></div>}
              {ki.map(kiRow)}
              {ai.length > 0 && <div className="rp-row" style={{ padding: '10px 16px' }}><span className="rp-label" style={{ margin: 0 }}>Automatikusan kiszűrve</span></div>}
              {ai.map(kiRow)}
            </div>
          )}

          <p className="rp-label">A riport tartalma · {riport.length} cikk</p>
          <div className="rp-panel">
            {riport.length === 0 && <div className="rp-empty">Még nincs hír a riportban.</div>}
            {groups(riport).map(g => {
              const a = g[0], rest = g.slice(1), open = openGroups.has(a.article_id)
              const sources = [...new Set(rest.map(r => r.source))]
              const toggle = () => setOpenGroups(s => { const n = new Set(s); n.has(a.article_id) ? n.delete(a.article_id) : n.add(a.article_id); return n })
              return (
                <div className="rp-row rp-row-zoned" key={a.article_id}>
                  <div className="rp-body">
                    {titleLink(a)}<div className="rp-when">{whenLabel(a)}</div>
                    {a.excerpt && <div className="rp-lead">{a.excerpt}</div>}
                    {rest.length > 0 && <div className="rp-more">
                      <button className="rp-link" onClick={toggle} title="Megmutatja az ugyanerről szóló többi cikket">
                        {open ? 'Elrejtem' : `+ még ${rest.length} cikk: ${sources.slice(0, 4).join(', ')}${sources.length > 4 ? '…' : ''}`}
                      </button>
                      {open && <ul className="rp-sublist">{rest.map(r => (
                        <li key={r.article_id}>
                          <a href={r.url} target="_blank" rel="noopener noreferrer" title="Megnyitja az eredeti cikket új lapon">{r.title}</a>
                          <span className="rp-src">{r.source}<button className="rp-x sm" onClick={() => toKi(r)} title="Kiveszi ezt a cikket a riportból" aria-label="Kivesz">×</button></span>
                        </li>
                      ))}</ul>}
                    </div>}
                  </div>
                  <div className="rp-zones">
                    <button className="rp-zone rp-zone-x" onClick={() => toKi(a)} title="Kiveszi ezt a hírt a riportból, a téma többi cikke marad"><span aria-hidden="true">×</span>Kivesz</button>
                  </div>
                </div>
              )
            })}
          </div>
        </>)}
      </div>

      {toast && (
        <div className={`rp-toast${toast.error ? ' error' : ''}`} role="status">
          <span>{toast.msg}</span>
          {toast.undo && <button onClick={undo} title="Visszaállítja az utolsó módosítást">Visszavon</button>}
        </div>
      )}
    </div>
  )
}
