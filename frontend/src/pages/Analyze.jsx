import { useRef, useState } from 'react'
import { api } from '../api'

// ── Agent metadata ────────────────────────────────────────────────────────────

const AGENT_META = {
  technician:     { label: 'The Technician',     icon: '📈', role: 'Technical Analysis' },
  fundamentalist: { label: 'The Fundamentalist', icon: '📊', role: 'Fundamental Analysis' },
  newshound:      { label: 'The Newshound',       icon: '📰', role: 'News & Sentiment' },
  macro_watcher:  { label: 'The Macro Watcher',  icon: '🌍', role: 'Macro & Sectors' },
  risk_manager:   { label: 'The Risk Manager',   icon: '🛡️', role: 'Risk & Portfolio' },
}

const ACTION_STYLE = {
  BUY:  { badge: 'badge-buy',  bar: 'bg-green-500',  ring: 'border-green-500/30' },
  SELL: { badge: 'badge-sell', bar: 'bg-red-500',    ring: 'border-red-500/30' },
  HOLD: { badge: 'badge-hold', bar: 'bg-gray-500',   ring: '' },
}

const DECISION_BG = {
  BUY:  'bg-green-500/10 border-green-500/30 text-green-400',
  SELL: 'bg-red-500/10 border-red-500/30 text-red-400',
  HOLD: 'bg-gray-500/10 border-gray-600/30 text-gray-400',
}

// ── Sub-components ────────────────────────────────────────────────────────────

