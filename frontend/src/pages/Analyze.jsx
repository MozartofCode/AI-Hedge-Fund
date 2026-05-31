import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

// ── Valuation signal config ───────────────────────────────────────────────────
const SIGNAL_CFG = {
  'STRONG BUY':   { color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/30', dot: 'bg-emerald-400', label: '⬆⬆ STRONG BUY'   },
  'BUY':          { color: 'text-green-400',   bg: 'bg-green-500/10 border-green-500/30',     dot: 'bg-green-400',   label: '⬆ BUY'           },
  'OUTPERFORM':   { color: 'text-lime-400',    bg: 'bg-lime-500/10 border-lime-500/30',       dot: 'bg-lime-400',    label: '↗ OUTPERFORM'    },
  'HOLD':         { color: 'text-gray-400',    bg: 'bg-gray-500/10 border-gray-600/30',       dot: 'bg-gray-400',    label: '→ HOLD'          },
  'UNDERPERFORM': { color: 'text-yellow-400',  bg: 'bg-yellow-500/10 border-yellow-500/30',   dot: 'bg-yellow-400',  label: '↘ UNDERPERFORM'  },
  'SELL':         { color: 'text-orange-400',  bg: 'bg-orange-500/10 border-orange-500/30',   dot: 'bg-orange-400',  label: '⬇ SELL'          },
  'STRONG SELL':  { color: 'text-red-400',     bg: 'bg-red-500/10 border-red-500/30',         dot: 'bg-red-400',     label: '⬇⬇ STRONG SELL'  },
  'N/A':          { color: 'text-gray-500',    bg: 'bg-gray-800/50 border-gray-700/30',       dot: 'bg-gray-500',    label: '— N/A'           },
}

const DECISION_CFG = {
  BUY:  { color: 'text-green-400',  bg: 'bg-green-500/10 border-green-500/30'  },
  SELL: { color: 'text-red-400',    bg: 'bg-red-500/10 border-red-500/30'      },
  HOLD: { color: 'text-gray-400',   bg: 'bg-gray-500/10 border-gray-600/30'    },
}

const AGENT_META = {
  technician:     { label: 'Technician',     icon: '📈', role: 'Price Action & Momentum' },
  fundamentalist: { label: 'Fundamentalist', icon: '📊', role: 'Financials & Valuation'  },
  newshound:      { label: 'Newshound',       icon: '📰', role: 'News & Sentiment'        },
  macro_watcher:  { label: 'Macro Watcher',  icon: '🌍', role: 'Market Conditions'       },
  risk_manager:   { label: 'Risk Manager',   icon: '🛡️', role: 'Portfolio Risk'          },
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt = (v, decimals = 2) =>
  v == null ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })

const fmtPct = (v, plus = true) => {
  if (v == null) return '—'
  const s = `${plus && v > 0 ? '+' : ''}${Number(v).toFixed(1)}%`
  return s
}

const fmtPrice = (v) => v == null ? '—' : `$${fmt(v)}`

const uptrendColor = (v) => {
  if (v == null) return 'text-gray-400'
  return v > 0 ? 'text-green-400' : 'text-red-400'
}

// ── Loading step indicator ─────────────────────────────────────────────────────
const STEPS = [
  { label: 'Fetching price & technicals', icon: '📈' },
  { label: 'Pulling fundamental data',    icon: '📊' },
  { label: 'Computing fair value',        icon: '💹' },
  { label: 'Scanning news & sentiment',  icon: '📰' },
  { label: 'Assessing macro conditions', icon: '🌍' },
  { label: 'Chairman deliberating…',     icon: '🏛️' },
]

