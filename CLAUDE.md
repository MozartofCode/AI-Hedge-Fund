# 🧠 AI Hedge Fund — CLAUDE.md

> A multi-agent AI trading committee that debates, votes, and autonomously executes paper trades.
> Built to demonstrate advanced AI orchestration, real-time data pipelines, and modern full-stack engineering.

---

## 📐 Project Overview

**Name:** AI Hedge Fund (working title: `AlphaCommittee`)
**Purpose:** A portfolio project for AI/product/software engineering roles that showcases:
- Multi-agent LLM orchestration with Claude
- Real-time financial data pipelines
- Autonomous trade execution via Alpaca paper trading
- A polished, recruiter-facing live dashboard

**Live Stack:**
- **Backend:** Python + FastAPI — deployed on **Railway**
- **Frontend:** React + Tailwind CSS — deployed on **Vercel**
- **Database:** PostgreSQL (Railway-managed) for trade logs, agent debates, portfolio history
- **Paper Broker:** Alpaca Markets (free paper trading account)
- **Data APIs:** Finnhub (news + sentiment), Alpha Vantage (technicals), Financial Modeling Prep (fundamentals)
- **AI Engine:** Anthropic Claude API (`claude-sonnet-4-20250514`)

---

## 🗂️ Repository Structure

```
alphacommittee/
├── backend/
│   ├── main.py                   # FastAPI app entry point
│   ├── scheduler.py              # APScheduler — triggers committee sessions
│   ├── agents/
│   │   ├── base_agent.py         # Shared Agent class (calls Claude API)
│   │   ├── technician.py         # Agent 1: Technical Analysis
│   │   ├── fundamentalist.py     # Agent 2: Fundamental Analysis
│   │   ├── newshound.py          # Agent 3: News & Sentiment
│   │   ├── macro_watcher.py      # Agent 4: Macro & Sector Rotation
│   │   └── risk_manager.py       # Agent 5: Risk & Portfolio Guard
│   ├── orchestrator.py           # Chairman — collects votes, makes final decision
│   ├── broker/
│   │   └── alpaca_client.py      # Alpaca paper trading API wrapper
│   ├── data/
│   │   ├── finnhub_client.py     # News + sentiment fetcher
│   │   ├── alphavantage_client.py# Technical indicators fetcher
│   │   └── fmp_client.py         # Fundamentals fetcher
│   ├── db/
│   │   ├── models.py             # SQLAlchemy models
│   │   └── crud.py               # DB read/write helpers
│   └── api/
│       ├── portfolio.py          # GET /portfolio — positions + P&L
│       ├── trades.py             # GET /trades — trade history
│       └── debates.py            # GET /debates — committee session logs
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx     # Page 1: Portfolio heatmap
│   │   │   └── Debates.jsx       # Page 2: Committee debate viewer
│   │   ├── components/
│   │   │   ├── Heatmap.jsx       # Treemap/heatmap of holdings
│   │   │   ├── AgentCard.jsx     # Displays agent vote + rationale
│   │   │   ├── TradeLog.jsx      # Recent trades table
│   │   │   └── PortfolioStats.jsx# P&L, win rate, Sharpe ratio
│   │   └── App.jsx
│   ├── package.json
│   └── vite.config.js
├── .env.example
├── requirements.txt
├── README.md
└── CLAUDE.md                     # ← this file
```

---

## 🤖 The 5 Agents — Roles & Data Sources

### Agent 1: The Technician 📈
**Focus:** Price action, momentum, mean reversion
**Data:** Alpaca historical bars (free IEX feed) + Alpha Vantage technical indicators
**Signals it analyzes:**
- RSI (overbought/oversold)
- MACD crossovers
- 50-day / 200-day moving average crossovers (Golden Cross / Death Cross)
- Bollinger Band squeezes
- Volume anomalies

**Output format:**
```json
{
  "agent": "technician",
  "ticker": "NVDA",
  "action": "BUY",
  "confidence": 0.78,
  "rationale": "MACD bullish crossover confirmed. RSI at 52 (neutral, room to run). Price reclaimed 50-day MA after 3-day consolidation.",
  "suggested_position_size_pct": 5
}
```

---

