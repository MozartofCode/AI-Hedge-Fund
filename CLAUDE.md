# 🏛️ AlphaCommittee — CLAUDE.md

> A multi-agent AI hedge fund that debates, votes, and autonomously executes paper trades.
> 5 specialized Claude agents analyze every stock, a Chairman orchestrates the final decision,
> and the system trades with $1,000,000 of paper money — no brokerage account needed.

---

## 📐 Project Overview

**Name:** AlphaCommittee
**Purpose:** Portfolio project showcasing multi-agent LLM orchestration, real-time financial data pipelines, and autonomous trade execution.

**Live Stack:**
- **Backend:** Python + FastAPI + APScheduler (auto-trades at 10am / 12:30pm / 3pm ET)
- **Frontend:** React 18 + Tailwind CSS + Recharts — 3 pages
- **Database:** PostgreSQL on **Supabase** (free tier, project: "AI Investor")
- **Paper Broker:** Self-contained — yfinance prices + PostgreSQL positions (no brokerage account)
- **Data APIs:** yfinance (free), Finnhub (news), Financial Modeling Prep (fundamentals)
- **AI Engine:** Anthropic Claude API (`claude-sonnet-4-6`, max_tokens=500)
- **Note:** AlphaVantage key is configured but **not used** — all technical indicators are calculated locally from yfinance data via pandas

---

## 🗂️ Repository Structure

```
AI-Hedge-Fund/
├── backend/
│   ├── main.py                    # FastAPI app, lifespan startup, /api/analyze endpoint
│   ├── scheduler.py               # APScheduler — 3 sessions/day at 10am/12:30pm/3pm ET
│   ├── orchestrator.py            # Chairman logic + analyze_ticker() for on-demand analysis
│   ├── agents/
│   │   ├── base_agent.py          # call_claude() helper shared by all agents
│   │   ├── technician.py          # Agent 1: Technical Analysis (yfinance + pandas)
│   │   ├── fundamentalist.py      # Agent 2: Fundamental Analysis (FMP)
│   │   ├── newshound.py           # Agent 3: News & Sentiment (Finnhub)
│   │   ├── macro_watcher.py       # Agent 4: Macro & Sector Rotation (yfinance + Finnhub, cached)
│   │   └── risk_manager.py        # Agent 5: Risk Guard (pure logic, no API calls)
│   ├── broker/
│   │   └── paper_broker.py        # Self-contained paper trading: yfinance prices + DB positions
│   ├── data/
│   │   ├── indicators.py          # RSI / MACD / SMA / BBands calculated from pandas Series
│   │   ├── finnhub_client.py      # News, sentiment, insider data, economic calendar
│   │   ├── alphavantage_client.py # Present but unused — indicators computed locally now
│   │   └── fmp_client.py          # P/E, revenue, balance sheet, analyst ratings
│   ├── db/
│   │   ├── models.py              # SQLAlchemy ORM models (6 tables)
│   │   ├── crud.py                # Async DB helpers + compute_win_rate() FIFO matching
│   │   └── session.py             # AsyncSessionLocal + engine setup
│   └── api/
│       ├── portfolio.py           # GET /api/portfolio — live positions + P&L
│       ├── trades.py              # GET /api/trades — paginated trade history
│       ├── debates.py             # GET /api/debates — committee session logs
│       └── stats.py               # GET /api/stats — win rate, Sharpe ratio, equity curve
├── alembic/
│   └── versions/
│       ├── 0001_initial_schema.py # committee_sessions, agent_votes, trades, portfolio_snapshots
│       └── 0002_paper_trading.py  # paper_portfolio, paper_positions, rename alpaca_order_id→order_id
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Portfolio.jsx      # Page 1: Hero heatmap + stats + equity curve
│       │   ├── Trades.jsx         # Page 2: Full trade history grid with BUY/SELL filter
│       │   └── Analyze.jsx        # Page 3: Search bar → live 5-agent analysis
│       ├── components/
│       │   └── AgentCard.jsx      # Reusable agent vote card (confidence bar + rationale)
│       ├── api.js                 # Fetch helpers for all backend endpoints
│       └── App.jsx                # Router + 3-item nav + market open/closed badge
├── .env                           # Never committed (gitignored)
├── .env.example
├── requirements.txt
├── alembic.ini
└── CLAUDE.md                      # ← this file
```

