# AI Hedge Fund — CLAUDE.md

Autonomous multi-agent paper trading system for **US stocks only** (NYSE / NASDAQ).
Five AI agents debate every stock, a Chairman synthesizes the votes, and the system
trades $1,000,000 of paper money — no brokerage account needed.

---

## Project Stack

| Layer | Tech |
|---|---|
| Backend | Python + FastAPI + APScheduler |
| Frontend | React 18 + Tailwind CSS + Recharts — Vercel |
| Database | PostgreSQL — Supabase |
| AI | Groq Llama (agents + Chairman) |
| Market Data | yfinance (prices, free), Finnhub (news), FMP (fundamentals & screener) |

---

## Repository Structure

```
AI-Hedge-Fund/
├── backend/
│   ├── main.py                       # FastAPI app + lifespan (DB init, US portfolio seed), /api/health, /api/run-committee
│   ├── scheduler.py                  # APScheduler: 1 US session/day + 30-min portfolio snapshots
│   ├── orchestrator.py               # US committee runner: run_full_committee(), run_committee_for_ticker()
│   ├── markets.py                    # US market hours + is_market_open()
│   ├── screener.py                   # Dynamic US watchlist (FMP screener + seed list)
│   ├── agents/
│   │   ├── base_agent.py             # call_llm(), Groq client + model config
│   │   ├── technician.py             # Multi-TF TA: EMA/RSI/MACD/ATR/BB/OB/Fib
│   │   ├── fundamentalist.py         # FMP financials + yfinance fallback
│   │   ├── newshound.py              # Finnhub news & sentiment
│   │   ├── macro_watcher.py          # VIX + sector ETFs + macro calendar (30-min cache)
│   │   └── risk_manager.py           # Pure logic: drawdown guard, max positions, position size
│   ├── broker/
│   │   └── paper_broker.py           # Paper trading: yfinance prices + DB positions
│   ├── data/
│   │   ├── fmp_client.py             # FMP API: P/E, revenue, balance sheet, DCF, analyst ratings
│   │   ├── finnhub_client.py         # News, sentiment, insider data, economic calendar
│   │   └── indicators.py             # Pure-pandas TA helpers (SMA/EMA/RSI/MACD/ATR…)
│   ├── db/
│   │   ├── models.py                 # SQLAlchemy ORM — 6 tables
│   │   ├── crud.py                   # Async DB helpers
│   │   └── session.py                # AsyncSessionLocal + engine
│   └── api/
│       ├── portfolio.py              # GET /api/portfolio
│       ├── trades.py                 # GET /api/trades
│       ├── debates.py                # GET /api/session/{id}, GET /api/latest-session/{ticker}
│       └── stats.py                  # GET /api/stats
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Portfolio.jsx         # US portfolio: heatmap + positions + trades + per-position committee view
│       │   └── Trades.jsx            # Trade history + committee session detail (shared modal body)
│       ├── api.js                    # All fetch helpers
│       └── App.jsx                   # Header + Portfolio page
├── requirements.txt
└── CLAUDE.md
```

---

## Models

```python
AGENT_MODEL             = "llama-3.3-70b-versatile"     # all agents (Groq, free tier)
CHAIRMAN_SCHEDULE_MODEL = "llama-3.3-70b-versatile"     # Chairman
```

Groq's free tier is the sole LLM provider — no API spend to track or cap.

---

## The Agents (5)

| Agent | Data Source | LLM? | Role |
|---|---|---|---|
| Technician | yfinance OHLCV (daily/weekly/monthly) | Yes | EMA, RSI, MACD, ATR, Bollinger Bands, order blocks, Fibonacci |
| Fundamentalist | FMP (yfinance fallback if FMP empty) | Yes | P/E, revenue growth, FCF, margins, DCF, analyst consensus |
| Newshound | Finnhub | Yes | News sentiment, insider MSPR, earnings surprise |
| Macro Watcher | yfinance VIX + sector ETFs, Finnhub calendar | Yes | VIX risk-off flag, sector rotation, macro events |
| Risk Manager | Portfolio state only — no external calls | No | Drawdown guard, max positions, position size, stop-loss / take-profit |

Chairman: runs only on BUY/SELL (skipped for plain HOLDs to save tokens).

Base weights (regime-adjusted in `_get_weights`):
Technician 0.30 · Fundamentalist 0.25 · Newshound 0.20 · Macro Watcher 0.25 · Risk Manager (veto)
Thresholds: BUY >= 0.52 · SELL <= 0.45 (see `BUY_THRESHOLD` / `SELL_THRESHOLD` in orchestrator.py)

---

## Scheduler

US session — 2/day (Mon–Fri, US/Eastern): 10:00 and 14:00
Portfolio snapshots — every 30 min during market hours.

`COMMITTEE_MAX_TICKERS` env var (default 30) limits tickers per session.

On free/sleeping hosts set `ENABLE_SCHEDULER=false` and drive trades via the GitHub Actions
cron (`.github/workflows/committee.yml`), which POSTs to `/api/run-committee`.

---

## Database Schema (PostgreSQL on Supabase)

| Table | Purpose |
|---|---|
| paper_portfolio | Single row — cash balance (starts $1,000,000) |
| paper_positions | Open positions (ticker, qty, avg_cost) |
| committee_sessions | Every committee run (ticker, decision, score, chairman rationale) |
| agent_votes | Each vote per session (action, confidence, rationale, raw data) |
| trades | Executed paper trades (side, qty, filled_price) |
| portfolio_snapshots | Equity curve snapshots every 30 min |

Rows carry a `market` column (always `'US'`). `Base.metadata.create_all` runs on boot.

---

## Environment Variables

```
GROQ_API_KEY=...
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@db.<project>.supabase.co:5432/postgres
FINNHUB_API_KEY=...
FMP_API_KEY=...
COMMITTEE_MAX_TICKERS=30
ENABLE_SCHEDULER=true
CRON_SECRET=
FRONTEND_URL=https://your-app.vercel.app
```

---

## API Endpoints

```
GET  /api/health
GET  /api/portfolio
GET  /api/stats
GET  /api/trades?page=1&limit=20
GET  /api/session/{session_id}
GET  /api/latest-session/{ticker}
POST /api/run-committee                  # autonomous committee (external cron); CRON_SECRET-gated
```

---

## Running Locally

```bash
# Backend
pip install -r requirements.txt
uvicorn backend.main:app --reload

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Backend: http://localhost:8000
Frontend: http://localhost:5173

---

## Important Notes

- FMP fallback: if the FMP key is missing or exhausted, fundamentalist.py auto-falls back to yfinance.
- Macro cache: VIX + sector data cached 30 min.
- DB auto-create: Base.metadata.create_all runs on boot; no manual migration needed.
- Prices/positions are paper only — `paper_broker.py` uses yfinance quotes, no real brokerage.
