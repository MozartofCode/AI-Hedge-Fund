import { useEffect, useState } from 'react'
import { Routes, Route, NavLink } from 'react-router-dom'
import Portfolio from './pages/Portfolio'
import Trades from './pages/Trades'
import Analyze from './pages/Analyze'
import { api } from './api'

function NavItem({ to, children }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
          isActive
            ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
            : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
        }`
      }
    >
      {children}
    </NavLink>
  )
}

export default function App() {
  const [marketOpen, setMarketOpen] = useState(null)

  useEffect(() => {
    api.health()
      .then(d => setMarketOpen(d.market_open))
      .catch(() => setMarketOpen(false))
    const id = setInterval(() =>
      api.health().then(d => setMarketOpen(d.market_open)).catch(() => {}),
    60_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <header className="border-b border-gray-800 bg-gray-950/90 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <span className="text-base font-bold tracking-tight text-white flex items-center gap-2">
              🏛️ <span>AlphaCommittee</span>
            </span>
            <nav className="flex gap-1">
              <NavItem to="/">Portfolio</NavItem>
              <NavItem to="/trades">Trades</NavItem>
              <NavItem to="/analyze">Analyze</NavItem>
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${
                marketOpen
                  ? 'bg-green-500/10 text-green-400 border-green-500/25'
                  : 'bg-gray-500/10 text-gray-500 border-gray-600/25'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${marketOpen ? 'bg-green-400 animate-pulse' : 'bg-gray-500'}`} />
              {marketOpen === null ? 'Connecting…' : marketOpen ? 'Market Open' : 'Market Closed'}
            </span>
          </div>
        </div>
      </header>

      {/* Page */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <Routes>
          <Route path="/"        element={<Portfolio />} />
          <Route path="/trades"  element={<Trades />} />
          <Route path="/analyze" element={<Analyze />} />
        </Routes>
      </main>
    </div>
  )
}
