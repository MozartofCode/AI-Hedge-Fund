import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'

function timeAgo(iso) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d}d ago`
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

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

export default function Trades() {
  const [rows, setRows]       = useState(null)
  const [total, setTotal]     = useState(0)
  const [page, setPage]       = useState(1)
  const [pages, setPages]     = useState(1)
  const [filter, setFilter]   = useState('all') // 'all' | 'buy' | 'sell'
  const [loading, setLoading] = useState(true)

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
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold text-white">Trade History</h1>
          {total > 0 && (
            <p className="text-xs text-gray-600 mt-0.5">{total.toLocaleString()} total trades</p>
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
                    <th className="text-right pb-3 font-medium hidden lg:table-cell">Order ID</th>
                    <th className="text-right pb-3 font-medium">Time</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/60">
                  {visible.map(t => {
                    const total = notional(t)
                    return (
                      <tr key={t.id} className="hover:bg-gray-800/30 transition-colors group">
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
                          {t.qty ? Number(t.qty).toFixed(4) : '—'}
                        </td>
                        <td className="py-3.5 text-right text-gray-400 tabular-nums hidden md:table-cell">
                          {total ? `$${total.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
                        </td>
                        <td className="py-3.5 text-right hidden lg:table-cell">
                          <code className="text-xs text-gray-600 group-hover:text-gray-500">
                            {t.order_id ?? '—'}
                          </code>
                        </td>
                        <td className="py-3.5 text-right text-gray-500 text-xs tabular-nums">
                          {timeAgo(t.filled_at)}
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
  )
}
