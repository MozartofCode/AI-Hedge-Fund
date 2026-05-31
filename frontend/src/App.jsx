import { useState } from 'react'
import Analyze        from './pages/Analyze'
import Portfolio      from './pages/Portfolio'
import ForexPortfolio from './pages/ForexPortfolio'

const TABS = [
  { id: 'analyze',   label: 'Analyze',         icon: '🔬' },
  { id: 'portfolio', label: 'Stock Portfolio',  icon: '💼' },
  { id: 'forex',     label: 'Forex Trading',    icon: '💱' },
]

export default function App() {
  const [tab, setTab] = useState('analyze')

  return (
    <div className="min-h-screen bg-gray-950">
      {/* ── Top nav ── */}
      <nav className="fixed top-0 inset-x-0 z-50 bg-gray-950/90 backdrop-blur-md border-b border-white/5">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
          <div />
          <div className="flex gap-1 bg-gray-900 p-1 rounded-xl border border-white/5">
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                  tab === t.id
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                {t.icon} {t.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* ── Page content ── */}
      <div className="pt-14">
        {tab === 'analyze'   && <Analyze />}
        {tab === 'portfolio' && <Portfolio />}
        {tab === 'forex'     && <ForexPortfolio />}
      </div>
    </div>
  )
}
