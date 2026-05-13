import { Treemap, ResponsiveContainer, Tooltip } from 'recharts'

function heatColor(plPct) {
  const v = Math.max(-10, Math.min(10, plPct ?? 0))
  if (v === 0) return '#374151'
  if (v > 0) {
    const t = v / 10
    return `rgb(${Math.round(55 + (21 - 55) * t)},${Math.round(65 + (128 - 65) * t)},${Math.round(81 + (61 - 81) * t)})`
  }
  const t = Math.abs(v) / 10
  return `rgb(${Math.round(55 + (220 - 55) * t)},${Math.round(65 + (38 - 65) * t)},${Math.round(81 + (38 - 81) * t)})`
}

function TreemapCell(props) {
  const { x, y, width, height, name, plPct, unrealizedPl } = props
  const fill = heatColor(plPct)
  const showLabel = width > 45 && height > 32
  const showSub = width > 55 && height > 52
  const plSign = plPct >= 0 ? '+' : ''

  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={fill} stroke="#030712" strokeWidth={2} rx={3} />
      {showLabel && (
        <text x={x + width / 2} y={y + height / 2 - (showSub ? 8 : 0)} textAnchor="middle" fill="white"
          fontSize={Math.min(14, width / 4)} fontWeight="700" dominantBaseline="middle">
          {name}
        </text>
      )}
      {showSub && (
        <text x={x + width / 2} y={y + height / 2 + 12} textAnchor="middle"
          fill="rgba(255,255,255,0.75)" fontSize={Math.min(11, width / 5)} dominantBaseline="middle">
          {plSign}{plPct?.toFixed(2)}%
        </text>
      )}
    </g>
  )
}

function HeatTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 text-sm shadow-xl">
      <div className="font-bold text-white text-base mb-1">{d.name}</div>
      <div className="space-y-0.5 text-gray-300">
        <div className="flex justify-between gap-4"><span>Price</span><span>${d.currentPrice?.toFixed(2)}</span></div>
        <div className="flex justify-between gap-4"><span>Shares</span><span>{d.qty?.toFixed(4)}</span></div>
        <div className="flex justify-between gap-4"><span>Market Value</span><span>${d.marketValue?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span></div>
        <div className={`flex justify-between gap-4 font-semibold ${d.unrealizedPl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          <span>Unrealized P&L</span>
          <span>{d.unrealizedPl >= 0 ? '+' : ''}${d.unrealizedPl?.toFixed(2)} ({d.unrealizedPl >= 0 ? '+' : ''}{d.plPct?.toFixed(2)}%)</span>
        </div>
      </div>
    </div>
  )
}

export default function Heatmap({ positions }) {
  if (!positions?.length) {
    return (
      <div className="card flex items-center justify-center h-52 text-gray-600 text-sm">
        No open positions
      </div>
    )
  }

  const data = positions.map(p => ({
    name: p.ticker,
    size: Math.max(p.market_value, 1),
    plPct: parseFloat(p.unrealized_plpc) * 100,
    unrealizedPl: p.unrealized_pl,
    currentPrice: p.current_price,
    marketValue: p.market_value,
    qty: p.qty,
  }))

  return (
    <div className="card p-3">
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Holdings Heatmap</h3>
      <ResponsiveContainer width="100%" height={220}>
        <Treemap data={data} dataKey="size" stroke="none" content={<TreemapCell />}>
          <Tooltip content={<HeatTooltip />} />
        </Treemap>
      </ResponsiveContainer>
    </div>
  )
}
