const AGENT_META = {
  technician:     { label: 'The Technician',     icon: '📈', role: 'Technical Analysis' },
  fundamentalist: { label: 'The Fundamentalist', icon: '📊', role: 'Fundamental Analysis' },
  newshound:      { label: 'The Newshound',       icon: '📰', role: 'News & Sentiment' },
  macro_watcher:  { label: 'The Macro Watcher',  icon: '🌍', role: 'Macro & Sectors' },
  risk_manager:   { label: 'The Risk Manager',   icon: '🛡️', role: 'Risk & Portfolio' },
}

const ACTION_STYLE = {
  BUY:  { badge: 'badge-buy',  bar: 'bg-green-500' },
  SELL: { badge: 'badge-sell', bar: 'bg-red-500' },
  HOLD: { badge: 'badge-hold', bar: 'bg-gray-500' },
}

export default function AgentCard({ vote }) {
  const { agent_name, action, confidence, rationale, veto } = vote
  const meta = AGENT_META[agent_name] ?? { label: agent_name, icon: '🤖', role: '' }
  const style = ACTION_STYLE[action] ?? ACTION_STYLE.HOLD
  const confPct = Math.round((confidence ?? 0) * 100)

  return (
    <div className={`card relative flex flex-col gap-2 ${veto ? 'border-red-500/40' : ''}`}>
      {/* Veto banner */}
      {veto && (
        <div className="absolute inset-x-0 top-0 bg-red-600/90 text-white text-xs font-bold text-center py-1 rounded-t-xl tracking-widest">
          ⛔ VETOED
        </div>
      )}

      <div className={veto ? 'mt-5' : ''}>
        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-lg leading-none">{meta.icon}</span>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-white leading-tight truncate">{meta.label}</div>
              <div className="text-xs text-gray-500 truncate">{meta.role}</div>
            </div>
          </div>
          <span className={style.badge}>{action ?? 'HOLD'}</span>
        </div>

        {/* Confidence bar */}
        {agent_name !== 'risk_manager' && (
          <div className="mt-2.5">
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>Confidence</span>
              <span>{confPct}%</span>
            </div>
            <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${style.bar}`}
                style={{ width: `${confPct}%` }}
              />
            </div>
          </div>
        )}

        {/* Rationale */}
        <p className="mt-2.5 text-xs text-gray-400 leading-relaxed line-clamp-4">{rationale || '—'}</p>
      </div>
    </div>
  )
}
