const fmt = {
  usd: v => v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—',
  pct: v => v != null ? `${v >= 0 ? '+' : ''}${Number(v).toFixed(2)}%` : '—',
  ratio: v => v != null ? Number(v).toFixed(2) : '—',
  num: v => v != null ? Number(v).toLocaleString() : '—',
}

function StatCard({ label, value, sub, positive, negative, neutral }) {
  const subColor = positive ? 'text-green-400' : negative ? 'text-red-400' : 'text-gray-500'
  return (
    <div className="card flex flex-col gap-1 min-w-0">
      <span className="text-xs font-medium text-gray-500 uppercase tracking-wider truncate">{label}</span>
      <span className="text-xl font-bold text-white truncate">{value}</span>
      {sub && <span className={`text-xs font-medium ${subColor}`}>{sub}</span>}
    </div>
  )
}

export default function PortfolioStats({ stats, portfolio }) {
  if (!stats && !portfolio) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="card animate-pulse h-20 bg-gray-800/50" />
        ))}
      </div>
    )
  }

  const totalValue = stats?.total_value ?? portfolio?.total_value
  const cash = stats?.cash ?? portfolio?.cash
  const pl = stats?.total_pl_usd
  const plPct = stats?.total_return_pct
  const winRate = stats?.win_rate
  const sharpe = stats?.sharpe_ratio
  const trades = stats?.total_trades

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
      <StatCard label="Portfolio Value" value={fmt.usd(totalValue)} />
      <StatCard label="Cash" value={fmt.usd(cash)} />
      <StatCard
        label="Total P&L"
        value={fmt.usd(pl)}
        sub={fmt.pct(plPct)}
        positive={pl > 0}
        negative={pl < 0}
      />
      <StatCard
        label="Win Rate"
        value={winRate != null ? `${(winRate * 100).toFixed(1)}%` : '—'}
        sub={winRate != null ? `${Math.round(winRate * 100)}% of trades` : 'no closed trades'}
        neutral
      />
      <StatCard
        label="Sharpe Ratio"
        value={fmt.ratio(sharpe)}
        sub={sharpe != null ? (sharpe >= 1 ? 'Good' : sharpe >= 0.5 ? 'Fair' : 'Low') : 'insufficient data'}
        positive={sharpe >= 1}
        negative={sharpe != null && sharpe < 0.5}
      />
      <StatCard label="Total Trades" value={fmt.num(trades)} />
    </div>
  )
}
