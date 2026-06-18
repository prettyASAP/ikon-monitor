import { useEffect, useRef } from 'react'

export default function Terminal({ lines = [], running = false }) {
  const bodyRef = useRef(null)

  useEffect(() => {
    const el = bodyRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [lines])

  return (
    <div className="terminal" style={{ height: '100%' }}>
      <div className="terminal-body" ref={bodyRef}>
        {lines.map(line => (
          <div key={line.id} className="terminal-line">
            <span className="terminal-ts">{line.ts}</span>
            <span className={`terminal-msg log-${line.level}`}>{line.msg}</span>
          </div>
        ))}
        {lines.length === 0 && (
          <div className="terminal-line">
            <span className="terminal-ts">—</span>
            <span className="terminal-msg log-dim">Nincs futás. Nyomj ▶ FUTÁS INDÍTÁSA gombot.</span>
          </div>
        )}
        <div className="terminal-line">
          <span className="terminal-ts"> </span>
          <span className="terminal-msg">
            {running && <span className="terminal-cursor" />}
          </span>
        </div>
      </div>
    </div>
  )
}
