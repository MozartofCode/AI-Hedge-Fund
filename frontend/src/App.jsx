import { useState } from 'react'
import Analyze        from './pages/Analyze'
import Portfolio      from './pages/Portfolio'

const TABS = [
  { id: 'analyze',   label: 'Analyze',         icon: '🔬' },
  { id: 'portfolio', label: 'Stock Portfolio',  icon: '💼' },
]

export default function App() {
  const [tab, setTab] = useState('analyze')

  return (
    <div className="min-h-screen bg-gray-950">
      {/* ── Header ── */}
      <header className="fixed top-0 inset-x-0 z-50 bg-gray-950/95 backdrop-blur-md border-b border-white/8">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between gap-8">

          {/* Navigation tabs */}
          <nav className="flex items-center gap-1">
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`relative px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  tab === t.id
                    ? 'text-white bg-white/8'
                    : 'text-gray-500 hover:text-gray-300 hover:bg-white/4'
                }`}
              >
                {t.label}
                {tab === t.id && (
                  <span className="absolute bottom-0 left-3 right-3 h-0.5 bg-indigo-500 rounded-full" />
                )}
              </button>
            ))}
          </nav>

          <div className="flex-1" />

        </div>
      </header>

      {/* ── Page content ── */}
      <div className="pt-16">
        {tab === 'analyze'   && <Analyze />}
        {tab === 'portfolio' && <Portfolio />}
      </div>
    </div>
  )
}
