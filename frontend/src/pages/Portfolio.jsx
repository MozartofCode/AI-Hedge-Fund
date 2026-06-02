import { useCallback, useEffect, useRef, useState } from 'react'
import { Treemap, ResponsiveContainer, Tooltip } from 'recharts'
import { api } from '../api'
import { CommitteeSessionBody } from './Trades'
import Trades from './Trades'

// ── Market configuration ──────────────────────────────────────────────────────

const MARKET_CONFIG = {
  US: { flag: '🇺🇸', name: 'United States', exchange: 'NYSE / NASDAQ', currency: '$',  currencyCode: 'USD' },
  BR: { flag: '🇧🇷', name: 'Brazil',         exchange: 'B3',            currency: 'R$', currencyCode: 'BRL' },
  AR: { flag: '🇦🇷', name: 'Argentina',      exchange: 'BYMA / ADRs',   currency: '$',  currencyCode: 'USD' },
  TR: { flag: '🇹🇷', name: 'Turkey',         exchange: 'BIST',          currency: '₺',  currencyCode: 'TRY' },
  NG: { flag: '🇳🇬', name: 'Nigeria',        exchange: 'NGX',           currency: '₦',  currencyCode: 'NGN' },
}

const MARKET_CODES = ['US', 'BR', 'AR', 'TR', 'NG']

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtCurrency(v, symbol = '$') {
  if (v == null) return '—'
  const abs = Math.abs(v)
  let str
  if (abs >= 1_000_000_000) str = `${(v / 1_000_000_000).toFixed(2)}B`
  else if (abs >= 1_000_000) str = `${(v / 1_000_000).toFixed(2)}M`
  else str = Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `${symbol}${str}`
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

// ── Market Dropdown ───────────────────────────────────────────────────────────

function MarketDropdown({ selected, onChange, marketsOpen }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const cfg = MARKET_CONFIG[selected]

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 px-3 py-2 rounded-xl bg-gray-800 border border-gray-700 hover:border-gray-600 transition-colors text-sm font-medium text-white min-w-[190px]"
      >
        <span className="text-xl leading-none">{cfg.flag}</span>
        <div className="flex-1 text-left">
          <div className="font-semibold leading-tight">{cfg.name}</div>
          <div className="text-xs text-gray-500 leading-tight">{cfg.exchange}</div>
        </div>
        <svg className={`w-4 h-4 text-gray-500 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1.5 w-60 bg-gray-900 border border-gray-700 rounded-xl shadow-2xl z-50 overflow-hidden">
          {MARKET_CODES.map(code => {
            const m      = MARKET_CONFIG[code]
            const isOpen = marketsOpen?.[code]
            return (
              <button
                key={code}
                onClick={() => { onChange(code); setOpen(false) }}
                className={`w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-gray-800 transition-colors ${code === selected ? 'bg-gray-800/80' : ''}`}
              >
                <span className="text-xl leading-none">{m.flag}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-white">{m.name}</div>
                  <div className="text-xs text-gray-500">{m.exchange}</div>
                </div>
                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${isOpen ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`} />
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
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

function PositionModal({ position, market, onClose }) {
  const [sessionData, setSessionData] = useState(null)
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState(null)

  useEffect(() => {
    api.latestSession(position.name, market)
      .then(d => { setSessionData(d); setLoading(false) })
      .catch(() => { setError('No committee session found for this position.'); setLoading(false) })
  }, [position.name, market])

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const plPositive = position.unrealizedPl >= 0
  const sym = MARKET_CONFIG[market]?.currency || '$'

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

// ── Analyze Panel ─────────────────────────────────────────────────────────────

const AGENT_META = {
  technician:     { label: 'The Technician',     icon: '📈', role: 'Technical Analysis' },
  fundamentalist: { label: 'The Fundamentalist', icon: '📊', role: 'Fundamental Analysis' },
  newshound:      { label: 'The Newshound',       icon: '📰', role: 'News & Sentiment' },
  macro_watcher:  { label: 'The Macro Watcher',  icon: '🌍', role: 'Macro & Sectors' },
  risk_manager:   { label: 'The Risk Manager',   icon: '🛡️', role: 'Risk & Portfolio' },
}

const DECISION_BG = {
  BUY:  'bg-green-500/10 border-green-500/30 text-green-400',
  SELL: 'bg-red-500/10 border-red-500/30 text-red-400',
  HOLD: 'bg-gray-500/10 border-gray-600/30 text-gray-400',
}

const ACTION_STYLE_A = {
  BUY:  { badge: 'badge-buy',  bar: 'bg-green-500' },
  SELL: { badge: 'badge-sell', bar: 'bg-red-500' },
  HOLD: { badge: 'badge-hold', bar: 'bg-gray-500' },
}

const STEPS = [
  { label: 'Fetching technical indicators', icon: '📈' },
  { label: 'Pulling fundamental data',       icon: '📊' },
  { label: 'Scanning news & sentiment',      icon: '📰' },
  { label: 'Assessing macro conditions',     icon: '🌍' },
  { label: 'Running risk checks',            icon: '🛡️' },
  { label: 'Chairman deliberating…',         icon: '🏛️' },
]

function AnalysisSpinner({ ticker }) {
  const [step, setStep] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setStep(s => Math.min(s + 1, STEPS.length - 1)), 3000)
    return () => clearInterval(id)
  }, [])
  return (
    <div className="flex flex-col items-center py-10 gap-6">
      <div className="text-center">
        <div className="text-3xl mb-2 animate-pulse">{STEPS[step].icon}</div>
        <div className="text-base font-semibold text-white">Analyzing {ticker}</div>
        <div className="text-sm text-gray-500 mt-1">{STEPS[step].label}</div>
      </div>
      <div className="w-full max-w-xs space-y-2">
        {STEPS.map((s, i) => (
          <div key={i} className="flex items-center gap-2.5">
            <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs flex-shrink-0 transition-all ${
              i < step  ? 'bg-green-500/20 text-green-400' :
              i === step ? 'bg-indigo-500/20 text-indigo-300 animate-pulse' :
              'bg-gray-800 text-gray-600'
            }`}>{i < step ? '✓' : i + 1}</span>
            <span className={`text-xs ${i < step ? 'text-gray-500 line-through' : i === step ? 'text-gray-200' : 'text-gray-600'}`}>{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

const US_SUGGESTIONS  = ['AAPL', 'NVDA', 'MSFT', 'TSLA', 'AMZN', 'META', 'PLTR', 'CRWD']
const BR_SUGGESTIONS  = ['PETR4.SA', 'VALE3.SA', 'ITUB4.SA', 'BBDC4.SA', 'WEGE3.SA']
const AR_SUGGESTIONS  = ['YPF', 'GGAL', 'BMA', 'PAM', 'TGS']
const TR_SUGGESTIONS  = ['THYAO.IS', 'ASELS.IS', 'KCHOL.IS', 'GARAN.IS', 'FROTO.IS']
const NG_SUGGESTIONS  = ['MTNN.LG', 'DANGCEM.LG', 'GTCO.LG', 'ZENITHBANK.LG']
const MARKET_SUGGESTIONS = { US: US_SUGGESTIONS, BR: BR_SUGGESTIONS, AR: AR_SUGGESTIONS, TR: TR_SUGGESTIONS, NG: NG_SUGGESTIONS }

// ── Analysis Result (Chairman hero + collapsible agent strip) ─────────────────

function AnalysisResult({ result, onRerun }) {
  const [showAgents, setShowAgents] = useState(false)

  const decision  = result.decision ?? 'HOLD'
  const decStyle  = DECISION_BG[decision] ?? DECISION_BG.HOLD
  const decColor  = decision === 'BUY' ? 'text-green-400' : decision === 'SELL' ? 'text-red-400' : 'text-gray-400'

  // Parse rationale into bullet lines (lines starting with •)
  const rawRationale = result.chairman_rationale ?? ''
  const bulletLines  = rawRationale
    .split('\n')
    .map(l => l.trim())
    .filter(l => l.startsWith('•'))

  // If no bullets parsed, fall back to a single block
  const hasStructured = bulletLines.length > 0

  return (
    <div className="space-y-3">

      {/* ── Chairman hero card ── */}
      <div className={`rounded-2xl border p-5 ${decStyle}`}>
        {/* Verdict row */}
        <div className="flex items-center gap-4 mb-4">
          <div className={`text-5xl font-black ${decColor}`}>{decision}</div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">Chairman's Verdict · {result.ticker}</div>
            <div className="flex items-center gap-2 flex-wrap">
              {result.position_size_pct > 0 && (
                <span className="text-sm font-semibold text-gray-300">{result.position_size_pct}% position</span>
              )}
              {result.risk_off && (
                <span className="text-xs font-medium text-amber-400 bg-amber-500/10 border border-amber-500/25 rounded-full px-2 py-0.5">⚠️ Risk-off market</span>
              )}
            </div>
          </div>
        </div>

        {/* Bullet rationale */}
        {hasStructured ? (
          <ul className="space-y-2.5 mb-4">
            {bulletLines.map((line, i) => (
              <li key={i} className="flex items-start gap-2.5 text-sm text-gray-200 leading-snug">
                <span className="flex-shrink-0 mt-0.5">{line.slice(0, 2)}</span>
                <span>{line.slice(2).trim()}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-300 leading-relaxed mb-4">{rawRationale}</p>
        )}

        {/* Price targets */}
        {result.price_targets && (
          <div className="border-t border-white/10 pt-4">
            <div className="text-xs text-gray-500 uppercase tracking-wider mb-3">Price Targets</div>
            <div className="grid grid-cols-3 gap-2 mb-3">
              {[
                { label: '1 Month',  key: '1m'  },
                { label: '6 Months', key: '6m'  },
                { label: '1 Year',   key: '1y'  },
              ].map(({ label, key }) => {
                const target = result.price_targets[key]
                const current = result.current_price
                const pct = (current && target)
                  ? ((target - current) / current * 100)
                  : null
                const up = pct == null ? null : pct >= 0
                return (
                  <div key={key} className="bg-black/20 rounded-xl p-3 text-center">
                    <div className="text-xs text-gray-500 mb-1">{label}</div>
                    <div className="text-base font-bold text-white">
                      {target ? `$${Number(target).toFixed(2)}` : '—'}
                    </div>
                    {pct != null && (
                      <div className={`text-xs font-semibold mt-0.5 ${up ? 'text-green-400' : 'text-red-400'}`}>
                        {up ? '+' : ''}{pct.toFixed(1)}%
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            {result.stop_loss && result.current_price && (
              <div className="flex items-center justify-between bg-red-500/10 border border-red-500/20 rounded-xl px-3.5 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-red-400 text-sm">🛑</span>
                  <span className="text-xs font-medium text-red-300">Stop Loss</span>
                </div>
                <div className="text-right">
                  <span className="text-sm font-bold text-red-300">${Number(result.stop_loss).toFixed(2)}</span>
                  <span className="text-xs text-red-400 ml-2">
                    ({((result.stop_loss - result.current_price) / result.current_price * 100).toFixed(1)}%)
                  </span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Agent vote strip ── */}
      <div>
        <button
          onClick={() => setShowAgents(s => !s)}
          className="flex items-center gap-2 text-xs text-gray-500 hover:text-gray-300 transition-colors w-full mb-2"
        >
          <div className="flex items-center gap-1.5 flex-1">
            {result.agent_votes?.map(v => {
              const meta  = AGENT_META[v.agent_name] ?? { icon: '🤖' }
              const color = v.action === 'BUY' ? 'text-green-400' : v.action === 'SELL' ? 'text-red-400' : 'text-gray-400'
              return (
                <span key={v.agent_name} className={`text-sm ${color}`} title={`${meta.icon} ${v.action}`}>
                  {meta.icon}
                </span>
              )
            })}
            <span className="ml-1">Agent breakdown</span>
          </div>
          <span>{showAgents ? '▲ Hide' : '▼ Show'}</span>
        </button>

        {showAgents && (
          <div className="space-y-1.5">
            {result.agent_votes?.map(v => {
              const meta    = AGENT_META[v.agent_name] ?? { label: v.agent_name, icon: '🤖', role: '' }
              const style   = ACTION_STYLE_A[v.action] ?? ACTION_STYLE_A.HOLD
              const confPct = Math.round((v.confidence ?? 0) * 100)
              const isRM    = v.agent_name === 'risk_manager'
              return (
                <div
                  key={v.agent_name}
                  className={`bg-gray-800/40 rounded-xl px-3.5 py-2.5 border ${v.veto ? 'border-red-500/30' : 'border-gray-700/30'}`}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-base leading-none flex-shrink-0">{meta.icon}</span>
                    <span className="text-xs font-medium text-gray-300 flex-1 min-w-0 truncate">{meta.label}</span>
                    {v.veto && <span className="text-xs font-bold text-red-400">VETO</span>}
                    {!isRM && <span className="text-xs text-gray-500">{confPct}%</span>}
                    <span className={style.badge + ' text-xs py-0 px-1.5'}>{v.action ?? 'HOLD'}</span>
                  </div>
                  {v.rationale && (
                    <p className="text-xs text-gray-500 leading-snug mt-1.5 pl-6">{v.rationale}</p>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Re-run */}
      <div className="text-center">
        <button onClick={onRerun} className="text-xs text-gray-600 hover:text-gray-400 transition-colors underline underline-offset-2">
          ↺ Run analysis again
        </button>
      </div>
    </div>
  )
}


function AnalyzePanel({ market, onClose }) {
  const [ticker, setTicker]   = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult]   = useState(null)
  const [error, setError]     = useState(null)
  const inputRef = useRef(null)
  const suggestions = MARKET_SUGGESTIONS[market] || US_SUGGESTIONS

  useEffect(() => {
    inputRef.current?.focus()
    setResult(null)
    setError(null)
    setTicker('')
  }, [market])

  const run = async (t) => {
    const sym = (t || ticker).trim().toUpperCase()
    if (!sym) return
    setTicker(sym)
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const data = await api.analyze(sym, market)
      setResult(data)
    } catch (e) {
      setError(`Analysis failed: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center p-0 sm:p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700/80 rounded-t-2xl sm:rounded-2xl w-full sm:max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-800 sticky top-0 bg-gray-900 rounded-t-2xl z-10">
          <div className="flex items-center gap-2.5">
            <span className="text-xl">🔬</span>
            <div>
              <div className="font-bold text-white text-base">Analyze a Stock</div>
              <div className="text-xs text-gray-500">{MARKET_CONFIG[market]?.flag} {MARKET_CONFIG[market]?.name} · {MARKET_CONFIG[market]?.exchange}</div>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-600 hover:text-gray-200 transition-colors text-xl leading-none ml-4">✕</button>
        </div>

        <div className="p-5 space-y-4">
          {/* Search */}
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-500 text-base select-none">🔍</span>
              <input
                ref={inputRef}
                type="text"
                value={ticker}
                onChange={e => setTicker(e.target.value.toUpperCase())}
                onKeyDown={e => e.key === 'Enter' && run()}
                placeholder="Enter ticker symbol…"
                className="w-full bg-gray-800 border border-gray-700 rounded-xl pl-10 pr-4 py-2.5 text-white placeholder-gray-600 text-sm focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30 transition-all uppercase"
                disabled={loading}
                maxLength={15}
              />
            </div>
            <button
              onClick={() => run()}
              disabled={loading || !ticker.trim()}
              className="px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 whitespace-nowrap"
            >
              {loading ? <><span className="animate-spin">⚙️</span> Analyzing…</> : 'Run Analysis'}
            </button>
          </div>

          {/* Quick picks */}
          <div className="flex flex-wrap gap-2 items-center">
            <span className="text-xs text-gray-600">Quick picks:</span>
            {suggestions.map(s => (
              <button
                key={s}
                onClick={() => run(s)}
                disabled={loading}
                className="text-xs px-2.5 py-1 rounded-lg bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200 transition-colors disabled:opacity-40"
              >
                {s}
              </button>
            ))}
          </div>

          {/* Error */}
          {error && (
            <div className="border border-red-500/30 bg-red-500/5 text-red-400 text-sm p-3 rounded-xl">
              ⚠️ {error}
            </div>
          )}

          {/* Loading */}
          {loading && <AnalysisSpinner ticker={ticker} />}

          {/* Results */}
          {result && !loading && (
            <AnalysisResult result={result} onRerun={() => run()} />
          )}

          {/* Empty state */}
          {!result && !loading && !error && (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <span className="text-4xl">🔬</span>
              <p className="text-gray-500 text-sm">Enter a ticker above and click Run Analysis</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Portfolio() {
  const [market, setMarket]               = useState('US')
  const [tab, setTab]                     = useState('holdings')
  const [portfolio, setPortfolio]         = useState(null)
  const [stats, setStats]                 = useState(null)
  const [lastUpdated, setLastUpdated]     = useState(null)
  const [refreshing, setRefreshing]       = useState(false)
  const [selectedPosition, setSelectedPosition] = useState(null)
  const [marketsOpen, setMarketsOpen]     = useState({})
  const [ago, setAgo]                     = useState('')

  // Fetch health (all markets open/closed status)
  useEffect(() => {
    const fetch = () => api.health()
      .then(d => setMarketsOpen(d.markets_open || {}))
      .catch(() => {})
    fetch()
    const id = setInterval(fetch, 60_000)
    return () => clearInterval(id)
  }, [])

  const refresh = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true)
    try {
      const [portData, statsData] = await Promise.all([
        api.portfolio(market),
        api.stats(market),
      ])
      setPortfolio(portData)
      setStats(statsData)
      setLastUpdated(new Date())
    } catch (e) {
      console.error('Portfolio refresh failed:', e)
    } finally {
      setRefreshing(false)
    }
  }, [market])

  // Re-fetch when market changes; reset position
  useEffect(() => {
    setPortfolio(null)
    setStats(null)
    setSelectedPosition(null)
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

  const cfg          = MARKET_CONFIG[market]
  const sym          = cfg.currency
  const positions    = portfolio?.positions ?? []
  const totalValue   = stats?.total_value ?? portfolio?.total_value
  const cash         = stats?.cash ?? portfolio?.cash
  const pl           = stats?.total_pl_usd
  const plPct        = stats?.total_return_pct
  const trades       = stats?.total_trades
  const isOpen       = marketsOpen[market]

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
          market={market}
          onClose={() => setSelectedPosition(null)}
        />
      )}

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5 space-y-4">

        {/* ── Top bar ── */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Market dropdown */}
          <MarketDropdown
            selected={market}
            onChange={(code) => { setMarket(code); setTab('holdings') }}
            marketsOpen={marketsOpen}
          />

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
            <StatCard label="Portfolio Value" value={fmtCurrency(totalValue, sym)} />
            <StatCard label="Cash" value={fmtCurrency(cash, sym)} />
            <StatCard
              label="Total P&L"
              value={fmtCurrency(pl, sym)}
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
          <Trades market={market} />
        )}

      </div>
    </>
  )
}
