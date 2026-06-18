let _id = 0
export const mkLine = (level, msg) => ({
  id: ++_id,
  ts: new Date().toLocaleTimeString('hu', { hour12: false }),
  level,
  msg,
})

export function buildSimulation(keywords = [], runData = null) {
  const lines = []
  const tier1 = keywords.filter(k => k.tier === 'tier1_specifikus')
  const tier2 = keywords.filter(k => k.tier === 'tier2_kozepes')
  const tier3 = keywords.filter(k => k.tier === 'tier3_generikus')

  lines.push({ delay: 0,   ...mkLine('cmd',  `▶  ikon-monitor run --triggered-by=api`) })
  lines.push({ delay: 120, ...mkLine('info', `✦  Adatbázis kapcsolat: OK`) })
  lines.push({ delay: 200, ...mkLine('info', `✦  Konfigurációs fájl betöltve`) })
  lines.push({ delay: 320, ...mkLine('data', `✦  Aktív kulcsszavak: ${keywords.length} db  │  T1:${tier1.length}  T2:${tier2.length}  T3:${tier3.length}`) })
  lines.push({ delay: 480, ...mkLine('dim',  `─`.repeat(58)) })
  lines.push({ delay: 560, ...mkLine('info', `⟳  Scraping indítása...`) })

  let cumDelay = 500
  const perKeyword = Math.min(60, 2800 / Math.max(keywords.length, 1))

  for (const kw of keywords) {
    const tag = kw.tier === 'tier1_specifikus' ? 'T1' : kw.tier === 'tier2_kozepes' ? 'T2' : 'T3'
    const color = kw.tier === 'tier1_specifikus' ? '!' : kw.tier === 'tier2_kozepes' ? '~' : '·'
    lines.push({ delay: cumDelay, ...mkLine('info', `   [${tag}] ${color} ${kw.keyword}`) })
    cumDelay += perKeyword
  }

  lines.push({ delay: cumDelay,       ...mkLine('dim',    `─`.repeat(58)) })
  lines.push({ delay: cumDelay + 200, ...mkLine('info',   `⊛  Deduplikáció és pontozás...`) })
  lines.push({ delay: cumDelay + 600, ...mkLine('info',   `⊛  Kategorizálás (T1-safety-net aktív)...`) })

  if (runData) {
    const { relevant = 0, review = 0, noise = 0, total_unique = 0, total_raw = 0 } = runData
    const dupRate = total_raw ? ((1 - total_unique / total_raw) * 100).toFixed(1) : '0.0'
    lines.push({ delay: cumDelay + 1000, ...mkLine('dim',    `─`.repeat(58)) })
    lines.push({ delay: cumDelay + 1100, ...mkLine('result', `↳ nyers: ${total_raw}  →  egyedi: ${total_unique}  (${dupRate}% dup)`) })
    lines.push({ delay: cumDelay + 1300, ...mkLine('success',`↳ RELEVÁNS:  ${relevant}`) })
    lines.push({ delay: cumDelay + 1400, ...mkLine('warn',   `↳ REVIEW:    ${review}`) })
    lines.push({ delay: cumDelay + 1500, ...mkLine('dim',    `↳ ZAJ:       ${noise}`) })
    lines.push({ delay: cumDelay + 1700, ...mkLine('dim',    `─`.repeat(58)) })
    lines.push({ delay: cumDelay + 1900, ...mkLine('success',`✓  Futás sikeresen befejezve`) })
  } else {
    lines.push({ delay: cumDelay + 1000, ...mkLine('warn', `Várakozás a pipeline befejezésére...`) })
  }

  return lines
}

export function playSimulation(lines, onLine, onDone) {
  const timers = []
  let aborted = false
  for (const line of lines) {
    const t = setTimeout(() => {
      if (!aborted) onLine({ id: line.id, ts: line.ts, level: line.level, msg: line.msg })
    }, line.delay)
    timers.push(t)
  }
  const lastDelay = lines[lines.length - 1]?.delay ?? 0
  const done = setTimeout(() => { if (!aborted) onDone?.() }, lastDelay + 200)
  timers.push(done)
  return () => { aborted = true; timers.forEach(clearTimeout) }
}

export function buildReplay(run) {
  const { run_id, started_at, completed_at, total_raw = 0, total_unique = 0,
          relevant = 0, review = 0, noise = 0, triggered_by = 'cli' } = run
  const durMs = started_at && completed_at
    ? new Date(completed_at) - new Date(started_at) : null
  const durStr = durMs != null ? `${(durMs / 1000).toFixed(1)}s` : '—'

  return [
    mkLine('cmd',     `▶  ikon-monitor run  [${run_id}]`),
    mkLine('data',    `   by: ${triggered_by}  •  ${new Date(started_at).toLocaleString('hu')}`),
    mkLine('dim',     `─`.repeat(44)),
    mkLine('info',    `⊛ nyers: ${total_raw}  →  egyedi: ${total_unique}  (${durStr})`),
    mkLine('dim',     `─`.repeat(44)),
    mkLine('success', `↳ RELEVÁNS:  ${relevant}`),
    mkLine('warn',    `↳ REVIEW:    ${review}`),
    mkLine('dim',     `↳ ZAJ:       ${noise}`),
    mkLine('dim',     `─`.repeat(44)),
    mkLine('success', `✓  Futás befejezve`),
  ]
}