function AnalysisSpinner({ ticker }) {
  const [step, setStep] = useState(0)

  useEffect(() => {   // ← fixed: was useState (bug), now useEffect
    const id = setInterval(() => setStep(s => Math.min(s + 1, STEPS.length - 1)), 3000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="max-w-md mx-auto mt-12 card flex flex-col items-center py-10 gap-6">
      <div className="text-center">
        <div className="text-4xl mb-3 animate-pulse">{STEPS[step].icon}</div>
        <div className="text-base font-semibold text-white">Analyzing {ticker}…</div>
        <div className="text-sm text-gray-500 mt-1">{STEPS[step].label}</div>
      </div>
      <div className="w-full max-w-xs space-y-2.5">
        {STEPS.map((s, i) => (
          <div key={i} className="flex items-center gap-2.5">
            <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs flex-shrink-0 transition-all ${
              i < step   ? 'bg-green-500/20 text-green-400'
              : i === step ? 'bg-indigo-500/20 text-indigo-300 animate-pulse'
              : 'bg-gray-800 text-gray-600'
            }`}>
              {i < step ? '✓' : i + 1}
            </span>
            <span className={`text-xs ${
              i < step   ? 'text-gray-600 line-through'
              : i === step ? 'text-gray-200'
              : 'text-gray-600'
            }`}>{s.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Price card ─────────────────────────────────────────────────────────────────
function PriceCard({ label, icon, price, upside, subtext, highlight }) {
  const positive = upside != null && upside > 0
  const negative = upside != null && upside < 0
  return (
    <div className={`flex-1 rounded-xl border p-4 ${highlight ? 'border-indigo-500/40 bg-indigo-500/5' : 'border-white/8 bg-gray-900/60'}`}>
      <div className="text-xs text-gray-500 mb-1 flex items-center gap-1.5">
        <span>{icon}</span>{label}
      </div>
      <div className="text-2xl font-bold text-white">{fmtPrice(price)}</div>
      {upside != null && (
        <div className={`text-sm font-medium mt-0.5 ${positive ? 'text-green-400' : negative ? 'text-red-400' : 'text-gray-400'}`}>
          {positive ? '▲' : negative ? '▼' : ''} {fmtPct(upside)}
          <span className="text-gray-600 ml-1 text-xs">vs spot</span>
        </div>
      )}
      {subtext && <div className="text-xs text-gray-600 mt-1">{subtext}</div>}
    </div>
  )
}

// ── Collapsible section ────────────────────────────────────────────────────────
function Section({ title, icon, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border border-white/8 rounded-xl overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-900/60 hover:bg-gray-900/90 transition-colors"
        onClick={() => setOpen(o => !o)}
      >
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
          <span>{icon}</span>{title}
        </div>
        <span className={`text-gray-500 transition-transform text-xs ${open ? 'rotate-180' : ''}`}>▼</span>
      </button>
      {open && <div className="px-4 py-3 bg-gray-900/30">{children}</div>}
    </div>
  )
}

// ── Metric row ─────────────────────────────────────────────────────────────────
function MetricRow({ label, value, valueClass, note, desc }) {
  return (
    <div className="flex items-start justify-between py-2 border-b border-white/5 last:border-0 gap-4">
      <div className="min-w-0">
        <div className="text-xs text-gray-400">{label}</div>
        {desc && <div className="text-[10px] text-gray-600 mt-0.5 leading-snug">{desc}</div>}
      </div>
      <div className="text-right flex-shrink-0">
        <span className={`text-xs font-medium ${valueClass || 'text-gray-300'}`}>{value ?? '—'}</span>
        {note && <span className="text-xs text-gray-600 ml-1.5">{note}</span>}
      </div>
    </div>
  )
}

// ── Valuation section ──────────────────────────────────────────────────────────
function ValuationSection({ data }) {
  if (!data) return <p className="text-xs text-gray-600">No data available.</p>
  const v = data
  return (
    <div className="space-y-0">
      <MetricRow
        label="P/E Ratio"
        desc="How much you pay for $1 of annual profit — lower is cheaper"
        value={v.pe_ratio ? `${fmt(v.pe_ratio, 1)}x` : null} />
      <MetricRow
        label="Value vs Growth (PEG)"
        desc="Under 1.0 = potentially cheap relative to growth rate"
        value={v.peg_ratio ? `${fmt(v.peg_ratio, 2)}` : null}
        valueClass={v.peg_ratio != null ? (v.peg_ratio < 1 ? 'text-green-400' : v.peg_ratio > 2 ? 'text-red-400' : 'text-gray-300') : ''} />
      <MetricRow
        label="Price vs Free Cash Flow"
        desc="How expensive the stock is vs cash the business generates — under 20x is healthy"
        value={v.p_fcf ? `${fmt(v.p_fcf, 1)}x` : null}
        valueClass={v.p_fcf != null ? (v.p_fcf < 20 ? 'text-green-400' : v.p_fcf > 40 ? 'text-red-400' : 'text-gray-300') : ''} />
      <MetricRow
        label="Revenue Growth"
        desc="How much faster the company is selling compared to a year ago"
        value={fmtPct(v.rev_growth_yoy)}
        valueClass={uptrendColor(v.rev_growth_yoy)} />
      <MetricRow
        label="Growth Momentum"
        desc="Is the growth rate itself speeding up? Positive = accelerating"
        value={v.rev_accel != null ? fmtPct(v.rev_accel) : null}
        note="vs prior quarter" valueClass={uptrendColor(v.rev_accel)} />
      <MetricRow
        label="Earnings Momentum"
        desc="Are profits growing faster each quarter? Positive = gaining steam"
        value={v.eps_accel != null ? fmtPct(v.eps_accel) : null}
        valueClass={uptrendColor(v.eps_accel)} />
      <MetricRow
        label="Turned Cash Profitable?"
        desc="Recently went from burning cash to generating it — a major turning point"
        value={v.fcf_inflection ? '✅ Yes — just turned positive' : 'Not yet'}
        valueClass={v.fcf_inflection ? 'text-emerald-400' : 'text-gray-500'} />
      <MetricRow
        label="Growth + Profit Score"
        desc="Revenue growth % + profit margin % combined — over 40 is healthy, 60+ is exceptional"
        value={v.rule_of_40 != null ? `${fmt(v.rule_of_40, 0)}` : null}
        valueClass={v.rule_of_40 != null ? (v.rule_of_40 > 60 ? 'text-emerald-400' : v.rule_of_40 > 40 ? 'text-green-400' : v.rule_of_40 > 20 ? 'text-gray-300' : 'text-red-400') : ''} />
      <MetricRow
        label="Analyst Target Upside"
        desc="How much further Wall Street analysts think the stock can rise"
        value={fmtPct(v.analyst_upside)}
        valueClass={uptrendColor(v.analyst_upside)} />
    </div>
  )
}

// ── Financial section ──────────────────────────────────────────────────────────
function FinancialSection({ data }) {
  if (!data) return <p className="text-xs text-gray-600">No data available.</p>
  const v = data
  const gmChange = v.gross_margin_change
  return (
    <div className="space-y-0">
      <MetricRow
        label="Profit on Each Sale"
        desc="% kept after cost of making the product — over 50% means strong pricing power"
        value={v.gross_margin != null ? `${fmt(v.gross_margin, 1)}%` : null}
        note={gmChange != null ? `${gmChange > 0 ? '+' : ''}${fmt(gmChange, 0)} bps vs last year` : null}
        valueClass={v.gross_margin != null ? (v.gross_margin > 50 ? 'text-green-400' : v.gross_margin > 30 ? 'text-gray-300' : 'text-yellow-400') : ''} />
      <MetricRow
        label="Operating Profit %"
        desc="% of revenue left after all business expenses — trending up is a great sign"
        value={v.op_margin != null ? `${fmt(v.op_margin, 1)}%` : null}
        note={v.op_margin_trend != null ? `${v.op_margin_trend > 0 ? '▲' : '▼'}${Math.abs(v.op_margin_trend).toFixed(1)}pp` : null}
        valueClass={uptrendColor(v.op_margin)} />
      <MetricRow
        label="Debt Level"
        desc="How much debt vs equity — under 1x is conservative, over 3x is risky"
        value={v.debt_to_equity != null ? `${fmt(v.debt_to_equity, 2)}x` : null}
        valueClass={v.debt_to_equity != null ? (v.debt_to_equity < 1 ? 'text-green-400' : v.debt_to_equity > 3 ? 'text-red-400' : 'text-gray-300') : ''} />
      <MetricRow
        label="Short-Term Financial Cushion"
        desc="Can the company pay its near-term bills? Over 2x means a comfortable buffer"
        value={v.current_ratio != null ? `${fmt(v.current_ratio, 2)}x` : null}
        valueClass={v.current_ratio != null ? (v.current_ratio > 2 ? 'text-green-400' : v.current_ratio < 1 ? 'text-red-400' : 'text-gray-300') : ''} />
      <MetricRow
        label="Cash vs Debt"
        desc="How much cash the company holds relative to its debt — higher is safer"
        value={v.cash_to_debt === 999 ? 'Debt-free 💰' : v.cash_to_debt != null ? `${fmt(v.cash_to_debt, 2)}x` : null}
        valueClass={v.cash_to_debt != null ? (v.cash_to_debt > 2 ? 'text-green-400' : v.cash_to_debt < 0.5 ? 'text-red-400' : 'text-gray-300') : ''} />
      <MetricRow
        label="Buying Back Own Stock"
        desc="% of shares repurchased — signals management confidence and reduces share count"
        value={v.buyback_yield != null ? `${fmt(v.buyback_yield, 1)}% of market cap` : null}
        valueClass={v.buyback_yield != null ? (v.buyback_yield > 3 ? 'text-green-400' : 'text-gray-300') : ''} />
      <MetricRow
        label="New Shares Created"
        desc="Positive = more shares issued (dilutes your stake). Negative = buybacks (good)"
        value={fmtPct(v.dilution_yoy)}
        valueClass={v.dilution_yoy != null ? (v.dilution_yoy < -2 ? 'text-green-400' : v.dilution_yoy > 10 ? 'text-red-400' : 'text-gray-300') : ''} />
      <MetricRow
        label="Innovation Spending"
        desc="% of revenue reinvested in research and development"
        value={v.rd_intensity != null ? `${fmt(v.rd_intensity, 1)}% of revenue` : null} />
    </div>
  )
}

// ── Newsworthy section ────────────────────────────────────────────────────────
function NewsworthySection({ data }) {
  if (!data) return <p className="text-xs text-gray-600">No data available.</p>
  const v = data
  const sentiment = v.news_sentiment
  const sentimentLabel = sentiment == null ? '—' : sentiment > 0.6 ? 'Positive 🟢' : sentiment < 0.3 ? 'Negative 🔴' : 'Neutral 🟡'
  const sentimentColor = sentiment == null ? 'text-gray-400' : sentiment > 0.6 ? 'text-green-400' : sentiment < 0.3 ? 'text-red-400' : 'text-yellow-400'
  const mspr = v.insider_mspr
  const insiderLabel = mspr == null ? '—' : mspr > 0.5 ? 'Executives buying heavily 🟢' : mspr > 0.2 ? 'Mild buying' : mspr < -0.3 ? 'Executives selling 🔴' : 'Neutral'

  return (
    <div className="space-y-0">
      <MetricRow
        label="News Tone"
        desc="Overall tone of recent news coverage about this stock"
        value={sentimentLabel} valueClass={sentimentColor} />
      <MetricRow
        label="Recent News Articles"
        desc="Number of news articles in the last 2 weeks"
        value={v.article_count_14d} />
      <MetricRow
        label="Earnings Beats in a Row"
        desc="How many consecutive quarters the company beat analyst expectations"
        value={v.consecutive_beats != null ? `${v.consecutive_beats} quarter${v.consecutive_beats !== 1 ? 's' : ''}` : null}
        valueClass={v.consecutive_beats >= 3 ? 'text-emerald-400' : v.consecutive_beats >= 2 ? 'text-green-400' : 'text-gray-300'} />
      <MetricRow
        label="Executive Buying/Selling"
        desc="Are company insiders (CEOs, directors) buying or selling their own stock?"
        value={insiderLabel}
        valueClass={mspr != null ? (mspr > 0.2 ? 'text-green-400' : mspr < -0.3 ? 'text-red-400' : 'text-gray-300') : ''} />
      <MetricRow
        label="Short Squeeze Potential"
        desc="Could investors betting against this stock be forced to buy, driving price up? (0–8 scale)"
        value={v.squeeze_risk != null ? `${v.squeeze_risk} / 8` : null}
        valueClass={v.squeeze_risk != null ? (v.squeeze_risk > 5 ? 'text-orange-400' : v.squeeze_risk > 3 ? 'text-yellow-400' : 'text-gray-300') : ''} />
      <MetricRow
        label="Investors Betting Against It"
        desc="% of shares borrowed to short — high % means many investors expect the price to fall"
        value={v.short_interest_pct != null ? `${fmt(v.short_interest_pct, 1)}% of float` : null}
        note={v.days_to_cover != null ? `${fmt(v.days_to_cover, 1)} days to cover` : ''} />
      <MetricRow
        label="Unusual Options Activity"
        desc="Are traders placing unusually large bullish bets through options contracts?"
        value={v.unusual_call_activity ? `Yes ⚡` : 'Nothing unusual'}
        valueClass={v.unusual_call_activity ? 'text-amber-400' : 'text-gray-500'} />
      <MetricRow
        label="Analyst Rating Changes (30d)"
        desc="How many analysts upgraded vs downgraded their recommendation recently"
        value={v.analyst_upgrades != null ? `▲${v.analyst_upgrades} upgrades  ▼${v.analyst_downgrades ?? 0} downgrades` : null}
        valueClass={(v.analyst_upgrades ?? 0) > (v.analyst_downgrades ?? 0) ? 'text-green-400' : 'text-red-400'} />
      {v.sentiment_divergence && (
        <div className="mt-2 p-2 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300">
          ⚡ Contrarian signal: negative news + insider buying = potential smart-money accumulation
        </div>
      )}
      {v.recent_headlines?.length > 0 && (
        <div className="mt-3 space-y-1.5">
          <div className="text-xs text-gray-600 uppercase tracking-wider">Recent Headlines</div>
          {v.recent_headlines.map((h, i) => (
            <div key={i} className="text-xs text-gray-400 border-l-2 border-gray-700 pl-2.5 py-0.5 leading-snug line-clamp-1">
              {h.headline}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Agent tab panel ────────────────────────────────────────────────────────────
function AgentTabs({ votes }) {
  const filtered = (votes || []).filter(v => AGENT_META[v.agent_name])
  const [active, setActive] = useState(filtered[0]?.agent_name || '')
  const vote = filtered.find(v => v.agent_name === active)
  const meta = AGENT_META[active] || {}

  const actionColor = { BUY: 'text-green-400', SELL: 'text-red-400', HOLD: 'text-gray-400' }
  const confPct = Math.round((vote?.confidence ?? 0) * 100)

  const subScores = [
    { label: 'Valuation',    val: vote?.valuation_score },
    { label: 'Growth',       val: vote?.growth_score },
    { label: 'Profitability',val: vote?.profitability_score },
    { label: 'Revisions',    val: vote?.revisions_score },
  ].filter(s => s.val != null)

  return (
    <div className="border border-white/8 rounded-xl overflow-hidden">
      {/* Tab bar */}
      <div className="flex overflow-x-auto bg-gray-900/60 border-b border-white/5">
        {filtered.map(v => {
          const m = AGENT_META[v.agent_name]
          const isActive = v.agent_name === active
          const ac = { BUY: 'text-green-400', SELL: 'text-red-400', HOLD: 'text-gray-500' }[v.action] || 'text-gray-500'
          return (
            <button
              key={v.agent_name}
              onClick={() => setActive(v.agent_name)}
              className={`flex-shrink-0 flex flex-col items-center px-4 py-2.5 text-xs font-medium transition-colors border-b-2 ${
                isActive ? 'border-indigo-500 bg-gray-900/60 text-white' : 'border-transparent text-gray-500 hover:text-gray-300'
              }`}
            >
              <span className="text-base mb-0.5">{m.icon}</span>
              <span className="hidden sm:block">{m.label}</span>
              <span className={`text-[10px] font-bold mt-0.5 ${ac}`}>{v.action}</span>
            </button>
          )
        })}
      </div>

      {/* Active agent panel */}
      {vote && (
        <div className="p-4 bg-gray-900/30 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-white">{meta.label}</div>
              <div className="text-xs text-gray-500">{meta.role}</div>
            </div>
            <div className="text-right">
              <div className={`text-lg font-black ${actionColor[vote.action] || 'text-gray-400'}`}>
                {vote.veto ? '⛔ VETOED' : vote.action}
              </div>
              {vote.agent_name !== 'risk_manager' && (
                <div className="text-xs text-gray-500">{confPct}% confidence</div>
              )}
            </div>
          </div>

          {vote.agent_name !== 'risk_manager' && (
            <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  vote.action === 'BUY' ? 'bg-green-500' : vote.action === 'SELL' ? 'bg-red-500' : 'bg-gray-500'
                }`}
                style={{ width: `${confPct}%` }}
              />
            </div>
          )}

          <p className="text-xs text-gray-400 leading-relaxed">{vote.rationale || '—'}</p>

          {subScores.length > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
              {subScores.map(s => (
                <div key={s.label} className="rounded-lg bg-gray-800/50 px-2 py-1.5 text-center">
                  <div className="text-xs text-gray-500">{s.label}</div>
                  <div className={`text-sm font-bold ${s.val > 0.65 ? 'text-green-400' : s.val < 0.35 ? 'text-red-400' : 'text-gray-300'}`}>
                    {Math.round(s.val * 100)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Chairman rationale bullets ────────────────────────────────────────────────
function convictionLabel(score) {
  if (score == null) return ''
  if (score >= 0.70) return 'High conviction'
  if (score >= 0.55) return 'Moderate conviction'
  if (score >= 0.45) return 'Mixed signals'
  return 'Low conviction'
}

function ChairmanRationale({ rationale, decision, score, priceTargets, stopLoss }) {
  if (!rationale) return null
  const lines = rationale.split('\n').filter(l => l.trim().startsWith('•'))
  const cfg = DECISION_CFG[decision] || DECISION_CFG.HOLD

  return (
    <div className={`border rounded-xl p-4 ${cfg.bg}`}>
      <div className="flex items-center gap-3 mb-3">
        <span className="text-2xl">🏛️</span>
        <div>
          <div className="text-xs text-gray-500 uppercase tracking-wider">Committee's Final Verdict</div>
          <div className="flex items-center gap-2">
            <span className={`text-xl font-black ${cfg.color}`}>{decision}</span>
            {score != null && (
              <span className="text-xs text-gray-500">{convictionLabel(score)}</span>
            )}
          </div>
        </div>
      </div>

      <div className="space-y-2">
        {lines.length > 0 ? lines.map((line, i) => (
          <p key={i} className="text-sm text-gray-300 leading-relaxed">{line.trim()}</p>
        )) : (
          <p className="text-sm text-gray-300 leading-relaxed">{rationale}</p>
        )}
      </div>

      {(priceTargets || stopLoss) && (
        <div className="mt-4 pt-3 border-t border-white/10 grid grid-cols-4 gap-2 text-center">
          {[['1m', '1 Month'], ['6m', '6 Months'], ['1y', '1 Year']].map(([k, label]) => (
            <div key={k} className="rounded-lg bg-black/20 px-2 py-1.5">
              <div className="text-[10px] text-gray-500">{label}</div>
              <div className="text-xs font-semibold text-gray-200">{fmtPrice(priceTargets?.[k])}</div>
            </div>
          ))}
          <div className="rounded-lg bg-red-900/30 px-2 py-1.5">
            <div className="text-[10px] text-gray-500">Stop Loss</div>
            <div className="text-xs font-semibold text-red-400">{fmtPrice(stopLoss)}</div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main result card ───────────────────────────────────────────────────────────
function AnalysisResult({ result, onReset }) {
  const sig = SIGNAL_CFG[result.valuation_signal] || SIGNAL_CFG['N/A']
  const dcfUpside = result.dcf_price && result.spot_price
    ? (result.dcf_price - result.spot_price) / result.spot_price * 100
    : null

  return (
    <div className="space-y-3 animate-fade-in">
      {/* ── Header: ticker + company + valuation signal ── */}
      <div className="card">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <div className="text-3xl font-black text-white tracking-tight">{result.ticker}</div>
            <div className="text-sm text-gray-400 mt-0.5">{result.company_name || '—'}</div>
            {result.market !== 'US' && (
              <div className="text-xs text-gray-600 mt-0.5">Market: {result.market}</div>
            )}
          </div>
          {result.valuation_signal && result.valuation_signal !== 'N/A' && (
            <div className={`flex items-center gap-2 px-3 py-2 rounded-xl border ${sig.bg}`}>
              <span className={`w-2 h-2 rounded-full ${sig.dot}`} />
              <span className={`text-sm font-bold ${sig.color}`}>{sig.label}</span>
            </div>
          )}
        </div>

        {/* ── Price trio ── */}
        <div className="flex gap-3 mt-4 flex-col sm:flex-row">
          <PriceCard
            label="Current Price"
            icon="💹"
            price={result.spot_price || result.current_price}
          />
          <PriceCard
            label="Estimated True Value"
            icon="📐"
            price={result.dcf_price}
            upside={dcfUpside}
            subtext="Based on projected future cash flows"
            highlight={!!result.dcf_price}
          />
          <PriceCard
            label="Analyst Target Price"
            icon="🏦"
            price={result.ws_price}
            upside={result.ws_upside_pct}
            subtext={result.ws_ci_lo && result.ws_ci_hi
              ? `Confidence range: $${fmt(result.ws_ci_lo)} – $${fmt(result.ws_ci_hi)}`
              : result.ws_price_high && result.ws_price_low
                ? `Range: $${fmt(result.ws_price_low)} – $${fmt(result.ws_price_high)}`
                : 'Wall Street average target'}
            highlight={!!result.ws_price}
          />
        </div>
      </div>

      {/* ── Three collapsible sections ── */}
      <Section title="Is It Worth the Price?" icon="📈" defaultOpen>
        <ValuationSection data={result.sections?.valuation} />
      </Section>

      <Section title="Company Financial Health" icon="💰">
        <FinancialSection data={result.sections?.financial} />
      </Section>

      <Section title="News & Market Buzz" icon="📰">
        <NewsworthySection data={result.sections?.newsworthy} />
      </Section>

      {/* ── Chairman verdict ── */}
      <ChairmanRationale
        rationale={result.chairman_rationale}
        decision={result.decision}
        score={result.weighted_score}
        priceTargets={result.price_targets}
        stopLoss={result.stop_loss}
      />

      {/* ── Agent tabs ── */}
      <div>
        <div className="text-xs text-gray-600 uppercase tracking-wider mb-2 px-1">Agent Breakdown</div>
        <AgentTabs votes={result.agent_votes} />
      </div>

      {/* ── Analyze another ── */}
      <div className="text-center pt-1 pb-4">
        <button
          onClick={onReset}
          className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors underline underline-offset-2"
        >
          ↺ Analyze another stock
        </button>
      </div>
    </div>
  )
}

// ── Search with autocomplete ───────────────────────────────────────────────────
function SearchBox({ onRun, loading }) {
  const [query, setQuery]       = useState('')
  const [suggestions, setSugg]  = useState([])
  const [showSugg, setShowSugg] = useState(false)
  const inputRef  = useRef(null)
  const debounce  = useRef(null)

  const handleChange = (val) => {
    setQuery(val)
    clearTimeout(debounce.current)
    // If looks like a raw ticker (≤5 chars, all alpha/digit) skip search
    const isSymbol = /^[A-Z0-9.]{1,6}$/.test(val.trim().toUpperCase())
    if (!val.trim() || isSymbol) { setSugg([]); return }
    debounce.current = setTimeout(async () => {
      try {
        const results = await api.search(val.trim())
        setSugg(results.slice(0, 6))
        setShowSugg(true)
      } catch { setSugg([]) }
    }, 400)
  }

  const submit = (sym) => {
    setSugg([]); setShowSugg(false)
    onRun(sym || query.trim().toUpperCase())
  }

  return (
    <div className="relative w-full max-w-xl mx-auto">
      <div className="flex gap-3">
        <div className="flex-1 relative">
          <span className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500 text-base select-none pointer-events-none">🔍</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => handleChange(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') setShowSugg(false) }}
            onFocus={() => suggestions.length && setShowSugg(true)}
            placeholder="Ticker, company name, or sector…"
            className="w-full bg-gray-900 border border-white/10 rounded-2xl pl-11 pr-4 py-3.5 text-white placeholder-gray-600
                       text-sm focus:outline-none focus:border-indigo-500/60 focus:ring-1 focus:ring-indigo-500/30 transition-all"
            disabled={loading}
            autoFocus
          />
          {/* Autocomplete dropdown */}
          {showSugg && suggestions.length > 0 && (
            <div className="absolute top-full mt-1.5 left-0 right-0 bg-gray-900 border border-white/10 rounded-xl overflow-hidden shadow-xl z-50">
              {suggestions.map((s, i) => (
                <button
                  key={i}
                  className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-800 transition-colors text-left"
                  onClick={() => submit(s.symbol)}
                >
                  <span className="font-bold text-white text-sm w-16 flex-shrink-0">{s.symbol}</span>
                  <span className="text-gray-400 text-xs truncate">{s.name}</span>
                  <span className="ml-auto text-xs text-gray-600 flex-shrink-0">{s.exchangeShortName}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <button
          onClick={() => submit()}
          disabled={loading || !query.trim()}
          className="px-6 py-3.5 rounded-2xl bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold
                     transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2 flex-shrink-0"
        >
          {loading ? <span className="animate-spin">⚙️</span> : '▶'}
          {loading ? 'Analyzing…' : 'Analyze'}
        </button>
      </div>
    </div>
  )
}

// ── Time-based greeting (America/New_York = EST/EDT) ─────────────────────────
function useGreeting() {
  const estHour = parseInt(
    new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      hour: 'numeric',
      hour12: false,
    }).format(new Date()),
    10
  )
  if (estHour >= 5  && estHour < 12) return 'Good morning'
  if (estHour >= 12 && estHour < 17) return 'Good afternoon'
  return 'Good evening'
}

// ── Quick-start suggestion cards ─────────────────────────────────────────────
const SUGGESTIONS = [
  { ticker: 'NVDA', label: 'Deep dive on NVDA',       sub: 'AI chip leader — still room to run?' },
  { ticker: 'TSLA', label: 'Is TSLA a buy right now?', sub: 'Valuation, sentiment & technicals'   },
  { ticker: 'RKLB', label: 'Analyze RKLB',             sub: 'Space-tech underdog — upside play?'  },
  { ticker: 'AAPL', label: "Apple's earnings outlook", sub: 'Services growth vs hardware cycle'   },
]

// ── Main page ──────────────────────────────────────────────────────────────────
export default function Analyze() {
  const [loading, setLoading] = useState(false)
  const [result,  setResult]  = useState(null)
  const [error,   setError]   = useState(null)
  const greeting = useGreeting()

  const run = async (sym) => {
    if (!sym) return
    setLoading(true); setResult(null); setError(null)
    try {
      const data = await api.analyze(sym.toUpperCase(), 'US')
      setResult(data)
    } catch (e) {
      setError(`Analysis failed: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  const reset = () => { setResult(null); setError(null) }

  // ── Result view ──
  if (result && !loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-6">
        <AnalysisResult result={result} onReset={reset} />
      </div>
    )
  }

  // ── Loading view ──
  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-6">
        <AnalysisSpinner ticker="…" />
      </div>
    )
  }

  // ── Landing view (Claude-style) ──
  return (
    <div className="min-h-[calc(100vh-56px)] flex flex-col items-center justify-center px-4 pb-16 pt-8">
      <div className="w-full max-w-2xl flex flex-col items-center gap-10">

        {/* ── Greeting ── */}
        <div className="text-center space-y-3">
          <h1 className="text-4xl sm:text-5xl font-bold tracking-tight bg-gradient-to-br from-white via-gray-100 to-gray-400 bg-clip-text text-transparent">
            {greeting}, Investor.
          </h1>
          <p className="text-gray-500 text-base max-w-sm mx-auto leading-relaxed">
            5 AI agents debate every stock. What would you like to analyze today?
          </p>
        </div>

        {/* ── Search ── */}
        <div className="w-full">
          <SearchBox onRun={run} loading={loading} />
        </div>

        {/* ── Suggestion cards ── */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
          {SUGGESTIONS.map(s => (
            <button
              key={s.ticker}
              onClick={() => run(s.ticker)}
              className="text-left px-4 py-3.5 rounded-2xl border border-white/8 bg-gray-900/50
                         hover:bg-gray-800/70 hover:border-white/15 transition-all group"
            >
              <div className="text-sm font-semibold text-gray-200 group-hover:text-white leading-snug">
                {s.label}
              </div>
              <div className="text-xs text-gray-500 mt-0.5 leading-snug">{s.sub}</div>
            </button>
          ))}
        </div>

        {/* ── Error ── */}
        {error && (
          <div className="w-full rounded-xl border border-red-500/30 bg-red-500/5 text-red-400 text-sm p-3 text-left">
            ⚠️ {error}
          </div>
        )}

      </div>
    </div>
  )
}
