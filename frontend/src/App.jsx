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
      {/* ── Header ── */}
      <header className="fixed top-0 inset-x-0 z-50 bg-gray-950/95 backdrop-blur-md border-b border-white/8">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between gap-8">

          {/* Logo + wordmark */}
          <div className="flex items-center gap-3 flex-shrink-0">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-600/30">
              <span className="text-white text-sm font-black">AI</span>
            </div>
            <div>
              <div className="text-white text-sm font-bold tracking-tight leading-none">AI Hedge Fund</div>
              <div className="text-gray-500 text-[10px] leading-none mt-0.5 tracking-wide">PAPER TRADING</div>
            </div>
          </div>

          {/* Navigation tabs — left-aligned after logo */}
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
                <span className="mr-1.5 opacity-70">{t.icon}</span>
                {t.label}
                {tab === t.id && (
                  <span className="absolute bottom-0 left-3 right-3 h-0.5 bg-indigo-500 rounded-full" />
                )}
              </button>
            ))}
          </nav>

          {/* Right side — spacer / future home for account/settings */}
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            <span className="hidden sm:flex items-center gap-1.5 text-xs text-gray-600 bg-gray-900 border border-white/5 px-3 py-1.5 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
              Live
            </span>
          </div>

        </div>
      </header>

      {/* ── Page content ── */}
      <div className="pt-16">
        {tab === 'analyze'   && <Analyze />}
        {tab === 'portfolio' && <Portfolio />}
        {tab === 'forex'     && <ForexPortfolio />}
      </div>
    </div>
  )
}
