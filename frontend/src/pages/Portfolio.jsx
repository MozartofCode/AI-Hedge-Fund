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

// ── Analysis Result — valuation numbers + technical + fundamental ─────────────

function ScoreBar({ value, color }) {
  if (value == null) return null
  return (
    <div className="h-1 bg-gray-700 rounded-full overflow-hidden">
      <div className={`h-1 rounded-full ${color}`} style={{ width: `${Math.round(value * 100)}%` }} />
    </div>
  )
}

function AgentCard({ icon, label, vote }) {
  if (!vote) return null
  const action = vote.action ?? 'HOLD'
  const conf   = vote.confidence ?? 0
  const badgeCls = action === 'BUY'
    ? 'bg-green-500/20 text-green-400'
    : action === 'SELL'
    ? 'bg-red-500/20 text-red-400'
    : 'bg-gray-600/30 text-gray-400'

  const subScores = [
    { label: 'Valuation',     val: vote.valuation_score },
    { label: 'Growth',        val: vote.growth_score },
    { label: 'Profitability', val: vote.profitability_score },
    { label: 'Estimates',     val: vote.revisions_score },
  ].filter(s => s.val != null)

  return (
    <div className="bg-gray-800/40 rounded-xl p-3.5 border border-gray-700/30 space-y-2.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-300">{icon} {label}</span>
        <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${badgeCls}`}>{action}</span>
      </div>

      {vote.rationale && (
        <p className="text-xs text-gray-400 leading-snug">{vote.rationale}</p>
      )}

      {subScores.length > 0 && (
        <div className="space-y-1.5 pt-0.5">
          {subScores.map(({ label: lbl, val }) => {
            const barColor = val >= 0.6 ? 'bg-green-500' : val >= 0.4 ? 'bg-yellow-500' : 'bg-red-500'
            return (
              <div key={lbl}>
                <div className="flex justify-between text-[10px] text-gray-600 mb-0.5">
                  <span>{lbl}</span><span>{Math.round(val * 100)}%</span>
                </div>
                <ScoreBar value={val} color={barColor} />
              </div>
            )
          })}
        </div>
      )}

      <div>
        <div className="flex justify-between text-[10px] text-gray-600 mb-0.5">
          <span>Conviction</span><span>{Math.round(conf * 100)}%</span>
        </div>
        <ScoreBar value={conf} color="bg-indigo-500" />
      </div>
    </div>
  )
}

function AnalysisResult({ result, onRerun }) {
  const decision = result.decision ?? 'HOLD'
  const cur      = result.current_price
  const dcf      = result.dcf_price
  const ws       = result.ws_price
  const wsLo     = result.ws_price_low
  const wsHi     = result.ws_price_high

  const dcfDiff = (cur && dcf) ? ((dcf - cur) / cur * 100) : null
  const wsDiff  = (cur && ws)  ? ((ws  - cur) / cur * 100) : null

  const decCls = decision === 'BUY'
    ? 'text-green-400 border-green-500/40 bg-green-500/10'
    : decision === 'SELL'
    ? 'text-red-400 border-red-500/40 bg-red-500/10'
    : 'text-gray-400 border-gray-600/40 bg-gray-500/10'

  const techVote = result.agent_votes?.find(v => v.agent_name === 'technician')
  const fundVote = result.agent_votes?.find(v => v.agent_name === 'fundamentalist')

  return (
    <div className="space-y-4">

      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          {result.company_name && (
            <div className="text-xs text-gray-500 mb-0.5">{result.company_name}</div>
          )}
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-black text-white">
              {cur ? `$${cur.toFixed(2)}` : '—'}
            </span>
            <span className="text-sm text-gray-500">{result.ticker}</span>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`text-sm font-bold px-3 py-1 rounded-xl border ${decCls}`}>
            {decision}
          </span>
          <button
            onClick={onRerun}
            className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
            title="Re-run analysis"
          >↺</button>
        </div>
      </div>

      {/* Valuation block */}
      <div className="bg-gray-800/40 rounded-xl p-4 border border-gray-700/30">
        <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-3">
          Valuation
        </div>

        <div className="grid grid-cols-3 gap-3 mb-3">
          <div>
            <div className="text-[10px] text-gray-600 mb-1">Current Price</div>
            <div className="text-lg font-bold text-white">{cur ? `$${cur.toFixed(2)}` : '—'}</div>
          </div>
          <div>
            <div className="text-[10px] text-gray-600 mb-1">DCF Fair Value</div>
            <div className="text-lg font-bold text-white">{dcf ? `$${dcf.toFixed(2)}` : '—'}</div>
            {dcfDiff != null && (
              <div className={`text-[10px] font-semibold mt-0.5 ${dcfDiff >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {dcfDiff >= 0 ? '+' : ''}{dcfDiff.toFixed(1)}% vs price
              </div>
            )}
          </div>
          <div>
            <div className="text-[10px] text-gray-600 mb-1">Wall St. Target</div>
            <div className="text-lg font-bold text-white">{ws ? `$${ws.toFixed(2)}` : '—'}</div>
            {wsDiff != null && (
              <div className={`text-[10px] font-semibold mt-0.5 ${wsDiff >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {wsDiff >= 0 ? '+' : ''}{wsDiff.toFixed(1)}% upside
              </div>
            )}
          </div>
        </div>

        {/* Analyst range bar */}
        {wsLo != null && wsHi != null && cur != null && wsHi > wsLo && (
          <div>
            <div className="flex justify-between text-[10px] text-gray-600 mb-1">
              <span>Low ${wsLo.toFixed(2)}</span>
              <span>High ${wsHi.toFixed(2)}</span>
            </div>
            <div className="relative h-2 bg-gray-700 rounded-full overflow-hidden">
              <div className="absolute inset-0 bg-gradient-to-r from-red-500/40 via-yellow-500/40 to-green-500/40" />
              <div
                className="absolute top-0.5 bottom-0.5 w-px bg-white shadow rounded-full"
                style={{ left: `${Math.max(1, Math.min(99, (cur - wsLo) / (wsHi - wsLo) * 100)).toFixed(1)}%` }}
              />
            </div>
            <div className="text-[10px] text-gray-600 mt-1 text-center">
              Price is at {Math.round((cur - wsLo) / (wsHi - wsLo) * 100)}% of the analyst range
            </div>
          </div>
        )}
      </div>

      {/* Technical + Fundamental */}
      <div className="grid grid-cols-2 gap-3">
        <AgentCard icon="📈" label="Technical" vote={techVote} />
        <AgentCard icon="📊" label="Fundamental" vote={fundVote} />
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
  const [showAnalyze, setShowAnalyze]     = useState(false)
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

      {showAnalyze && (
        <AnalyzePanel market={market} onClose={() => setShowAnalyze(false)} />
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

          {/* Analyze button */}
          <button
            onClick={() => setShowAnalyze(true)}
            className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-300 hover:bg-indigo-600/30 transition-colors text-sm font-medium"
          >
            <span>🔬</span> Analyze
          </button>

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