function AgentCard({ vote, loading }) {
  if (loading) {
    return (
      <div className="card animate-pulse">
        <div className="flex items-center gap-2 mb-3">
          <div className="w-8 h-8 bg-gray-700 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3 bg-gray-700 rounded w-3/4" />
            <div className="h-2.5 bg-gray-800 rounded w-1/2" />
          </div>
        </div>
        <div className="h-1.5 bg-gray-800 rounded-full mb-3" />
        <div className="space-y-1.5">
          <div className="h-2.5 bg-gray-800 rounded" />
          <div className="h-2.5 bg-gray-800 rounded w-5/6" />
          <div className="h-2.5 bg-gray-800 rounded w-4/6" />
        </div>
      </div>
    )
  }

  if (!vote) return null

  const { agent_name, action, confidence, rationale, veto } = vote
  const meta  = AGENT_META[agent_name] ?? { label: agent_name, icon: '🤖', role: '' }
  const style = ACTION_STYLE[action] ?? ACTION_STYLE.HOLD
  const confPct = Math.round((confidence ?? 0) * 100)

  return (
    <div className={`card relative flex flex-col gap-2.5 ${veto ? 'border-red-500/40' : style.ring ? `border-${style.ring}` : ''}`}>
      {veto && (
        <div className="absolute inset-x-0 top-0 bg-red-600/90 text-white text-xs font-bold text-center py-1 rounded-t-xl tracking-widest">
          ⛔ VETOED
        </div>
      )}
      <div className={veto ? 'mt-5' : ''}>
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-xl leading-none">{meta.icon}</span>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-white leading-tight truncate">{meta.label}</div>
              <div className="text-xs text-gray-500">{meta.role}</div>
            </div>
          </div>
          <span className={style.badge}>{action ?? 'HOLD'}</span>
        </div>

        {agent_name !== 'risk_manager' && (
          <div className="mt-3">
            <div className="flex justify-between text-xs text-gray-500 mb-1.5">
              <span>Confidence</span>
              <span className="font-medium text-gray-300">{confPct}%</span>
            </div>
            <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${style.bar}`}
                style={{ width: `${confPct}%` }}
              />
            </div>
          </div>
        )}

        <p className="mt-2.5 text-xs text-gray-400 leading-relaxed line-clamp-5">{rationale || '—'}</p>
      </div>
    </div>
  )
}

function VerdictBanner({ result }) {
  const bg = DECISION_BG[result.decision] ?? DECISION_BG.HOLD
  const score = result.weighted_score

  return (
    <div className={`card border ${bg} mb-1`}>
      <div className="flex flex-col sm:flex-row sm:items-start gap-4">
        {/* Left: decision */}
        <div className="flex items-center gap-4">
          <div className="text-4xl">🏛️</div>
          <div>
            <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Chairman's Verdict</div>
            <div className="flex items-center gap-3">
              <span className={`text-3xl font-black ${
                result.decision === 'BUY' ? 'text-green-400' :
                result.decision === 'SELL' ? 'text-red-400' : 'text-gray-400'
              }`}>
                {result.decision}
              </span>
              <div className="text-xs text-gray-500">
                <div>Score: <span className="text-gray-300 font-medium">{score?.toFixed(3)}</span></div>
                {result.risk_off && <div className="text-amber-400 mt-0.5">⚠️ Risk-off mode active</div>}
                {result.risk_manager_veto && <div className="text-red-400 mt-0.5">⛔ Risk Manager vetoed</div>}
              </div>
            </div>
          </div>
        </div>

        {/* Right: rationale */}
        {result.chairman_rationale && (
          <div className="flex-1 border-l border-gray-700/50 pl-4 hidden sm:block">
            <p className="text-sm text-gray-300 leading-relaxed italic">
              "{result.chairman_rationale}"
            </p>
          </div>
        )}
      </div>

      {/* Rationale on mobile */}
      {result.chairman_rationale && (
        <p className="text-sm text-gray-300 leading-relaxed italic mt-3 sm:hidden border-t border-gray-700/40 pt-3">
          "{result.chairman_rationale}"
        </p>
      )}
    </div>
  )
}

// ── Loading steps indicator ───────────────────────────────────────────────────

const STEPS = [
  { label: 'Fetching technical indicators',  icon: '📈' },
  { label: 'Pulling fundamental data',        icon: '📊' },
  { label: 'Scanning news & sentiment',       icon: '📰' },
  { label: 'Assessing macro conditions',      icon: '🌍' },
  { label: 'Running risk checks',             icon: '🛡️' },
  { label: 'Chairman deliberating…',          icon: '🏛️' },
]

function AnalysisSpinner({ ticker }) {
  const [step, setStep] = useState(0)

  // Advance steps roughly every 3s (visual only)
  useState(() => {
    const id = setInterval(() =>
      setStep(s => Math.min(s + 1, STEPS.length - 1)),
    3000)
    return () => clearInterval(id)
  })

  return (
    <div className="card flex flex-col items-center py-10 gap-6">
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
            }`}>
              {i < step ? '✓' : i + 1}
            </span>
            <span className={`text-xs ${
              i < step  ? 'text-gray-500 line-through' :
              i === step ? 'text-gray-200' :
              'text-gray-600'
            }`}>
              {s.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

const SUGGESTIONS = ['AAPL', 'NVDA', 'MSFT', 'TSLA', 'AMZN', 'META', 'GOOGL', 'JPM', 'XOM', 'SPY']

export default function Analyze() {
  const [ticker, setTicker]   = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult]   = useState(null)
  const [error, setError]     = useState(null)
  const inputRef = useRef(null)

  const run = async (t) => {
    const sym = (t || ticker).trim().toUpperCase()
    if (!sym) return
    setTicker(sym)
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const data = await api.analyze(sym)
      setResult(data)
    } catch (e) {
      setError(`Analysis failed: ${e.message}. Make sure the backend is running and API keys are configured.`)
    } finally {
      setLoading(false)
    }
  }

  const handleKey = (e) => {
    if (e.key === 'Enter') run()
  }

  return (
    <div className="space-y-5 max-w-4xl mx-auto">
      {/* Header */}
      <div>
        <h1 className="text-lg font-bold text-white">Analyze a Stock</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Enter any ticker and the full 5-agent committee will analyze it in real time.
          Works even when the market is closed — no order will be placed.
        </p>
      </div>

      {/* Search bar */}
      <div className="card p-4">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-500 text-lg select-none">🔍</span>
            <input
              ref={inputRef}
              type="text"
              value={ticker}
              onChange={e => setTicker(e.target.value.toUpperCase())}
              onKeyDown={handleKey}
              placeholder="Enter ticker symbol (e.g. AAPL)"
              className="w-full bg-gray-800 border border-gray-700 rounded-xl pl-10 pr-4 py-3 text-white placeholder-gray-600
                         text-sm focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30 transition-all uppercase"
              disabled={loading}
              maxLength={10}
              autoFocus
            />
          </div>
          <button
            onClick={() => run()}
            disabled={loading || !ticker.trim()}
            className="px-6 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold
                       transition-colors disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap flex items-center gap-2"
          >
            {loading ? (
              <>
                <span className="animate-spin text-base">⚙️</span>
                Analyzing…
              </>
            ) : (
              'Run Analysis'
            )}
          </button>
        </div>

        {/* Quick-pick suggestions */}
        <div className="flex flex-wrap gap-2 mt-3">
          <span className="text-xs text-gray-600 pt-0.5">Quick picks:</span>
          {SUGGESTIONS.map(s => (
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
      </div>

      {/* Error */}
      {error && (
        <div className="card border-red-500/30 bg-red-500/5 text-red-400 text-sm p-4">
          ⚠️ {error}
        </div>
      )}

      {/* Loading spinner */}
      {loading && <AnalysisSpinner ticker={ticker} />}

      {/* Results */}
      {result && !loading && (
        <div className="space-y-4 animate-fade-in">
          {/* Verdict banner */}
          <VerdictBanner result={result} />

          {/* Agent cards grid */}
          <div>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
              Agent Votes — {result.ticker}
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
              {result.agent_votes?.map(v => (
                <AgentCard key={v.agent_name} vote={v} />
              ))}
            </div>
          </div>

          {/* Run again */}
          <div className="text-center pt-2">
            <button
              onClick={() => run()}
              className="text-xs text-gray-600 hover:text-gray-400 transition-colors underline underline-offset-2"
            >
              ↺ Run analysis again
            </button>
          </div>
        </div>
      )}

      {/* Initial empty state */}
      {!result && !loading && !error && (
        <div className="card flex flex-col items-center justify-center py-16 gap-4 border-dashed border-gray-700">
          <span className="text-5xl">🔬</span>
          <div className="text-center">
            <p className="text-gray-400 font-medium">No analysis yet</p>
            <p className="text-gray-600 text-sm mt-1">
              Type a ticker above and click "Run Analysis"
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
