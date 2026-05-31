# AI Hedge Fund — CLAUDE.md

Autonomous multi-agent paper trading system. Five AI agents debate every stock,
a Chairman synthesizes the votes, and the system trades $1,000,000 of paper money
across global stock markets and 10 forex pairs — no brokerage account needed.

---

## Project Stack

| Layer | Tech |
|---|---|
| Backend | Python + FastAPI + APScheduler — Railway |
| Frontend | React 18 + Tailwind CSS + Recharts — Vercel |
| Database | PostgreSQL — Supabase (project: AI Investor, id: ysqopwgijjhubarumayq) |
| AI | Anthropic Claude (Haiku for all agents, Sonnet for on-demand Chairman) |
| Market Data | yfinance (free, unlimited), Finnhub (news), FMP (fundamentals) |

---

## Repository Structure

```
AI-Hedge-Fund/
├── backend/
│   ├── main.py                       # FastAPI app + lifespan (DB init, forex portfolio seed)
│   ├── scheduler.py                  # APScheduler: 1 session/day per market + 2 forex sessions
│   ├── orchestrator.py               # Stock committee runner + analyze_ticker()
│   ├── forex_orchestrator.py         # Forex committee runner
│   ├── markets.py                    # Market open/close times + is_market_open()
│   ├── agents/
│   │   ├── base_agent.py             # call_claude(), daily budget guard, model constants
│   │   ├── technician.py             # Multi-TF TA: EMA/RSI/MACD/ATR/BB/OB/Fib
│   │   ├── fundamentalist.py         # FMP financials + yfinance fallback
│   │   ├── newshound.py              # Finnhub news & sentiment
│   │   ├── macro_watcher.py          # VIX + 10 sector ETFs + macro calendar (30-min cache)
│   │   ├── risk_manager.py           # Pure logic: drawdown guard, max positions, position size
│   │   ├── fx_technician.py          # Forex TA: EMA 20/50/200, RSI, MACD, ATR (10-min cache)
│   │   ├── fx_carry.py               # Carry trade: interest rate differential signal
│   │   ├── fx_macro.py               # DXY, VIX, oil, gold + pair-specific context
│   │   └── fx_risk_manager.py        # Pure logic: correlation veto, max 5 positions, stop-loss
│   ├── broker/
│   │   ├── paper_broker.py           # Stock paper trading: yfinance prices + DB positions
│   │   └── forex_broker.py           # Forex paper trading: is_forex_market_open(), place_order()
│   ├── data/
│   │   ├── forex_client.py           # yfinance forex wrappers, CB rates dict, macro snapshot
│   │   ├── fmp_client.py             # FMP API: P/E, revenue, balance sheet, analyst ratings
│   │   ├── finnhub_client.py         # News, sentiment, insider data, economic calendar
│   │   └── alphavantage_client.py    # Configured but unused
│   ├── db/
│   │   ├── models.py                 # SQLAlchemy ORM — 9 tables
│   │   ├── crud.py                   # Async DB helpers + forex CRUD
│   │   └── session.py                # AsyncSessionLocal + engine
│   └── api/
│       ├── portfolio.py              # GET /api/portfolio
│       ├── trades.py                 # GET /api/trades
│       ├── debates.py                # GET /api/debates
│       ├── stats.py                  # GET /api/stats (includes claude_daily_spend_usd)
│       └── forex.py                  # GET+POST /api/forex/*
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Analyze.jsx           # Search landing + full analysis result view
│       │   ├── Portfolio.jsx         # Stock portfolio: heatmap + equity curve + trades
│       │   └── ForexPortfolio.jsx    # Forex: live rates strip + positions + trades
│       ├── api.js                    # All fetch helpers
│       └── App.jsx                   # Header (3 tabs) + page routing
├── requirements.txt
└── CLAUDE.md
```

---

## Models & Cost

```python
AGENT_MODEL             = "claude-haiku-4-5-20251001"   # all agents
CHAIRMAN_MODEL          = "claude-sonnet-4-6"            # on-demand analyze only
CHAIRMAN_SCHEDULE_MODEL = "claude-haiku-4-5-20251001"   # scheduled committee (cost saving)

DAILY_BUDGET_USD = float(os.getenv("DAILY_BUDGET_USD", "1.00"))
```

call_claude() checks is_over_daily_budget() before every Claude call and returns a HOLD
fallback if the cap is reached. Cost is tracked in a module-level _budget dict that resets
at midnight UTC.

Recommended env var: DAILY_BUDGET_USD=1.25 (covers ~$0.91 stock + ~$0.09 forex + headroom).

---

## The Agents

### Stock Agents (5)

