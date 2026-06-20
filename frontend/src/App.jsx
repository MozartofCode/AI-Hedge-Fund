import Portfolio from './pages/Portfolio'

export default function App() {
  return (
    <div className="min-h-screen bg-gray-950">
      {/* ── Header ── */}
      <header className="fixed top-0 inset-x-0 z-50 bg-gray-950/95 backdrop-blur-md border-b border-white/8">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center gap-3">
          <span className="text-xl">💼</span>
          <span className="text-sm font-semibold text-white">Stock Portfolio</span>
        </div>
      </header>

      {/* ── Page content ── */}
      <div className="pt-16">
        <Portfolio />
      </div>
    </div>
  )
}