---

## 🤖 The 5 Agents

### Agent 1 — The Technician 📈
**Data:** yfinance OHLCV (250 days) → indicators calculated locally with pandas  
**No API key needed — completely free and unlimited**

Signals:
- RSI 14 (overbought >70, oversold <30)
- MACD line vs signal crossover + histogram
- SMA 50 vs SMA 200 (Golden Cross / Death Cross)
- Bollinger Bands (squeeze / breakout)
- Recent 5-bar price action + volume

---

### Agent 2 — The Fundamentalist 📊
**Data:** Financial Modeling Prep free tier (250 calls/day)

Signals:
- P/E ratio vs sector
- Revenue growth QoQ
- Free cash flow trend (4 quarters)
- Debt-to-equity
- Analyst buy/hold/sell consensus
- Days until next earnings (risk flag if < 2 days)

---

### Agent 3 — The Newshound 📰
**Data:** Finnhub free tier (60 calls/min)

Signals:
- Company news sentiment score
- Sector average bullish %
- Article buzz intensity
- Top 5 recent headlines
- Insider MSPR score (-1 to +1, positive = insiders buying)
- Last quarter earnings surprise %

---

### Agent 4 — The Macro Watcher 🌍
**Data:** yfinance (^VIX + 10 sector ETFs) + Finnhub economic calendar  
**Results cached 30 minutes** — fetched once per session, not once per ticker

Signals:
- VIX level (>25 triggers risk-off, reduces all confidence scores by 20%)
- 1-day % return for 10 sector ETFs (XLK, XLV, XLE, XLF, XLY, XLP, XLI, XLU, XLB, XLRE)
- Upcoming high/medium-impact US macro events (Fed, CPI, NFP)

**Special flag:** `"risk_off": true` — when set, all agent confidence scores are multiplied by 0.80 in the weighted scoring.

---

### Agent 5 — The Risk Manager 🛡️
**Data:** Portfolio passed in from orchestrator — no external API calls, no Claude call  
**Pure deterministic logic only**

Rules enforced (in order):
1. If portfolio drawdown ≥ 8% from peak → veto ALL new BUYs until recovery
2. If ticker already has an open position → block duplicate BUY
3. If open positions ≥ 3 → block new BUYs (max positions reached)
4. If approved → position size = min(5%, 10%) = 5% of portfolio value

**Output:**
```json
{
  "agent": "risk_manager",
  "veto": false,
  "approved_position_size_pct": 5.0,
  "reason": "Approved. Portfolio exposure 12.3%, 1/3 positions open. Drawdown 0.0%.",
  "portfolio_drawdown_pct": 0.0
}
```
If `"veto": true`, the trade is cancelled regardless of all other agent votes.

---

## 🏛️ The Orchestrator & Chairman

**Weighted scoring:**
| Agent | Weight |
|---|---|
| Technician | 25% |
| Fundamentalist | 20% |
| Newshound | 20% |
| Macro Watcher | 15% |
| *(Risk Manager has veto power, not a weighted vote)* | — |

BUY threshold: **score ≥ 0.60**  
SELL threshold: **score ≤ 0.35** (only if ticker already held)

**Two orchestration modes:**
1. `run_committee_for_ticker()` — full session: saves to DB, places real paper orders
2. `analyze_ticker()` — analysis only: no DB write, no order, works when market is closed

---

## 🔄 Execution Flow

