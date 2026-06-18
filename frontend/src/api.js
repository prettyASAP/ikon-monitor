const BASE = '/api/v1'

function qs(params) {
  return Object.entries(params)
    .filter(([, v]) => v != null && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
    .join('&')
}

async function req(url, { method = 'GET', body } = {}) {
  const r = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) {
    const detail = await r.json().catch(() => ({}))
    throw Object.assign(new Error(detail?.detail?.message ?? r.statusText), { status: r.status, detail })
  }
  if (r.status === 204) return null
  return r.json()
}

export const api = {
  health: () => req('/health'),

  runs: {
    list:    (p = {})   => req(`${BASE}/runs?${qs(p)}`),
    get:     (id)       => req(`${BASE}/runs/${id}`),
    trigger: (body)     => req(`${BASE}/runs`, { method: 'POST', body }),
    summary: (id)       => req(`${BASE}/runs/${id}/summary`),
  },

  articles: {
    list:  (p = {})     => req(`${BASE}/articles?${qs(p)}`),
    get:   (id)         => req(`${BASE}/articles/${id}`),
    trend: (kw, n = 10) => req(`${BASE}/articles/${encodeURIComponent(kw)}/trend?n_runs=${n}`),
  },

  feedback: {
    list:   (p = {})          => req(`${BASE}/feedback?${qs(p)}`),
    submit: (articleId, body) => req(`${BASE}/feedback/${articleId}`, { method: 'POST', body }),
    remove: (articleId)       => req(`${BASE}/feedback/${articleId}`, { method: 'DELETE' }),
    bulk:   (body, runId)     => req(`${BASE}/feedback/bulk${runId ? `?run_id=${runId}` : ''}`, { method: 'POST', body }),
  },

  keywords: {
    list:   (p = {})        => req(`${BASE}/keywords?${qs(p)}`),
    create: (body)          => req(`${BASE}/keywords`, { method: 'POST', body }),
    patch:  (id, body)      => req(`${BASE}/keywords/${id}`, { method: 'PATCH', body }),
    remove: (id)            => req(`${BASE}/keywords/${id}`, { method: 'DELETE' }),
  },

  config: {
    scoring: () => req(`${BASE}/config/scoring`),
  },
}
