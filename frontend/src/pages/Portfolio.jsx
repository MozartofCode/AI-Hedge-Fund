import { useCallback, useEffect, useState } from 'react'
import { Treemap, ResponsiveContainer, Tooltip } from 'recharts'
import { api } from '../api'
import { CommitteeSessionBody } from './Trades'
import Trades from './Trades'

// ── Market configuration (US only) ────────────────────────────────────────────

const MARKET = { flag: '🇺🇸', name: 'United States', exchange: 'NYSE / NASDAQ', currency: '$' }
const SYMBOL = MARKET.currency

// ── Helpers ───────────────────────────────────────────────────────────────────

// Compact form (e.g. $1.23M) — used in tight spaces like heatmap tooltips.
function fmtCurrency(v, symbol = '$') {
  if (v == null) return '—'
  const abs = Math.abs(v)
  let str
  if (abs >= 1_000_000_000) str = `${(v / 1_000_000_000).toFixed(2)}B`
  else if (abs >= 1_000_000) str = `${(v / 1_000_000).toFixed(2)}M`
  else str = Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${symbol}${str}`
}

// Full form (e.g. $1,004,000.00) — used for headline stats so small gains/losses
// like a few thousand dollars on a $1M balance are never rounded away.
function fmtMoney(v, symbol = '$') {
  if (v == null) return '—'
  const sign = v < 0 ? '-' : ''
  return `${sign}${symbol}${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtPct(v) {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`
}

function plColor(plPct) {
  const v = Math.max(-15, Math.min(15, plPct ?? 0))
  if (v === 0) return '#374151'
  if (v > 0) {
    const t = v / 15
    return `rgb(${Math.round(22 + (20 - 22) * t)},${Math.round(101 + (83 - 101) * t)},${Math.round(52 + (45 - 52) * t)})`
  }
  const t = Math.abs(v) / 15
  return `rgb(${Math.round(127 + (185 - 127) * t)},${Math.round(29 + (28 - 29) * t)},${Math.round(29 + (28 - 29) * t)})`
}

// ── Treemap cell ──────────────────────────────────────────────────────────────

function HeatCell(props) {
  const { x, y, width, height, name, plPct, onCellClick } = props
  const fill    = plColor(plPct)
  const canLabel = width > 40 && height > 30
  const canSub   = width > 52 && height > 52
  const sign     = plPct >= 0 ? '+' : ''

  return (
    <g onClick={() => onCellClick && onCellClick(name)} style={{ cursor: 'pointer' }}>
      <rect
        x={x + 1} y={y + 1}
        width={Math.max(0, width - 2)} height={Math.max(0, height - 2)}
        fill={fill} stroke="#030712" strokeWidth={2} rx={4}
      />
      {canLabel && (
        <text
          x={x + width / 2} y={y + height / 2 - (canSub ? 9 : 0)}
          textAnchor="middle" dominantBaseline="middle"
          fill="white" fontWeight="700"
          fontSize={Math.min(16, Math.max(10, width / 5))}
          style={{ pointerEvents: 'none', userSelect: 'none' }}
        >
          {name}
        </text>
      )}
      {canSub && (
        <text
          x={x + width / 2} y={y + height / 2 + 11}
          textAnchor="middle" dominantBaseline="middle"
          fill="rgba(255,255,255,0.80)"
          fontSize={Math.min(12, Math.max(9, width / 7))}
          style={{ pointerEvents: 'none', userSelect: 'none' }}
        >
          {sign}{plPct?.toFixed(2)}%
        </text>
      )}
    </g>
  )
}

function HeatTooltip({ active, payload, currencySymbol }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const sym = currencySymbol || '$'
  const plPositive = d.unrealizedPl >= 0
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl p-3.5 text-sm shadow-2xl min-w-[200px]">
      <div className="font-bold text-white text-base mb-2">{d.name}</div>
      <div className="space-y-1 text-gray-300">
        <div className="flex justify-between gap-4"><span className="text-gray-500">Current Price</span><span>{sym}{d.currentPrice?.toFixed(2)}</span></div>
        <div className="flex justify-between gap-4"><span className="text-gray-500">Shares</span><span>{d.qty?.toFixed(4)}</span></div>
        <div className="flex justify-between gap-4"><span className="text-gray-500">Market Value</span><span>{fmtCurrency(d.marketValue, sym)}</span></div>
        <div className="flex justify-between gap-4"><span className="text-gray-500">Avg Entry</span><span>{sym}{d.avgEntry?.toFixed(2)}</span></div>
        <div className={`flex justify-between font-semibold pt-1 border-t border-gray-700/60 ${plPositive ? 'text-green-400' : 'text-red-400'}`}>
          <span>Unrealized P&L</span>
          <span>{plPositive ? '+' : ''}{sym}{d.unrealizedPl?.toFixed(2)} ({plPositive ? '+' : ''}{d.plPct?.toFixed(2)}%)</span>
        </div>
        <p className="text-gray-600 text-xs pt-1">Click to see committee analysis →</p>
      </div>
    </div>
  )
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, sub, color }) {
  const subColor = color === 'green' ? 'text-green-400' : color === 'red' ? 'text-red-400' : 'text-gray-500'
  return (
    <div className="card flex flex-col gap-0.5 min-w-0">
      <span className="text-xs font-medium text-gray-500 uppercase tracking-wider truncate">{label}</span>
      <span className="text-xl font-bold text-white truncate">{value}</span>
      {sub && <span className={`text-xs font-medium ${subColor}`}>{sub}</span>}
    </div>
  )
}

// ── Position Detail Modal ─────────────────────────────────────────────────────

function PositionModal({ position, onClose }) {
  const [sessionData, setSessionData] = useState(null)
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState(null)

  useEffect(() => {
    api.latestSession(position.name)
      .then(d => { setSessionData(d); setLoading(false) })
      .catch(() => { setError('No committee session found for this position.'); setLoading(false) })
  }, [position.name])

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const plPositive = position.unrealizedPl >= 0
  const sym = SYMBOL

  return (
    <div
      className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700/80 rounded-2xl w-full max-w-2xl max-h-[85vh] overflow-y-auto shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between p-5 border-b border-gray-800 sticky top-0 bg-gray-900 rounded-t-2xl z-10">
          <div>
            <div className="flex items-center gap-3">
              <span className="text-xl font-black text-white">{position.name}</span>
              <span className={`text-sm font-bold ${plPositive ? 'text-green-400' : 'text-red-400'}`}>
                {plPositive ? '+' : ''}{position.plPct?.toFixed(2)}%
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              {position.qty?.toFixed(4)} shares · Avg entry {sym}{position.avgEntry?.toFixed(2)} · Current {sym}{position.currentPrice?.toFixed(2)}
            </p>
            <p className={`text-xs font-semibold mt-0.5 ${plPositive ? 'text-green-400' : 'text-red-400'}`}>
              Unrealized P&L: {plPositive ? '+' : ''}{sym}{position.unrealizedPl?.toFixed(2)}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-600 hover:text-gray-200 transition-colors text-xl leading-none mt-0.5 ml-4">✕</button>
        </div>
        <div className="p-5 space-y-4">
          {!loading && sessionData && (
            <p className="text-xs text-gray-600">Latest committee session: {new Date(sessionData.session_timestamp).toLocaleString()}</p>
          )}
          <CommitteeSessionBody sessionData={sessionData} loading={loading} error={error} />
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Portfolio() {
  const [tab, setTab]                     = useState('holdings')
  const [portfolio, setPortfolio]         = useState(null)
  const [stats, setStats]                 = useState(null)
  const [lastUpdated, setLastUpdated]     = useState(null)
  const [refreshing, setRefreshing]       = useState(false)
  const [selectedPosition, setSelectedPosition] = useState(null)
  const [isOpen, setIsOpen]               = useState(false)
  const [ago, setAgo]                     = useState('')

  // Fetch health (US market open/closed status)
  useEffect(() => {
    const fetch = () => api.health()
      .then(d => setIsOpen(!!d.market_open))
      .catch(() => {})
    fetch()
    const id = setInterval(fetch, 60_000)
    return () => clearInterval(id)
  }, [])

  const refresh = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true)
    // Fetch independently so holdings + portfolio value render the moment the
    // portfolio responds, without waiting on the slower stats call.
    const pPort  = api.portfolio().then(setPortfolio).catch(e => console.error('Portfolio fetch failed:', e))
    const pStats = api.stats().then(setStats).catch(e => console.error('Stats fetch failed:', e))
    await Promise.allSettled([pPort, pStats])
    setLastUpdated(new Date())
    setRefreshing(false)
  }, [])

  // Initial fetch + 60s auto-refresh
  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 60_000)
    return () => clearInterval(id)
  }, [refresh])

  // "Updated X ago" counter
  useEffect(() => {
    if (!lastUpdated) return
    const tick = () => {
      const s = Math.floor((Date.now() - lastUpdated.getTime()) / 1000)
      setAgo(s < 5 ? 'just now' : `${s}s ago`)
    }
    tick()
    const id = setInterval(tick, 5000)
    return () => clearInterval(id)
  }, [lastUpdated])

  const cfg          = MARKET
  const sym          = SYMBOL
  const positions    = portfolio?.positions ?? []
  const totalValue   = stats?.total_value ?? portfolio?.total_value
  const cash         = stats?.cash ?? portfolio?.cash
  const pl           = stats?.total_pl_usd
  const plPct        = stats?.total_return_pct
  const trades       = stats?.total_trades

  const heatData = positions.map(p => ({
    name:         p.ticker,
    size:         Math.max(p.market_value ?? 1, 1),
    plPct:        (p.unrealized_plpc ?? 0) * 100,
    unrealizedPl: p.unrealized_pl ?? 0,
    currentPrice: p.current_price,
    marketValue:  p.market_value,
    avgEntry:     p.avg_entry_price,
    qty:          p.qty,
  }))

  const positionByName = Object.fromEntries(heatData.map(p => [p.name, p]))
  const handleCellClick = (name) => {
    const pos = positionByName[name]
    if (pos) setSelectedPosition(pos)
  }

  return (
    <>
      {/* Position modal */}
      {selectedPosition && (
        <PositionModal
          position={selectedPosition}
          onClose={() => setSelectedPosition(null)}
        />
      )}

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5 space-y-4">

        {/* ── Top bar ── */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Market label (US only) */}
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-gray-800 border border-gray-700 text-sm font-medium text-white">
            <span className="text-xl leading-none">{cfg.flag}</span>
            <div className="text-left">
              <div className="font-semibold leading-tight">{cfg.name}</div>
              <div className="text-xs text-gray-500 leading-tight">{cfg.exchange}</div>
            </div>
          </div>

          {/* Market status */}
          <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-full border ${
            isOpen
              ? 'bg-green-500/10 text-green-400 border-green-500/25'
              : 'bg-gray-500/10 text-gray-500 border-gray-600/25'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${isOpen ? 'bg-green-400 animate-pulse' : 'bg-gray-500'}`} />
            {isOpen ? 'Market Open' : 'Market Closed'}
          </span>

          <div className="flex-1" />

          {/* Refresh */}
          <div className="flex items-center gap-2">
            {lastUpdated && <span className="text-xs text-gray-600 hidden sm:inline">Updated {ago}</span>}
            <button
              onClick={() => refresh(true)}
              disabled={refreshing}
              className="text-xs px-3 py-1.5 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors disabled:opacity-40 flex items-center gap-1.5"
            >
              <span className={refreshing ? 'animate-spin' : ''}>↺</span>
              <span className="hidden sm:inline">Refresh</span>
            </button>
          </div>
        </div>

        {/* ── Stats strip ── */}
        {!portfolio && !stats ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="card animate-pulse h-20 bg-gray-800/50" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Portfolio Value" value={fmtMoney(totalValue, sym)} />
            <StatCard label="Cash" value={fmtMoney(cash, sym)} />
            <StatCard
              label="Total P&L"
              value={fmtMoney(pl, sym)}
              sub={fmtPct(plPct)}
              color={pl > 0 ? 'green' : pl < 0 ? 'red' : null}
            />
            <StatCard label="Total Trades" value={trades != null ? Number(trades).toLocaleString() : '—'} />
          </div>
        )}

        {/* ── Tab toggle ── */}
        <div className="flex gap-1 bg-gray-800/50 rounded-xl p-1 w-fit">
          {[
            { key: 'holdings', label: 'Holdings', icon: '📊' },
            { key: 'trades',   label: 'Trades',   icon: '📋' },
          ].map(({ key, label, icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-semibold transition-colors ${
                tab === key
                  ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              <span>{icon}</span> {label}
            </button>
          ))}
        </div>

        {/* ── Content ── */}
        {tab === 'holdings' && (
          <div className="card p-4">
            {heatData.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-80 gap-3">
                <span className="text-4xl">📭</span>
                <p className="text-gray-500 text-sm">No open positions in {cfg.name}</p>
                <p className="text-gray-600 text-xs text-center max-w-xs">
                  The committee will automatically buy {cfg.exchange} stocks during trading hours
                </p>
              </div>
            ) : (
              <>
                <p className="text-xs text-gray-600 mb-3">Click any position to see the latest committee analysis</p>
                <ResponsiveContainer width="100%" height={380}>
                  <Treemap
                    data={heatData}
                    dataKey="size"
                    stroke="none"
                    content={(props) => <HeatCell {...props} onCellClick={handleCellClick} />}
                  >
                    <Tooltip content={<HeatTooltip currencySymbol={sym} />} />
                  </Treemap>
                </ResponsiveContainer>
              </>
            )}
          </div>
        )}

        {tab === 'trades' && (
          <Trades />
        )}

      </div>
    </>
  )
}
