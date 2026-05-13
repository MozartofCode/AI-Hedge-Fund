function timeAgo(iso) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return new Date(iso).toLocaleDateString()
}

export default function TradeLog({ trades }) {
  if (!trades) {
    return (
      <div className="card">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Recent Trades</h3>
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-8 bg-gray-800/50 rounded animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  if (!trades.length) {
    return (
      <div className="card">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Recent Trades</h3>
        <p className="text-sm text-gray-600 text-center py-4">No trades yet</p>
      </div>
    )
  }

  return (
    <div className="card overflow-hidden">
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Recent Trades</h3>
      <div className="overflow-x-auto -mx-4 px-4">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 uppercase border-b border-gray-800">
              <th className="text-left pb-2 font-medium">Ticker</th>
              <th className="text-left pb-2 font-medium">Side</th>
              <th className="text-right pb-2 font-medium">Price</th>
              <th className="text-right pb-2 font-medium hidden sm:table-cell">Qty</th>
              <th className="text-right pb-2 font-medium">Time</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {trades.map(t => (
              <tr key={t.id} className="hover:bg-gray-800/30 transition-colors">
                <td className="py-2.5 font-bold text-white">{t.ticker}</td>
                <td className="py-2.5">
                  <span className={t.side === 'buy' ? 'badge-buy' : 'badge-sell'}>
                    {t.side?.toUpperCase()}
                  </span>
                </td>
                <td className="py-2.5 text-right text-gray-300">
                  {t.filled_price ? `$${Number(t.filled_price).toFixed(2)}` : '—'}
                </td>
                <td className="py-2.5 text-right text-gray-500 hidden sm:table-cell">
                  {t.qty ? Number(t.qty).toFixed(3) : '—'}
                </td>
                <td className="py-2.5 text-right text-gray-500 text-xs">{timeAgo(t.filled_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