```
Automatic (Mon–Fri at 10:00am, 12:30pm, 3:00pm ET):
  1. scheduler.py fires _committee_job()
  2. Checks is_market_open() — skips if market closed
  3. Fetches live portfolio from paper_broker.py (yfinance prices + DB positions)
  4. For each of 10 watchlist tickers:
       a. 4 data agents run IN PARALLEL via asyncio.gather()
       b. Risk Manager evaluates portfolio state
       c. Chairman (Claude) receives all votes → produces final decision
       d. If BUY/SELL and market open → paper_broker.place_order() executes trade
       e. Full session saved to PostgreSQL (committee_sessions + agent_votes + trades)
  5. Portfolio snapshot saved to portfolio_snapshots table

On-demand (Analyze page):
  1. User types ticker + clicks "Run Analysis"
  2. POST /api/analyze → analyze_ticker()
  3. Same 5-agent logic but NO order placement, NO DB write
  4. Returns full agent votes + chairman verdict to frontend
```

**Watchlist:** AAPL, NVDA, MSFT, TSLA, AMZN, META, GOOGL, JPM, XOM, SPY

---

## 🖥️ Frontend Pages

### Page 1 — Portfolio (`/`)
- Stats strip: Total Value, Cash, Total P&L (+%), Win Rate, Sharpe Ratio, Total Trades
- **Hero heatmap** (Recharts Treemap): tile size = position market value, color = unrealized P&L % (dark red → dark green). Hover tooltip shows full position details.
- Equity curve (LineChart): daily portfolio value from snapshots table
- Auto-refreshes every 60s, manual Refresh button

### Page 2 — Trades (`/trades`)
- Full paginated table of all executed trades
- Filter tabs: All / BUY / SELL
- Columns: Ticker, Side, Price, Qty, Total Value, Order ID, Time

### Page 3 — Analyze (`/analyze`)
- Search bar + 10 quick-pick buttons for watchlist tickers
- Step-by-step loading animation (6 steps matching agent pipeline)
- Verdict banner: BUY/SELL/HOLD with weighted score + chairman rationale
- 5 agent cards grid with confidence bars and full rationale text
- Works when market is closed — analysis only, no order placed

---

## 🗃️ Database Schema (PostgreSQL on Supabase)

### `paper_portfolio` — single row, tracks cash balance
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | Always = 1 |
| cash | FLOAT | Starts at $1,000,000 |
| updated_at | TIMESTAMPTZ | |

### `paper_positions` — one row per open position
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| ticker | VARCHAR(10) UNIQUE | |
| qty | FLOAT | Fractional shares allowed |
| avg_cost | FLOAT | Average fill price |
| opened_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### `committee_sessions`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| ticker | VARCHAR(10) | |
| session_timestamp | TIMESTAMPTZ | |
| decision | VARCHAR(10) | BUY / SELL / HOLD |
| chairman_rationale | TEXT | |
| weighted_score | FLOAT | |
| order_placed | BOOLEAN | |
| order_id | VARCHAR(100) | paper-{hex} |

### `agent_votes`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| session_id | UUID FK → committee_sessions | |
| agent_name | VARCHAR(50) | |
| action | VARCHAR(10) | BUY / SELL / HOLD |
| confidence | FLOAT | 0.0–1.0 |
| rationale | TEXT | |
| raw_data_snapshot | JSONB | Full market data used for this vote |

### `trades`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| session_id | UUID FK → committee_sessions | |
| ticker | VARCHAR(10) | |
| side | VARCHAR(10) | buy / sell |
| qty | FLOAT | |
| filled_price | FLOAT | yfinance last_price at order time |
| filled_at | TIMESTAMPTZ | |
| order_id | VARCHAR(100) | paper-{hex} |

### `portfolio_snapshots` — equity curve history
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| snapshot_timestamp | TIMESTAMPTZ | Every 30 min during market hours |
| total_value | FLOAT | cash + sum(positions market value) |
| cash | FLOAT | |
| positions | JSONB | Array of enriched position objects |

---

## 🔑 Environment Variables

