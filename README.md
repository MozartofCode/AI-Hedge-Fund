# AI Hedge Fund

An autonomous paper trading system powered by AI. This is a **US-only stock hedge fund**:
a committee of AI agents independently analyzes US-listed stocks (NYSE / NASDAQ), debates
the evidence, and executes paper trades — starting with $1,000,000 and no brokerage account
needed.

---

## What It Does

Five AI analysts each study a different angle of a stock — its price chart, financial health,
recent news, the overall economy, and risk — then each votes to buy, sell, or hold. A Chairman
AI reads all five opinions and makes the final call, like a group of advisors debating before
a boss decides. Trades execute automatically during US market hours and every position is
tracked live.

---

## Architecture

```
                    ┌─────────────────────────────┐
                    │   React 18 + Tailwind CSS    │
                    │   Vercel (frontend)          │
                    └─────────────┬───────────────┘
                                  │ REST
                    ┌─────────────▼───────────────┐
                    │   FastAPI + APScheduler      │
                    │   backend                    │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │      US Stock Committee      │
                    │                              │
                    │  Technician                  │
                    │  Fundamentalist              │
                    │  Newshound                   │
                    │  Macro Watcher               │
                    │  Risk Manager (pure logic)   │
                    │  Chairman (AI)               │
                    └─────────────┬───────────────┘
                                  │
                    ┌─────────────▼───────────────┐
                    │   PostgreSQL — Supabase      │
                    └──────────────────────────────┘
```

**AI Models:** Groq Llama for the agents and the Chairman
**Data:** yfinance (prices, free) · Finnhub (news) · FMP (fundamentals & screener)

---

## Features

- **US Stock Portfolio** — autonomous paper trading on NYSE / NASDAQ; $1M starting balance;
  positions tracked live with a P&L heatmap and trade history
- **Committee transparency** — click any position or trade to see every agent's vote and the
  Chairman's rationale
- **Free to run** — Groq's free Llama tier powers every agent and the Chairman, so there's no
  per-call API spend
- **Plain-English results** — all agent rationales and metric labels are written for everyday
  investors, not finance professionals

---

## Setup

### Environment Variables

**Backend:**
```
GROQ_API_KEY=...
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@db.<project>.supabase.co:5432/postgres
FINNHUB_API_KEY=...
FMP_API_KEY=...
COMMITTEE_MAX_TICKERS=30
FRONTEND_URL=https://your-app.vercel.app
```

**Frontend (Vercel):**
```
VITE_API_URL=https://your-backend-host
```

> FMP free tier (250 calls/day) works for most metrics. If unavailable, the system
> automatically falls back to yfinance for all fundamental data — nothing breaks.

### Local Development

```bash
# Backend
pip install -r requirements.txt
uvicorn backend.main:app --reload

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Backend: http://localhost:8000
Frontend: http://localhost:5173

### Deployment

See [DEPLOY_FREE.md](DEPLOY_FREE.md) for free hosting options (Render + GitHub Actions cron,
or an Oracle Cloud always-free VM). The frontend deploys to Vercel with root set to `frontend/`.

---

## Project Structure

```
AI-Hedge-Fund/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── orchestrator.py          # US stock committee logic + autonomous trading
│   ├── scheduler.py             # Daily auto-trading schedule (US session)
│   ├── markets.py               # US market hours + open/close check
│   ├── screener.py              # Dynamic US watchlist (FMP + seed list)
│   ├── agents/                  # The 5 AI agents
│   ├── broker/                  # Paper trading execution (yfinance prices)
│   ├── data/                    # Market data clients (yfinance, Finnhub, FMP)
│   ├── db/                      # Database models + CRUD
│   └── api/                     # FastAPI route handlers
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Portfolio.jsx    # US portfolio: heatmap + trades + committee view
│       │   └── Trades.jsx       # Trade history + committee session detail
│       └── App.jsx
└── requirements.txt
```

---

## License

MIT