### Agent 2: The Fundamentalist 📊
**Focus:** Company health, valuation, earnings
**Data:** Financial Modeling Prep free tier (250 calls/day)
**Signals it analyzes:**
- P/E ratio vs. sector median
- Revenue growth QoQ / YoY
- Free cash flow positive/negative trend
- Debt-to-equity
- Upcoming earnings date (avoid trading into earnings unless thesis is strong)
- Analyst consensus rating

**Output format:** Same JSON schema as above

---

### Agent 3: The Newshound 📰
**Focus:** News sentiment, market narrative, catalysts
**Data:** Finnhub news API (60 calls/min free) — company news + market news + insider sentiment
**Signals it analyzes:**
- Sentiment score of last 10 news articles for ticker (Finnhub provides this natively)
- Insider buy/sell ratio (Finnhub MSPR score)
- Earnings surprise from last quarter
- Any FDA/regulatory/legal headlines flagged

**Output format:** Same JSON schema as above

---

### Agent 4: The Macro Watcher 🌍
**Focus:** Sector rotation, macro regime, market-wide risk
**Data:** Finnhub economic calendar + Alpha Vantage sector performance
**Signals it analyzes:**
- Upcoming Fed meeting / CPI dates (avoid new positions 2 days before)
- Sector ETF momentum (XLK, XLE, XLF, XLV etc.)
- VIX level (if VIX > 25, reduce conviction scores across all agents by 20%)
- USD strength index trend
- Treasury yield curve shape

**Output format:** Same JSON schema, but may also issue a market-wide **RISK-OFF** flag that the Orchestrator must respect.

---

### Agent 5: The Risk Manager 🛡️
**Focus:** Portfolio protection — this agent NEVER generates buy signals
**Data:** Live Alpaca portfolio positions + trade history from DB
**Rules it enforces:**
- No single position > 10% of portfolio
- No single sector > 30% of portfolio
- Max 3 open positions at a time (MVP scope)
- If portfolio is down > 8% from peak (drawdown), all agents are silenced and only SELL/HOLD votes are valid
- If a ticker already has an open position, block duplicate BUY votes
- Calculates final safe position size (Kelly Criterion simplified)

**Output format:**
```json
{
  "agent": "risk_manager",
  "ticker": "NVDA",
  "veto": false,
  "approved_position_size_pct": 4.5,
  "reason": "Approved. Portfolio exposure at 42%, sector exposure XLK at 18%. Position capped at 4.5% per Kelly.",
  "portfolio_drawdown_pct": -2.1
}
```
If `"veto": true`, the trade is cancelled regardless of other agent votes.

---

## 🏛️ The Orchestrator — Chairman Logic

The Orchestrator is a Claude API call that receives all 5 agent JSON outputs and produces the final decision.

**System prompt philosophy:**
> "You are the Chairman of an AI investment committee. You have received structured analysis from 5 specialized agents. Your job is to weigh their arguments, consider the Risk Manager's constraints, and produce a final trade decision with a clear written rationale that would satisfy a compliance officer."

**Orchestrator inputs:**
- All 5 agent JSON votes
- Current portfolio state
- Current market hours (no trades outside 9:30am–4:00pm ET)

**Orchestrator output:**
```json
{
  "decision": "BUY",
  "ticker": "NVDA",
  "position_size_pct": 4.5,
  "order_type": "market",
  "chairman_rationale": "3 of 4 voting agents recommend BUY with average confidence 0.74. Technical and news signals are aligned. Fundamentals are neutral but not disqualifying. Risk Manager approved with capped sizing. Macro Watcher notes elevated VIX but no RISK-OFF flag. Proceeding.",
  "agent_votes": { ... },
  "session_id": "uuid",
  "timestamp": "2025-05-11T10:32:00Z"
}
```

**Weighted vote scoring:**
| Agent | Vote Weight |
|---|---|
| Technician | 25% |
| Fundamentalist | 20% |
| Newshound | 20% |
| Macro Watcher | 15% |
| Risk Manager | Veto power (blocks regardless of score) |

Weighted score threshold: **≥ 0.60** to trigger a BUY. SELL triggers at ≤ 0.35 on an existing position.

---