```env
ANTHROPIC_API_KEY=sk-ant-...          # Claude API — all 5 agents + chairman

ALPHAVANTAGE_API_KEY=...              # Configured but currently unused
                                       # (indicators calculated from yfinance)

FINNHUB_API_KEY=...                   # News, sentiment, economic calendar
                                       # Free tier: 60 calls/min

FMP_API_KEY=...                       # Fundamentals — P/E, revenue, balance sheet
                                       # Free tier: 250 calls/day

DATABASE_URL=postgresql+asyncpg://... # Must use +asyncpg driver prefix
                                       # Supabase: postgresql+asyncpg://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres

FRONTEND_URL=http://localhost:5173    # CORS origin (change to Vercel URL when deployed)
```

---

## 📊 API Call Budget (Per Day)

3 committee sessions × 10 tickers each:

| Service | Calls/Day | Free Limit | Cost |
|---|---|---|---|
| **yfinance** | Unlimited | Free forever | $0 |
| **AlphaVantage** | 0 | 25/day | $0 |
| **FMP** | ~180 | 250/day ✅ | $0 |
| **Finnhub** | ~30 (cached) | 60/min ✅ | $0 |
| **Anthropic** | ~150 | Paid | ~$0.45/day (~$13/month) |

**Why 150 Anthropic calls?**
- 5 agents per ticker × 10 tickers × 3 sessions = 150
- The 4 data agents (Technician, Fundamentalist, Newshound, Macro Watcher) each make 1 Claude call to interpret their data
- The Chairman makes 1 Claude call to synthesize the votes into a final decision
- Each call uses `max_tokens=500` (structured JSON, not essays) — kept intentionally small
- Each Analyze page search = 5 more Claude calls (one-off, on demand)
- At claude-sonnet-4-6 pricing (~$0.003/call) = ~$0.45/day

---

## 🚀 Running Locally

**1. Install dependencies:**
```bash
pip install -r requirements.txt
```

**2. Start the backend:**
```bash
uvicorn backend.main:app --reload
```
You should see:
```
Scheduler started — committee at 10:00am / 12:30pm / 3:00pm ET (Mon–Fri)
INFO: Uvicorn running on http://127.0.0.1:8000
```

**3. Start the frontend (separate terminal):**
```bash
cd frontend && npm run dev
```
Opens at http://localhost:5173

**Do you need to deploy for automation to work?**
**No.** The scheduler runs inside the FastAPI process. As long as `uvicorn` is running on your machine, the committee will auto-trade at 10am/12:30pm/3pm ET every weekday. Vercel/Railway deployment is only needed if you want the app accessible from other devices or to keep it running 24/7 without your laptop.

---

## 🚀 Deployment (Optional)

### Backend → Railway
```
Start command: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```
Set all env vars in Railway dashboard. Use Supabase DATABASE_URL (Railway-managed Postgres also works).

### Frontend → Vercel
Set env var: `VITE_API_URL=https://your-railway-backend.up.railway.app`
Vercel auto-deploys on push to `main`.

---

## ⚠️ Important Notes for Claude Code

- **Paper broker is self-contained** — no brokerage account needed. `paper_broker.py` uses yfinance for prices and PostgreSQL for positions/cash. Starting balance: $1,000,000.
- **Migrations already applied** — tables were created directly in Supabase via MCP. If re-running on a fresh DB, run `alembic upgrade head`.
- **AlphaVantage not used** — the key is in `.env` but all technical indicators (RSI, MACD, SMA, BBands) are calculated locally in `backend/data/indicators.py` using pandas. Zero API calls needed.
- **Macro cache** — `macro_watcher.py` caches VIX + sector data for 30 minutes. This means all 10 tickers in a session share one set of macro data. Cache resets between sessions automatically.
- **Risk Manager never calls Claude** — it's deterministic Python logic only. This saves 10 Claude calls per session (one per ticker).
- **Market hours:** `is_market_open()` checks 9:30am–4:00pm ET, Mon–Fri. Orders are only placed during this window.
- **Error handling:** Every agent wraps its data fetch in try/except and returns `HOLD, confidence=0.0` on failure — a single bad API call never crashes the session.
- **No hardcoded keys** — always read from `.env` via `python-dotenv`.
- **CORS** — backend allows `FRONTEND_URL` origin. Update this env var when deploying.
