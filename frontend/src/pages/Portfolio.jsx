import { useCallback, useEffect, useState } from 'react'
import { Treemap, ResponsiveContainer, Tooltip } from 'recharts'
import { api } from '../api'
import { CommitteeSessionBody } from './Trades'

// ── Helpers ──────────────────────────────────────────────────────────────────

const fmt = {
  usd:  v => v != null ? `$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—',
  pct:  v => v != null ? `${v >= 0 ? '+' : ''}${Number(v).toFixed(2)}%` : '—',
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

// ── Treemap cell ─────────────────────────────────────────────────────────────

function HeatCell(props) {
  const { x, y, width, height, name, plPct, onCellClick } = props
  const fill    = plColor(plPct)
  const canLabel = width > 40 && height > 30
  const canSub   = width > 52 && height > 52
  const sign     = plPct >= 0 ? '+' : ''

  return (
    <g
      onClick={() => onCellClick && onCellClick(name)}
      style={{ cursor: 'pointer' }}
    >
      <rect
        x={x + 1} y={y + 1}
        width={Math.max(0, width - 2)} height={Math.max(0, height - 2)}
        fill={fill}
        stroke="#030712" strokeWidth={2}
        rx={4}
      />
      {/* Hover highlight overlay */}
      <rect
        x={x + 1} y={y + 1}
        width={Math.max(0, width - 2)} height={Math.max(0, height - 2)}
        fill="transparent"
        stroke="rgba(255,255,255,0.25)" strokeWidth={0}
        rx={4}
        className="hover-cell-highlight"
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

function HeatTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const plPositive = d.unrealizedPl >= 0
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-xl p-3.5 text-sm shadow-2xl min-w-[200px]">
      <div className="font-bold text-white text-base mb-2">{d.name}</div>
      <div className="space-y-1 text-gray-300">
        <Row label="Current Price" value={`$${d.currentPrice?.toFixed(2)}`} />
        <Row label="Shares"        value={d.qty?.toFixed(4)} />
        <Row label="Market Value"  value={fmt.usd(d.marketValue)} />
        <Row label="Avg Entry"     value={`$${d.avgEntry?.toFixed(2)}`} />
        <div className={`flex justify-between font-semibold pt-1 border-t border-gray-700/60 ${plPositive ? 'text-green-400' : 'text-red-400'}`}>
          <span>Unrealized P&L</span>
          <span>{plPositive ? '+' : ''}${d.unrealizedPl?.toFixed(2)} ({plPositive ? '+' : ''}{d.plPct?.toFixed(2)}%)</span>
        </div>
        <p className="text-gray-600 text-xs pt-1">Click to see committee analysis →</p>
      </div>
    </div>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-gray-500">{label}</span>
      <span>{value}</span>
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

  return (
    <div
      className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700/80 rounded-2xl w-full max-w-2xl max-h-[85vh] overflow-y-auto shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-gray-800 sticky top-0 bg-gray-900 rounded-t-2xl z-10">
          <div>
            <div className="flex items-center gap-3">
              <span className="text-xl font-black text-white">{position.name}</span>
              <span className={`text-sm font-bold ${plPositive ? 'text-green-400' : 'text-red-400'}`}>
                {plPositive ? '+' : ''}{position.plPct?.toFixed(2)}%
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              {position.qty?.toFixed(4)} shares · Avg entry ${position.avgEntry?.toFixed(2)} · Current ${position.currentPrice?.toFixed(2)}
            </p>
            <p className={`text-xs font-semibold mt-0.5 ${plPositive ? 'text-green-400' : 'text-red-400'}`}>
              Unrealized P&L: {plPositive ? '+' : ''}${position.unrealizedPl?.toFixed(2)}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-600 hover:text-gray-200 transition-colors text-xl leading-none mt-0.5 ml-4"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4">
          {!loading && sessionData && (
            <p className="text-xs text-gray-600">
              Latest committee session: {new Date(sessionData.session_timestamp).toLocaleString()}
            </p>
          )}
          <CommitteeSessionBody sessionData={sessionData} loading={loading} error={error} />
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Portfolio() {
  const [portfolio, setPortfolio]         = useState(null)
  const [stats, setStats]                 = useState(null)
  const [lastUpdated, setLastUpdated]     = useState(null)
  const [refreshing, setRefreshing]       = useState(false)
  const [selectedPosition, setSelectedPosition] = useState(null)

  const refresh = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true)
    try {
      const [portData, statsData] = await Promise.all([api.portfolio(), api.stats()])
      setPortfolio(portData)
      setStats(statsData)
      setLastUpdated(new Date())
    } catch (e) {
      console.error('Portfolio refresh failed:', e)
    } finally {
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 60_000)
    return () => clearInterval(id)
  }, [refresh])

  const positions   = portfolio?.positions ?? []
  const totalValue  = stats?.total_value ?? portfolio?.total_value
  const cash        = stats?.cash ?? portfolio?.cash
  const pl          = stats?.total_pl_usd
  const plPct       = stats?.total_return_pct
  const trades      = stats?.total_trades

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

  // Build a quick lookup so the modal can find position details by ticker
  const positionByName = Object.fromEntries(heatData.map(p => [p.name, p]))

  const handleCellClick = (name) => {
    const pos = positionByName[name]
    if (pos) setSelectedPosition(pos)
  }

  const [ago, setAgo] = useState('')
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

  return (
    <>
      {selectedPosition && (
        <PositionModal
          position={selectedPosition}
          onClose={() => setSelectedPosition(null)}
        />
      )}

      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-end">
          <div className="flex items-center gap-3">
            {lastUpdated && (
              <span className="text-xs text-gray-600">Updated {ago}</span>
            )}
            <button
              onClick={() => refresh(true)}
              disabled={refreshing}
              className="text-xs px-3 py-1.5 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors disabled:opacity-40 flex items-center gap-1.5"
            >
              <span className={refreshing ? 'animate-spin' : ''}>↺</span> Refresh
            </button>
          </div>
        </div>

        {/* Stats strip — 4 cards, no Win Rate or Sharpe */}
        {!portfolio && !stats ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="card animate-pulse h-20 bg-gray-800/50" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Portfolio Value" value={fmt.usd(totalValue)} />
            <StatCard label="Cash" value={fmt.usd(cash)} />
            <StatCard
              label="Total P&L"
              value={fmt.usd(pl)}
              sub={fmt.pct(plPct)}
              color={pl > 0 ? 'green' : pl < 0 ? 'red' : null}
            />
            <StatCard label="Total Trades" value={trades != null ? Number(trades).toLocaleString() : '—'} />
          </div>
        )}

        {/* Hero heatmap */}
        <div className="card p-4">
          {heatData.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-80 gap-3">
              <span className="text-4xl">📭</span>
              <p className="text-gray-500 text-sm">No open positions yet</p>
              <p className="text-gray-600 text-xs">The committee will buy stocks automatically during market hours</p>
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
                  <Tooltip content={<HeatTooltip />} />
                </Treemap>
              </ResponsiveContainer>
            </>
          )}
        </div>
      </div>
    </>
  )
}
