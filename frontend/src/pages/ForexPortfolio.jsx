import { useEffect, useState, useCallback, useRef } from 'react'
import { api } from '../api'

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt = (v, d = 2) =>
  v == null ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })

const fmtRate = (v, pair) => {
  if (v == null) return '—'
  // JPY pairs quote to 3 decimals; others to 5
  const decimals = (pair || '').includes('JPY') || (pair || '').includes('MXN') ? 3 : 5
  return Number(v).toFixed(decimals)
}

const fmtPct = (v) => {
  if (v == null) return '—'
  const n = Number(v) * 100
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`
}

const fmtPL = (v) => {
  if (v == null) return '—'
  const n = Number(v)
  return `${n >= 0 ? '+' : ''}$${fmt(Math.abs(n))}`
}

function timeAgo(ts) {
  if (!ts) return ''
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000)
  if (diff < 60)  return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

// ── Live Rates Strip ──────────────────────────────────────────────────────────
function RatesStrip({ rates }) {
  if (!rates || rates.length === 0) return null
  // Duplicate for seamless scroll
  const items = [...rates, ...rates]
  return (
    <div className="overflow-hidden relative border-b border-white/5 bg-gray-900/40">
      <div className="flex animate-marquee whitespace-nowrap py-2">
        {items.map((r, i) => {
          const carry = r.carry_differential
          const carryColor = carry > 0 ? 'text-green-400' : carry < 0 ? 'text-red-400' : 'text-gray-500'
          return (
            <span key={i} className="inline-flex items-center gap-2 px-5 text-xs">
              <span className="font-bold text-white tracking-wide">{r.pair}</span>
              <span className="text-gray-300 font-mono">{r.rate ? fmtRate(r.rate, r.pair) : '—'}</span>
              {carry != null && (
                <span className={`text-[10px] ${carryColor}`}>
                  {carry > 0 ? '+' : ''}{carry}% carry
                </span>
              )}
              <span className="text-gray-700 mx-2">|</span>
            </span>
          )
        })}
      </div>
    </div>
  )
}

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, color }) {
  return (
    <div className="bg-gray-900/60 border border-white/8 rounded-xl p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-xl font-bold ${color || 'text-white'}`}>{value}</div>
      {sub && <div className="text-xs text-gray-600 mt-0.5">{sub}</div>}
    </div>
  )
}

