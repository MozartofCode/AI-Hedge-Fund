const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function post(path) {
  const res = await fetch(`${BASE}${path}`, { method: 'POST' })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export const api = {
  health:        ()                              => get('/api/health'),
  portfolio:     (market = 'US')                 => get(`/api/portfolio?market=${market}`),
  stats:         (market = 'US')                 => get(`/api/stats?market=${market}`),
  trades:        (page = 1, limit = 20, market = 'US') => get(`/api/trades?page=${page}&limit=${limit}&market=${market}`),
  debates:       (page = 1, limit = 20, market = 'US') => get(`/api/debates?page=${page}&limit=${limit}&market=${market}`),
  session:       (id)                            => get(`/api/session/${id}`),
  latestSession: (ticker, market = 'US')         => get(`/api/latest-session/${encodeURIComponent(ticker)}?market=${market}`),
  analyze:       (ticker, market = 'US')         => post(`/api/analyze?ticker=${encodeURIComponent(ticker)}&market=${market}`),
  search:        (q, market = 'US')              => get(`/api/search?q=${encodeURIComponent(q)}&market=${market}`),
}
