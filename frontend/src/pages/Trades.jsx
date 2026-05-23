import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day   = String(d.getDate()).padStart(2, '0')
  const hours = String(d.getHours()).padStart(2, '0')
  const mins  = String(d.getMinutes()).padStart(2, '0')
  return `${month}/${day} ${hours}:${mins}`
}

function fmtQty(qty) {
  if (qty == null) return '—'
  // Show whole number if it is one, otherwise 2 decimal places
  return Number.isInteger(qty) || Math.abs(qty - Math.round(qty)) < 0.001
    ? String(Math.round(qty))
    : Number(qty).toFixed(2)
}

// ── Agent metadata ────────────────────────────────────────────────────────────

const AGENT_META = {
  technician:     { label: 'The Technician',     icon: '📈', role: 'Technical Analysis' },
  fundamentalist: { label: 'The Fundamentalist', icon: '📊', role: 'Fundamental Analysis' },
  newshound:      { label: 'The Newshound',       icon: '📰', role: 'News & Sentiment' },
  macro_watcher:  { label: 'The Macro Watcher',  icon: '🌍', role: 'Macro & Sectors' },
  risk_manager:   { label: 'The Risk Manager',   icon: '🛡️', role: 'Risk & Portfolio' },
}

const ACTION_STYLE = {
  BUY:  { badge: 'badge-buy',  bar: 'bg-green-500' },
  SELL: { badge: 'badge-sell', bar: 'bg-red-500' },
  HOLD: { badge: 'badge-hold', bar: 'bg-gray-500' },
}

// ── Trade Detail Modal ────────────────────────────────────────────────────────

