const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export const api = {
  health:        ()                       => get('/api/health'),
  portfolio:     ()                       => get('/api/portfolio'),
  stats:         ()                       => get('/api/stats'),
  trades:        (page = 1, limit = 20)   => get(`/api/trades?page=${page}&limit=${limit}`),
  session:       (id)                     => get(`/api/session/${id}`),
  latestSession: (ticker)                 => get(`/api/latest-session/${encodeURIComponent(ticker)}`),
}
