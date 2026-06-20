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

**AI Models:** Claude Haiku for the agents · Groq Llama (default) or Claude for the Chairman,
selectable with `SCHEDULED_PROVIDER`
**Data:** yfinance (prices, free) · Finnhub (news) · FMP (fundamentals & screener)

---

## Features

- **US Stock Portfolio** — autonomous paper trading on NYSE / NASDAQ; $1M starting balance;
  positions tracked live with a P&L heatmap and trade history
- **Committee transparency** — click any position or trade to see every agent's vote and the
  Chairman's rationale
- **Daily budget guard** — Claude spend is capped (default $1.25/day) so there are no
  surprise bills
- **Plain-English results** — all agent rationales and metric labels are written for everyday
  investors, not finance professionals

---

## Cost Profile

| Component | Model | Cost |
|---|---|---|
| 4 stock agents (per ticker) | Claude Haiku | ~$0.002 |
| Chairman (per BUY/SELL) | Claude Haiku / Groq | ~$0.001 |
| Scheduled committee (daily, ~30 tickers) | Haiku | ~$0.91/day |

Using Groq's free Llama tier for the scheduled trader (`SCHEDULED_PROVIDER=groq`, the default)
drops the daily Claude spend close to zero.

---

## Setup

### Environment Variables

**Backend:**
```
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=...
SCHEDULED_PROVIDER=groq
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@db.<project>.supabase.co:5432/postgres
FINNHUB_API_KEY=...
FMP_API_KEY=...
DAILY_BUDGET_USD=1.25
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
