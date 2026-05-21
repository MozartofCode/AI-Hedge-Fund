# 🏛️ AlphaCommittee — AI Hedge Fund

> 5 specialized AI agents debate every stock. A Chairman orchestrates the final vote. The system trades autonomously with $1M of paper money — no brokerage account required.

---

## What It Does

AlphaCommittee runs a simulated investment committee 3 times every trading day. For each of 10 watchlist stocks, five Claude-powered agents independently analyze the ticker from different angles, cast a weighted vote, and a Chairman agent synthesizes them into a final BUY / SELL / HOLD decision. If the market is open and the score clears the threshold, the trade executes automatically.

**The 5 agents:**
| Agent | Role | Data Source |
|---|---|---|
| 📈 Technician | RSI, MACD, SMA, Bollinger Bands | yfinance + pandas (free) |
| 📊 Fundamentalist | P/E, revenue growth, FCF, analyst ratings | Financial Modeling Prep |
| 📰 Newshound | News sentiment, insider buying, earnings surprise | Finnhub |
| 🌍 Macro Watcher | VIX, sector rotation, Fed/CPI calendar | yfinance + Finnhub |
| 🛡️ Risk Manager | Drawdown guard, position limits, duplicate check | Pure logic (no API) |

---

## Tech Stack

- **Backend:** Python · FastAPI · APScheduler · SQLAlchemy async
- **Database:** PostgreSQL (Supabase)
- **Prices:** yfinance (free, no API key)
- **AI:** Anthropic Claude (`claude-sonnet-4-6`)
- **Frontend:** React 18 · Tailwind CSS · Recharts · Vite

---

## Frontend (3 Pages)

**Portfolio** — Live heatmap where tile size = position value and color = unrealized P&L. Auto-refreshes from the API every 60 seconds.

**Trades** — Full paginated history of every buy and sell with BUY/SELL filter tabs.

**Analyze** — Type any ticker and get a live 5-agent analysis with step-by-step progress, a verdict banner, and individual agent cards showing confidence and rationale.

---

## Running Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt
cd frontend && npm install

# 2. Create .env (see .env.example)
# Required: ANTHROPIC_API_KEY, FINNHUB_API_KEY, FMP_API_KEY, DATABASE_URL

# 3. Run backend (auto-trades at 10am / 12:30pm / 3pm ET on weekdays)
uvicorn backend.main:app --reload

# 4. Run frontend
cd frontend && npm run dev
# → http://localhost:5173
```

No deployment needed for automation — the scheduler runs inside the FastAPI process.

---

## API Cost

~$0.45/day (~$13/month) for Anthropic. All other data sources are free.