## 🔄 Execution Flow

```
Every 30 minutes (market hours only):
  1. scheduler.py triggers a committee session for a watchlist of 10 tickers
  2. For each ticker, all 4 data-gathering agents run IN PARALLEL (asyncio)
  3. Each agent formats its JSON vote via a Claude API call
  4. Risk Manager evaluates current portfolio state
  5. Orchestrator (Chairman) receives all votes → calls Claude API → produces decision
  6. If decision = BUY/SELL → alpaca_client.py submits order to paper-api.alpaca.markets
  7. Full session (all votes + decision + trade result) saved to PostgreSQL
  8. Frontend polls /api/debates and /api/portfolio every 60 seconds
```

**Watchlist (MVP):** AAPL, NVDA, MSFT, TSLA, AMZN, META, GOOGL, JPM, XOM, SPY

---

## 🖥️ Frontend Pages

### Page 1: Portfolio Dashboard (`/`)
**Components:**
- **Portfolio Stats Bar** — Total value, cash remaining, total P&L ($), total P&L (%), win rate, number of trades
- **Holdings Heatmap** — Treemap using `recharts` or `d3`. Each box = one ticker. Size = position value. Color = performance (-10% red → +10% green). Hover shows: ticker, industry, shares held, avg cost, current price, P&L.
- **Sector Exposure Bar** — Horizontal stacked bar showing % allocated per sector
- **Recent Trades Table** — Last 10 trades: ticker, buy/sell, price, time, P&L on closed positions

### Page 2: Committee Debates (`/debates`)
**Components:**
- **Session List** — Scrollable list of all sessions, sorted by most recent. Each row shows: timestamp, ticker analyzed, final decision (BUY/SELL/HOLD), outcome (if trade placed).
- **Session Detail Panel** — Click a session to expand:
  - Chairman rationale (prominent, styled like a verdict)
  - Agent cards: one per agent, showing their vote, confidence score, and full rationale
  - Color-coded: green = BUY vote, red = SELL vote, grey = HOLD/neutral
  - If Risk Manager vetoed, show a red "VETOED" banner

---

## 🗃️ Database Schema (PostgreSQL)

### `committee_sessions`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| ticker | VARCHAR | |
| session_timestamp | TIMESTAMPTZ | |
| decision | VARCHAR | BUY / SELL / HOLD |
| chairman_rationale | TEXT | |
| weighted_score | FLOAT | |
| order_placed | BOOLEAN | |
| order_id | VARCHAR | Alpaca order ID |

### `agent_votes`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| session_id | UUID FK | |
| agent_name | VARCHAR | |
| action | VARCHAR | BUY / SELL / HOLD |
| confidence | FLOAT | 0.0–1.0 |
| rationale | TEXT | |
| raw_data_snapshot | JSONB | The market data that informed this vote |

### `trades`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| session_id | UUID FK | |
| ticker | VARCHAR | |
| side | VARCHAR | buy / sell |
| qty | FLOAT | |
| filled_price | FLOAT | |
| filled_at | TIMESTAMPTZ | |
| alpaca_order_id | VARCHAR | |

### `portfolio_snapshots`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| snapshot_timestamp | TIMESTAMPTZ | |
| total_value | FLOAT | |
| cash | FLOAT | |
| positions | JSONB | Array of {ticker, qty, market_value, unrealized_pl} |

---

## 🔑 Environment Variables

Create a `.env` file from `.env.example`:

```
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Alpaca (Paper Trading)
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Finnhub
FINNHUB_API_KEY=...

# Alpha Vantage
ALPHAVANTAGE_API_KEY=...

# Financial Modeling Prep
FMP_API_KEY=...

# Database
DATABASE_URL=postgresql://...

# App
FRONTEND_URL=https://your-app.vercel.app
```

---

## 📦 Python Dependencies (`requirements.txt`)

```
fastapi
uvicorn
sqlalchemy
asyncpg
alembic
httpx
alpaca-py
finnhub-python
anthropic
apscheduler
python-dotenv
pandas
pytz
```

---

## 🚀 Deployment

### Backend → Railway
1. Connect GitHub repo to Railway
2. Set all env vars in Railway dashboard
3. Set start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
4. Railway auto-provisions PostgreSQL — copy `DATABASE_URL` into env vars

