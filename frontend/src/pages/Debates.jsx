import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import AgentCard from '../components/AgentCard'

const DECISION_STYLE = {
  BUY:  'badge-buy',
  SELL: 'badge-sell',
  HOLD: 'badge-hold',
}

function Pagination({ page, pages, onPage }) {
  if (pages <= 1) return null
  return (
    <div className="flex items-center justify-center gap-2 pt-2">
      <button
        onClick={() => onPage(p => Math.max(1, p - 1))}
        disabled={page === 1}
        className="px-3 py-1.5 text-xs rounded-lg bg-gray-800 text-gray-300 disabled:opacity-30 hover:bg-gray-700 transition-colors"
      >
        ← Prev
      </button>
      <span className="text-xs text-gray-500">{page} / {pages}</span>
      <button
        onClick={() => onPage(p => Math.min(pages, p + 1))}
        disabled={page === pages}
        className="px-3 py-1.5 text-xs rounded-lg bg-gray-800 text-gray-300 disabled:opacity-30 hover:bg-gray-700 transition-colors"
      >
        Next →
      </button>
    </div>
  )
}

function SessionRow({ session, selected, onClick }) {
  const isSelected = selected?.id === session.id
  const score = session.weighted_score

  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-3 py-3 rounded-lg border transition-all ${
        isSelected
          ? 'bg-indigo-500/10 border-indigo-500/30'
          : 'border-transparent hover:bg-gray-800/60 hover:border-gray-700'
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="font-bold text-white text-sm">{session.ticker}</span>
        <span className={DECISION_STYLE[session.decision] ?? 'badge-hold'}>{session.decision ?? '—'}</span>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-gray-500">
          {session.session_timestamp
            ? new Date(session.session_timestamp).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
            : '—'}
        </span>
        {score != null && (
          <span className="text-xs text-gray-600">score {score.toFixed(2)}</span>
        )}
      </div>
      {session.order_placed && (
        <div className="mt-1">
          <span className="text-xs bg-green-500/10 text-green-500 border border-green-500/20 rounded px-1.5 py-0.5">
            ✓ Order placed
          </span>
        </div>
      )}
    </button>
  )
}

function ChairmanVerdict({ session }) {
  const hasVeto = session.agent_votes?.some(v => v.veto)

  return (
    <div className="card border-indigo-500/20">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg">🏛️</span>
            <h2 className="text-base font-bold text-white">
              {session.ticker} — Chairman's Verdict
            </h2>
          </div>
          <div className="flex items-center gap-3">
            <span className={DECISION_STYLE[session.decision] ?? 'badge-hold'}>
              {session.decision ?? '—'}
            </span>
            {session.weighted_score != null && (
              <span className="text-xs text-gray-500">
                Weighted score: <span className="text-gray-300">{session.weighted_score.toFixed(3)}</span>
              </span>
            )}
            {session.session_timestamp && (
              <span className="text-xs text-gray-600">
                {new Date(session.session_timestamp).toLocaleString()}
              </span>
            )}
          </div>
        </div>
        {hasVeto && (
          <div className="flex-shrink-0 bg-red-600/20 border border-red-500/30 text-red-400 text-xs font-bold px-2.5 py-1 rounded-lg">
            ⛔ VETOED
          </div>
        )}
      </div>

      {/* Rationale */}
      {session.chairman_rationale && (
        <blockquote className="border-l-2 border-indigo-500/50 pl-3 text-sm text-gray-300 italic leading-relaxed mb-4">
          "{session.chairman_rationale}"
        </blockquote>
      )}

      {/* Agent cards */}
      {session.agent_votes?.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Agent Votes</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {session.agent_votes.map(v => (
              <AgentCard key={v.agent_name} vote={v} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function Debates() {
  const [sessions, setSessions] = useState([])
  const [selected, setSelected] = useState(null)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const data = await api.debates(page, 20)
      setSessions(data.items ?? [])
      setPages(data.pages ?? 1)
      setTotal(data.total ?? 0)
      // Auto-select first session if none selected
      if (!selected && data.items?.length) setSelected(data.items[0])
    } catch (e) {
      console.error('Debates refresh failed:', e)
    } finally {
      setLoading(false)
    }
  }, [page]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setLoading(true)
    refresh()
    const id = setInterval(refresh, 60_000)
    return () => clearInterval(id)
  }, [refresh])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-white">Committee Debates</h1>
        {total > 0 && (
          <span className="text-xs text-gray-600">{total.toLocaleString()} sessions</span>
        )}
      </div>

      <div className="flex gap-4 items-start">
        {/* Session list */}
        <div className="w-64 flex-shrink-0 card flex flex-col gap-1 max-h-[calc(100vh-10rem)] overflow-y-auto">
          {loading && !sessions.length ? (
            Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-16 bg-gray-800/50 rounded-lg animate-pulse" />
            ))
          ) : sessions.length === 0 ? (
            <p className="text-sm text-gray-600 text-center py-6">No sessions yet</p>
          ) : (
            sessions.map(s => (
              <SessionRow
                key={s.id}
                session={s}
                selected={selected}
                onClick={() => setSelected(s)}
              />
            ))
          )}
          <Pagination page={page} pages={pages} onPage={setPage} />
        </div>

        {/* Detail panel */}
        <div className="flex-1 min-w-0">
          {selected ? (
            <ChairmanVerdict session={selected} />
          ) : (
            <div className="card flex items-center justify-center h-48 text-gray-600 text-sm">
              Select a session to view the committee debate
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
