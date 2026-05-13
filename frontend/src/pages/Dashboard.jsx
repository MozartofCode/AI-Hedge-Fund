import { useCallback, useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { api } from '../api'
import PortfolioStats from '../components/PortfolioStats'
import Heatmap from '../components/Heatmap'
import TradeLog from '../components/TradeLog'

// Basic sector map for the 10 watchlist tickers
const SECTOR_MAP = {
  AAPL: 'Technology', NVDA: 'Technology', MSFT: 'Technology',
  META: 'Technology', GOOGL: 'Technology',
  TSLA: 'Consumer Disc', AMZN: 'Consumer Disc',
  JPM: 'Financials', XOM: 'Energy', SPY: 'ETF',
}
const SECTOR_COLORS = {
  Technology: '#6366f1', 'Consumer Disc': '#f59e0b',
  Financials: '#3b82f6', Energy: '#10b981', ETF: '#8b5cf6', Other: '#6b7280',
}

function SectorBar({ positions }) {
  if (!positions?.length) return null
  const total = positions.reduce((s, p) => s + (p.market_value || 0), 0)
  if (!total) return null

  const sectors = {}
  positions.forEach(p => {
    const s = SECTOR_MAP[p.ticker] || 'Other'
    sectors[s] = (sectors[s] || 0) + p.market_value
  })

  return (
    <div className="card">
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Sector Exposure</h3>
      <div className="flex h-5 rounded-full overflow-hidden gap-px mb-2">
        {Object.entries(sectors).map(([sector, val]) => (
          <div
            key={sector}
            style={{ width: `${(val / total * 100).toFixed(1)}%`, background: SECTOR_COLORS[sector] }}
            title={`${sector}: ${(val / total * 100).toFixed(1)}%`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {Object.entries(sectors).map(([sector, val]) => (
          <div key={sector} className="flex items-center gap-1.5 text-xs text-gray-400">
            <span className="w-2 h-2 rounded-sm" style={{ background: SECTOR_COLORS[sector] }} />
            {sector}
            <span className="text-gray-600">{(val / total * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function EquityChart({ data }) {
  if (!data?.length) {
    return (
      <div className="card flex items-center justify-center h-52 text-gray-600 text-sm">
        Equity chart populates after first portfolio snapshot
      </div>
    )
  }

  const isPositive = data[data.length - 1]?.pl >= 0

  return (
    <div className="card">
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Equity Curve</h3>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis
            dataKey="date"
            tick={{ fill: '#6b7280', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: '#6b7280', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={v => `$${(v / 1000).toFixed(0)}k`}
            width={44}
          />
          <Tooltip
            contentStyle={{ background: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: '#9ca3af' }}
            formatter={v => [`$${Number(v).toLocaleString('en-US', { minimumFractionDigits: 2 })}`, 'Equity']}
          />
          <Line
            type="monotone"
            dataKey="equity"
            stroke={isPositive ? '#22c55e' : '#ef4444'}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function RefreshBadge({ lastUpdated }) {
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

  if (!lastUpdated) return null
  return (
    <span className="text-xs text-gray-600">Updated {ago} · auto-refreshes every 60s</span>
  )
}

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState(null)
  const [stats, setStats] = useState(null)
  const [trades, setTrades] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const [portData, statsData, tradesData] = await Promise.all([
        api.portfolio(),
        api.stats(),
        api.trades(1, 10),
      ])
      setPortfolio(portData)
      setStats(statsData)
      setTrades(tradesData.items ?? [])
      setLastUpdated(new Date())
    } catch (e) {
      console.error('Dashboard refresh failed:', e)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 60_000)
    return () => clearInterval(id)
  }, [refresh])

  const positions = portfolio?.positions ?? []

  return (
    <div className="space-y-4">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-white">Portfolio Dashboard</h1>
        <RefreshBadge lastUpdated={lastUpdated} />
      </div>

      {/* Stats bar */}
      <PortfolioStats stats={stats} portfolio={portfolio} />

      {/* Heatmap + Equity chart */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-3">
          <Heatmap positions={positions} />
        </div>
        <div className="lg:col-span-2">
          <EquityChart data={stats?.daily_equity ?? []} />
        </div>
      </div>

      {/* Sector exposure */}
      <SectorBar positions={positions} />

      {/* Trades */}
      <TradeLog trades={trades} />
    </div>
  )
}