// ── Positions table ───────────────────────────────────────────────────────────
function PositionsTable({ positions }) {
  if (!positions || positions.length === 0) {
    return (
      <div className="text-center py-16 text-gray-600">
        <div className="text-4xl mb-3">💱</div>
        <div className="text-sm">No open forex positions</div>
        <div className="text-xs mt-1">The committee runs twice daily and will open positions when it finds strong signals</div>
      </div>
    )
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-600 border-b border-white/5">
            <th className="text-left py-2 pr-4 font-medium">Pair</th>
            <th className="text-left py-2 pr-4 font-medium">Direction</th>
            <th className="text-right py-2 pr-4 font-medium">Notional</th>
            <th className="text-right py-2 pr-4 font-medium">Entry Rate</th>
            <th className="text-right py-2 pr-4 font-medium">Current Rate</th>
            <th className="text-right py-2 pr-4 font-medium">P&L</th>
            <th className="text-right py-2 font-medium">Return</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => {
            const isLong  = p.direction === 'long'
            const plPos   = p.unrealized_pl >= 0
            const plColor = plPos ? 'text-green-400' : 'text-red-400'
            return (
              <tr key={p.pair} className="border-b border-white/5 hover:bg-white/2 transition-colors">
                <td className="py-3 pr-4 font-bold text-white tracking-wide">{p.pair}</td>
                <td className="py-3 pr-4">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    isLong
                      ? 'bg-green-500/15 text-green-400 border border-green-500/30'
                      : 'bg-red-500/15 text-red-400 border border-red-500/30'
                  }`}>
                    {isLong ? '▲ LONG' : '▼ SHORT'}
                  </span>
                </td>
                <td className="py-3 pr-4 text-right text-gray-300">${fmt(p.notional_usd)}</td>
                <td className="py-3 pr-4 text-right font-mono text-gray-400">{fmtRate(p.entry_rate, p.pair)}</td>
                <td className="py-3 pr-4 text-right font-mono text-white">{fmtRate(p.current_rate, p.pair)}</td>
                <td className={`py-3 pr-4 text-right font-medium ${plColor}`}>{fmtPL(p.unrealized_pl)}</td>
                <td className={`py-3 text-right font-medium ${plColor}`}>{fmtPct(p.unrealized_plpc)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Trades table ──────────────────────────────────────────────────────────────
function TradesTable({ trades, loading }) {
  if (loading) return <div className="text-center py-10 text-gray-600 text-sm">Loading trades…</div>
  if (!trades || trades.length === 0) {
    return (
      <div className="text-center py-16 text-gray-600">
        <div className="text-4xl mb-3">📋</div>
        <div className="text-sm">No trades yet</div>
      </div>
    )
  }

  const SIDE_LABELS = {
    buy:       { label: 'BUY',        color: 'text-green-400 bg-green-500/10 border-green-500/30' },
    sell:      { label: 'SELL',       color: 'text-red-400 bg-red-500/10 border-red-500/30' },
    sell_short:{ label: 'SHORT OPEN', color: 'text-orange-400 bg-orange-500/10 border-orange-500/30' },
    buy_cover: { label: 'SHORT CLOSE',color: 'text-blue-400 bg-blue-500/10 border-blue-500/30' },
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-600 border-b border-white/5">
            <th className="text-left py-2 pr-4 font-medium">Pair</th>
            <th className="text-left py-2 pr-4 font-medium">Side</th>
            <th className="text-right py-2 pr-4 font-medium">Rate</th>
            <th className="text-right py-2 pr-4 font-medium">Notional</th>
            <th className="text-right py-2 font-medium">Time</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => {
            const sc = SIDE_LABELS[t.side] || { label: t.side?.toUpperCase(), color: 'text-gray-400' }
            return (
              <tr key={t.id} className="border-b border-white/5 hover:bg-white/2 transition-colors">
                <td className="py-2.5 pr-4 font-bold text-white">{t.pair}</td>
                <td className="py-2.5 pr-4">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${sc.color}`}>
                    {sc.label}
                  </span>
                </td>
                <td className="py-2.5 pr-4 text-right font-mono text-gray-300">
                  {fmtRate(t.filled_price, t.pair)}
                </td>
                <td className="py-2.5 pr-4 text-right text-gray-400">
                  {t.notional_usd ? `$${fmt(t.notional_usd)}` : '—'}
                </td>
                <td className="py-2.5 text-right text-gray-600">{timeAgo(t.filled_at)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ForexPortfolio() {
  const [tab,         setTab]       = useState('holdings')
  const [portfolio,   setPortfolio] = useState(null)
  const [stats,       setStats]     = useState(null)
  const [rates,       setRates]     = useState([])
  const [trades,      setTrades]    = useState([])
  const [tradesTotal, setTTotal]    = useState(0)
  const [tradePage,   setTPage]     = useState(1)
  const [tradesLoading, setTLoad]   = useState(false)
  const [refreshing,  setRefreshing]= useState(false)
  const [lastUpdated, setLastUpdated]= useState(null)
  const [ago,         setAgo]       = useState('')

  // Refresh portfolio + stats + rates
  const refresh = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true)
    try {
      const [portData, statsData, ratesData] = await Promise.all([
        api.forexPortfolio(),
        api.forexStats(),
        api.forexRates(),
      ])
      setPortfolio(portData)
      setStats(statsData)
      setRates(ratesData?.rates || [])
      setLastUpdated(new Date())
    } catch (e) {
      console.error('Forex refresh error:', e)
    } finally {
      if (showSpinner) setRefreshing(false)
    }
  }, [])

  // Fetch trades (paginated)
  const fetchTrades = useCallback(async (page) => {
    setTLoad(true)
    try {
      const data = await api.forexTrades(page)
      setTrades(data.items || [])
      setTTotal(data.total || 0)
    } catch (e) {
      console.error('Forex trades error:', e)
    } finally {
      setTLoad(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(() => refresh(), 60_000)
    return () => clearInterval(id)
  }, [refresh])

  useEffect(() => {
    if (tab === 'trades') fetchTrades(tradePage)
  }, [tab, tradePage, fetchTrades])

  // Update "X ago" ticker
  useEffect(() => {
    const id = setInterval(() => {
      if (lastUpdated) setAgo(timeAgo(lastUpdated))
    }, 1000)
    return () => clearInterval(id)
  }, [lastUpdated])

  // ── Derived values ──
  const positions      = portfolio?.positions || []
  const totalValue     = portfolio?.total_value ?? 1_000_000
  const cash           = portfolio?.cash ?? 1_000_000
  const totalUnrPL     = portfolio?.total_unrealized_pl ?? 0
  const totalPL        = stats?.total_pl_usd
  const returnPct      = stats?.total_return_pct
  const totalTrades    = stats?.total_trades ?? 0
  const winRate        = stats?.win_rate

  const plColor    = (totalPL ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'
  const unrPLColor = totalUnrPL >= 0 ? 'text-green-400' : 'text-red-400'

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-4">

      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-white tracking-tight">💱 Forex Trading</h1>
          <p className="text-xs text-gray-600 mt-0.5">
            AI committee trades major currency pairs • $1M starting balance
          </p>
        </div>
        <div className="flex items-center gap-3">
          {ago && <span className="text-xs text-gray-600">Updated {ago}</span>}
          <button
            onClick={() => refresh(true)}
            disabled={refreshing}
            className="px-3 py-1.5 text-xs rounded-lg border border-white/10 bg-gray-900 hover:bg-gray-800 text-gray-300 transition-colors disabled:opacity-40"
          >
            {refreshing ? '⟳' : '↺'} Refresh
          </button>
        </div>
      </div>

      {/* ── Live rates strip ── */}
      <RatesStrip rates={rates} />

      {/* ── Stat cards ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Portfolio Value"
          value={`$${fmt(totalValue)}`}
          sub="Cash + open positions"
        />
        <StatCard
          label="Available Cash"
          value={`$${fmt(cash)}`}
          sub="Ready to deploy"
        />
        <StatCard
          label="Total P&L"
          value={totalPL != null ? fmtPL(totalPL) : `$${fmt(totalUnrPL)}`}
          sub={returnPct != null ? `${returnPct > 0 ? '+' : ''}${returnPct.toFixed(2)}% return` : 'Unrealized'}
          color={plColor}
        />
        <StatCard
          label="Total Trades"
          value={totalTrades}
          sub={winRate != null ? `${(winRate * 100).toFixed(0)}% win rate` : 'All time'}
        />
      </div>

      {/* ── Strategy info cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[
          { icon: '📈', title: 'Trend Following', desc: 'EMA alignment + MACD across daily and weekly charts' },
          { icon: '💰', title: 'Carry Trade', desc: 'Borrow cheap currencies, invest in high-yield ones' },
          { icon: '🌍', title: 'Macro Signals', desc: 'Dollar index trend, VIX risk-off, safe-haven flows' },
        ].map(s => (
          <div key={s.title} className="bg-gray-900/40 border border-white/5 rounded-xl p-3">
            <div className="text-base mb-1">{s.icon}</div>
            <div className="text-xs font-semibold text-gray-300">{s.title}</div>
            <div className="text-[11px] text-gray-600 mt-0.5 leading-relaxed">{s.desc}</div>
          </div>
        ))}
      </div>

      {/* ── Tab bar ── */}
      <div className="flex gap-1 bg-gray-900/60 p-1 rounded-xl border border-white/5 w-fit">
        {[['holdings', 'Open Positions'], ['trades', 'Trade History']].map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`px-4 py-1.5 rounded-lg text-xs font-medium transition-all ${
              tab === id ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            {label}
            {id === 'holdings' && positions.length > 0 && (
              <span className="ml-1.5 bg-indigo-500/40 text-indigo-200 text-[10px] px-1.5 py-0.5 rounded-full">
                {positions.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Content panel ── */}
      <div className="bg-gray-900/40 border border-white/8 rounded-xl p-4">
        {tab === 'holdings' && <PositionsTable positions={positions} />}
        {tab === 'trades' && (
          <div className="space-y-4">
            <TradesTable trades={trades} loading={tradesLoading} />
            {tradesTotal > 20 && (
              <div className="flex items-center justify-between pt-2 border-t border-white/5">
                <span className="text-xs text-gray-600">{tradesTotal} total trades</span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setTPage(p => Math.max(1, p - 1))}
                    disabled={tradePage === 1}
                    className="px-3 py-1 text-xs rounded border border-white/10 bg-gray-900 text-gray-400 hover:text-white disabled:opacity-30"
                  >
                    ← Prev
                  </button>
                  <span className="text-xs text-gray-600 px-2 py-1">
                    Page {tradePage}
                  </span>
                  <button
                    onClick={() => setTPage(p => p + 1)}
                    disabled={tradePage * 20 >= tradesTotal}
                    className="px-3 py-1 text-xs rounded border border-white/10 bg-gray-900 text-gray-400 hover:text-white disabled:opacity-30"
                  >
                    Next →
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Pairs info ── */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
        {rates.map(r => {
          const carryPos = (r.carry_differential ?? 0) > 0
          return (
            <div key={r.pair} className="bg-gray-900/30 border border-white/5 rounded-lg p-2.5 text-center">
              <div className="text-xs font-bold text-gray-300">{r.pair}</div>
              <div className="text-sm font-mono text-white mt-0.5">
                {r.rate ? fmtRate(r.rate, r.pair) : '—'}
              </div>
              <div className={`text-[10px] mt-0.5 ${carryPos ? 'text-green-500' : 'text-red-500'}`}>
                {(r.carry_differential ?? 0) > 0 ? '+' : ''}{r.carry_differential ?? 0}% carry
              </div>
            </div>
          )
        })}
      </div>

    </div>
  )
}