function TradeModal({ trade, onClose }) {
  const [sessionData, setSessionData] = useState(null)
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState(null)

  useEffect(() => {
    if (!trade?.session_id) {
      setLoading(false)
      setError('No committee session linked to this trade.')
      return
    }
    api.session(trade.session_id)
      .then(d => { setSessionData(d); setLoading(false) })
      .catch(() => { setError('Could not load committee session.'); setLoading(false) })
  }, [trade?.session_id])

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700/80 rounded-2xl w-full max-w-2xl max-h-[85vh] overflow-y-auto shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Modal header */}
        <div className="flex items-start justify-between p-5 border-b border-gray-800 sticky top-0 bg-gray-900 rounded-t-2xl z-10">
          <div>
            <div className="flex items-center gap-3">
              <span className={`text-xl font-black ${trade.side === 'buy' ? 'text-green-400' : 'text-red-400'}`}>
                {trade.side?.toUpperCase()}
              </span>
              <span className="text-xl font-bold text-white">{trade.ticker}</span>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              {fmtQty(trade.qty)} shares @ ${Number(trade.filled_price).toFixed(2)}
              {' · '}{formatTime(trade.filled_at)}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-600 hover:text-gray-200 transition-colors text-xl leading-none mt-0.5 ml-4"
          >
            ✕
          </button>
        </div>

        {/* Modal body */}
        <div className="p-5 space-y-4">
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-24 bg-gray-800/60 rounded-xl animate-pulse" />
              ))}
            </div>
          ) : error ? (
            <div className="text-gray-500 text-sm text-center py-10">{error}</div>
          ) : sessionData ? (
            <>
              {/* Chairman verdict strip */}
              {sessionData.chairman_rationale && (
                <div className="bg-gray-800/60 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-lg">🏛️</span>
                    <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Chairman's Rationale</span>
                    {sessionData.weighted_score != null && (
                      <span className="ml-auto text-xs text-gray-600">Score: {sessionData.weighted_score?.toFixed(3)}</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-300 leading-relaxed italic">
                    "{sessionData.chairman_rationale}"
                  </p>
                </div>
              )}

              {/* Agent votes */}
              <div className="space-y-3">
                {sessionData.agent_votes?.map(v => {
                  const meta   = AGENT_META[v.agent_name] ?? { label: v.agent_name, icon: '🤖', role: '' }
                  const style  = ACTION_STYLE[v.action] ?? ACTION_STYLE.HOLD
                  const confPct = Math.round((v.confidence ?? 0) * 100)
                  const isRM   = v.agent_name === 'risk_manager'

                  return (
                    <div
                      key={v.agent_name}
                      className={`bg-gray-800/50 rounded-xl p-4 border ${v.veto ? 'border-red-500/40' : 'border-gray-700/40'}`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="text-lg leading-none">{meta.icon}</span>
                          <div>
                            <div className="text-sm font-semibold text-white leading-tight">{meta.label}</div>
                            <div className="text-xs text-gray-500">{meta.role}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {v.veto && (
                            <span className="text-xs font-bold text-red-400 border border-red-500/40 rounded px-2 py-0.5">
                              VETOED
                            </span>
                          )}
                          <span className={style.badge}>{v.action ?? 'HOLD'}</span>
                        </div>
                      </div>

                      {!isRM && (
                        <div className="mb-2">
                          <div className="flex justify-between text-xs text-gray-500 mb-1">
                            <span>Confidence</span>
                            <span className="text-gray-300 font-medium">{confPct}%</span>
                          </div>
                          <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${style.bar}`}
                              style={{ width: `${confPct}%` }}
                            />
                          </div>
                        </div>
                      )}

                      <p className="text-xs text-gray-400 leading-relaxed">
                        {v.rationale || '—'}
                      </p>
                    </div>
                  )
                })}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}

// ── Pagination ────────────────────────────────────────────────────────────────

function Pagination({ page, pages, total, limit, onPage }) {
  if (pages <= 1) return null
  const start = (page - 1) * limit + 1
  const end   = Math.min(page * limit, total)
  return (
    <div className="flex items-center justify-between pt-3 border-t border-gray-800">
      <span className="text-xs text-gray-600">{start}–{end} of {total.toLocaleString()} trades</span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPage(p => Math.max(1, p - 1))}
          disabled={page === 1}
          className="px-3 py-1.5 text-xs rounded-lg bg-gray-800 text-gray-300 disabled:opacity-30 hover:bg-gray-700 transition-colors"
        >
          ← Prev
        </button>
        <span className="text-xs text-gray-500">{page} / {pages}</span>
        <button
          onClick={() => onPage(p => Math.min(pages, p + 1))}
          disabled={page === pages}
          className="px-3 py-1.5 text-xs rounded-lg bg-gray-800 text-gray-300 disabled:opacity-30 hover:bg-gray-700 transition-colors"
        >
          Next →
        </button>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Trades() {
  const [rows, setRows]               = useState(null)
  const [total, setTotal]             = useState(0)
  const [page, setPage]               = useState(1)
  const [pages, setPages]             = useState(1)
  const [filter, setFilter]           = useState('all') // 'all' | 'buy' | 'sell'
  const [loading, setLoading]         = useState(true)
  const [selectedTrade, setSelectedTrade] = useState(null)

  const LIMIT = 20

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.trades(page, LIMIT)
      setRows(data.items ?? [])
      setTotal(data.total ?? 0)
      setPages(data.pages ?? 1)
    } catch (e) {
      console.error('Trades load failed:', e)
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => { load() }, [load])

  const visible = rows
    ? rows.filter(t => filter === 'all' || t.side === filter)
    : null

  const notional = (t) => {
    if (t.qty && t.filled_price) return t.qty * t.filled_price
    return null
  }

  return (
    <>
      {/* Trade detail modal */}
      {selectedTrade && (
        <TradeModal trade={selectedTrade} onClose={() => setSelectedTrade(null)} />
      )}

      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-white">Trade History</h1>
            {total > 0 && (
              <p className="text-xs text-gray-600 mt-0.5">{total.toLocaleString()} total trades · click any row to see committee logic</p>
            )}
          </div>

          {/* Filter tabs */}
          <div className="flex gap-1 bg-gray-800/50 rounded-xl p-1">
            {['all', 'buy', 'sell'].map(f => (
              <button
                key={f}
                onClick={() => { setFilter(f); setPage(1) }}
                className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-colors capitalize ${
                  filter === f
                    ? f === 'buy'
                      ? 'bg-green-500/20 text-green-400 border border-green-500/30'
                      : f === 'sell'
                      ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                      : 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {f === 'all' ? 'All Trades' : f.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* Table */}
        <div className="card overflow-hidden">
          {loading && !rows ? (
            <div className="space-y-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-12 bg-gray-800/50 rounded-lg animate-pulse" />
              ))}
            </div>
          ) : !visible?.length ? (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <span className="text-4xl">📋</span>
              <p className="text-gray-500 text-sm">
                {filter === 'all' ? 'No trades yet' : `No ${filter.toUpperCase()} trades yet`}
              </p>
              <p className="text-gray-600 text-xs text-center max-w-xs">
                The committee executes trades automatically during market hours (Mon–Fri, 9:30am–4pm ET)
              </p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto -mx-4 px-4">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-gray-500 uppercase border-b border-gray-800">
                      <th className="text-left pb-3 font-medium">Ticker</th>
                      <th className="text-left pb-3 font-medium">Side</th>
                      <th className="text-right pb-3 font-medium">Price</th>
                      <th className="text-right pb-3 font-medium hidden sm:table-cell">Qty</th>
                      <th className="text-right pb-3 font-medium hidden md:table-cell">Total Value</th>
                      <th className="text-right pb-3 font-medium">Time</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60">
                    {visible.map(t => {
                      const tot = notional(t)
                      return (
                        <tr
                          key={t.id}
                          onClick={() => setSelectedTrade(t)}
                          className="hover:bg-gray-800/40 transition-colors cursor-pointer group"
                          title="Click to see committee logic"
                        >
                          <td className="py-3.5 font-bold text-white text-sm">{t.ticker}</td>
                          <td className="py-3.5">
                            <span className={t.side === 'buy' ? 'badge-buy' : 'badge-sell'}>
                              {t.side?.toUpperCase()}
                            </span>
                          </td>
                          <td className="py-3.5 text-right text-gray-200 tabular-nums">
                            {t.filled_price ? `$${Number(t.filled_price).toFixed(2)}` : '—'}
                          </td>
                          <td className="py-3.5 text-right text-gray-400 tabular-nums hidden sm:table-cell">
                            {fmtQty(t.qty)}
                          </td>
                          <td className="py-3.5 text-right text-gray-400 tabular-nums hidden md:table-cell">
                            {tot ? `$${tot.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
                          </td>
                          <td className="py-3.5 text-right text-gray-500 text-xs tabular-nums">
                            {formatTime(t.filled_at)}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <Pagination page={page} pages={pages} total={total} limit={LIMIT} onPage={setPage} />
            </>
          )}
        </div>
      </div>
    </>
  )
}