### Frontend → Vercel
1. Connect GitHub repo to Vercel
2. Set `VITE_API_URL=https://your-railway-backend.up.railway.app`
3. Vercel auto-deploys on push to `main`

---

## 🏗️ Build Order (MVP Sequence)

Work through this in order. Do NOT jump ahead.

**Phase 1 — Skeleton (Day 1)**
- [ ] Init FastAPI app, connect to PostgreSQL, run Alembic migrations
- [ ] Create Alpaca client — test placing a paper market order for AAPL
- [ ] Create a single `base_agent.py` that calls Claude API with a stub prompt and returns a vote JSON
- [ ] Verify end-to-end: trigger → agent vote → log to DB → order placed

**Phase 2 — Agents (Day 2)**
- [ ] Build all 5 agents with real data fetchers (Finnhub, Alpha Vantage, FMP, Alpaca bars)
- [ ] Build Orchestrator with weighted vote logic
- [ ] Add APScheduler to run committee every 30 min during market hours
- [ ] Add portfolio snapshot job every 15 min

**Phase 3 — API Layer (Day 3)**
- [ ] `GET /api/portfolio` — current positions, P&L, cash
- [ ] `GET /api/debates` — paginated session list with agent votes
- [ ] `GET /api/trades` — trade history
- [ ] `GET /api/stats` — win rate, Sharpe ratio, total return

**Phase 4 — Frontend (Day 4–5)**
- [ ] React app with React Router (2 pages)
- [ ] Portfolio Dashboard: stats bar + recharts treemap heatmap + trades table
- [ ] Debates page: session list + expandable agent vote cards
- [ ] Auto-refresh every 60 seconds (no websocket needed for MVP)
- [ ] Mobile-responsive layout with Tailwind

**Phase 5 — Polish & Deploy (Day 6)**
- [ ] Deploy backend to Railway
- [ ] Deploy frontend to Vercel
- [ ] Seed DB with 3–5 days of historical sessions (so dashboard isn't empty on recruiter visits)
- [ ] Write a sharp README.md with architecture diagram, live link, and 3-bullet summary

---

## 💡 Resume & Recruiter Talking Points

When describing this project in interviews or on your resume, lead with these:

> **"Built a multi-agent LLM system where 5 specialized Claude agents analyze stocks from different perspectives — technical, fundamental, sentiment, macro, and risk — then a Chairman orchestrator weighs their votes and autonomously executes paper trades via the Alpaca API."**

**What impresses AI engineers:**
- Parallel async agent execution (not sequential)
- Structured JSON output from each Claude call (prompt engineering)
- Weighted voting system with veto logic — not just "ask Claude what to do"
- Clean separation of concerns: each agent has one job

**What impresses product engineers:**
- Real user-facing product with two polished pages
- Live deployment recruiter can click and interact with
- Auto-refreshing data, not static screenshots

**What impresses software engineers:**
- FastAPI async backend with proper DB schema
- APScheduler for cron-like autonomous operation
- PostgreSQL with JSONB for flexible agent data
- Clean repo structure, env management, Railway/Vercel deploy

---

## ⚠️ Important Notes for Claude Code

- **Always use `paper-api.alpaca.markets`** — never `api.alpaca.markets`. Real money is not involved.
- **Rate limit guard:** Add a `time.sleep(1)` between Finnhub calls when processing multiple tickers. Free tier is 60/min but can spike.
- **Market hours check:** Wrap all order submission in a check — Alpaca will reject orders outside 9:30am–4:00pm ET. Use `pytz` for timezone handling.
- **Claude API calls:** Each agent call should use `max_tokens=500` — responses are structured JSON, not essays. This keeps costs low.
- **Error handling on agent failures:** If one agent's data fetch fails, it should return a `HOLD` vote with `confidence: 0.0` rather than crashing the session.
- **No hardcoded API keys** — always read from environment variables via `python-dotenv`.
- **Database migrations:** Use Alembic. Never alter schema by hand.
- **CORS:** FastAPI backend must allow `FRONTEND_URL` origin for the Vercel frontend to call it.