| Agent | Data Source | Claude? | Role |
|---|---|---|---|
| Technician | yfinance OHLCV (daily/weekly/monthly) | Haiku | EMA, RSI, MACD, ATR, Bollinger Bands, order blocks, Fibonacci |
| Fundamentalist | FMP (yfinance fallback if FMP empty) | Haiku | P/E, revenue growth, FCF, margins, DCF, analyst consensus |
| Newshound | Finnhub | Haiku | News sentiment, insider MSPR, earnings surprise |
| Macro Watcher | yfinance VIX + 10 sector ETFs, Finnhub calendar | Haiku | VIX risk-off flag, sector rotation, macro events |
| Risk Manager | Portfolio state only — no external calls | No | Drawdown guard (>=8% veto), max 3 positions, 5% position size |

Chairman: Sonnet on-demand / Haiku scheduled. Skipped entirely for plain HOLDs.

Weights: Technician 25% · Fundamentalist 20% · Newshound 20% · Macro Watcher 15% · Risk Manager (veto)
Thresholds: BUY >= 0.60 · SELL <= 0.35

### Forex Agents (4)

| Agent | Strategy | Claude? |
|---|---|---|
| FX Technician | EMA 20/50/200 alignment, RSI, MACD, ATR — returns momentum_score | Haiku |
| FX Carry | Interest rate differential (base_rate - quote_rate) + trend confirmation | Haiku |
| FX Macro | DXY, VIX, oil, gold + pair-specific USD relationship | Haiku |
| FX Risk Manager | Max 5 positions, 15% drawdown limit, correlation veto, 1.5xATR stop-loss | No |

Weights: FX Technician 35% · FX Carry 30% · FX Macro 35%
Thresholds: BUY >= 0.55 · SELL <= 0.45

10 Pairs: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCHF, USDCAD, NZDUSD, EURJPY, GBPJPY, USDMXN

Correlation veto (same direction blocked): EURUSD/GBPUSD · AUDUSD/NZDUSD · USDJPY/USDCHF

---

## Scheduler

Stock markets — 1 session/day (Mon-Fri, local market time):
  US: 11:30  BR: 12:00  AR: 13:00  TR: 11:00  NG: 12:00

Forex — 2 sessions/day (Mon-Fri, UTC):
  13:00 (London/NY overlap)  18:00 (NY afternoon)

Portfolio snapshots — every 30 min during market hours per market

COMMITTEE_MAX_TICKERS env var (default 30) limits tickers per session.

---

## Database Schema (PostgreSQL on Supabase)

All 9 tables have RLS enabled. FastAPI connects via direct Postgres superuser URL which bypasses RLS.

| Table | Purpose |
|---|---|
| paper_portfolio | Single row — stock cash balance (starts $1,000,000) |
| paper_positions | Open stock positions (ticker, qty, avg_cost) |
| committee_sessions | Every analysis run (ticker, decision, score, chairman rationale) |
| agent_votes | Each vote per session (action, confidence, rationale, raw data) |
| trades | Executed paper trades (side, qty, filled_price) |
| portfolio_snapshots | Equity curve snapshots every 30 min |
| forex_portfolio | Single row — forex cash balance (starts $1,000,000) |
| forex_positions | Open forex positions (pair, direction, notional_usd, entry_rate, stop_loss) |
| alembic_version | Migration tracking |

committee_sessions and trades are reused for forex with market='FOREX'.

---

## Environment Variables

```
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@db.ysqopwgijjhubarumayq.supabase.co:5432/postgres
FINNHUB_API_KEY=...
FMP_API_KEY=...
DAILY_BUDGET_USD=1.25
COMMITTEE_MAX_TICKERS=30
FRONTEND_URL=https://your-app.vercel.app
ALPHAVANTAGE_API_KEY=...               # present but unused
```

---

## API Endpoints

```
GET  /api/health
GET  /api/portfolio?market=US
GET  /api/stats?market=US
GET  /api/trades?page=1&limit=20&market=US
GET  /api/debates?page=1&limit=20&market=US
POST /api/analyze?ticker=AAPL&market=US
GET  /api/search?q=apple&market=US

GET  /api/forex/portfolio
GET  /api/forex/stats
GET  /api/forex/trades?page=1&limit=20
GET  /api/forex/rates
POST /api/forex/run-committee?pair=EURUSD
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

## Deployment

Railway (backend): uvicorn backend.main:app --host 0.0.0.0 --port $PORT
Vercel (frontend): set VITE_API_URL=https://your-railway-backend.up.railway.app

---

## Important Notes

- yfinance forex tickers use =X suffix: EURUSD=X, USDJPY=X, etc.
- FMP fallback: if FMP key missing or exhausted, fundamentalist.py auto-falls back to yfinance.
- Macro cache: VIX + sector data cached 30 min; forex macro snapshot cached 30 min.
- NaN handling: all forex TA uses _clean_nans() + _safe_float(); yfinance has weekend gaps.
- DB auto-create: Base.metadata.create_all runs on boot; no manual migration needed.
- AlphaVantage key is configured but never called — all indicators computed via pandas.
