# 🏛️ AlphaCommittee — AI Hedge Fund

> 5 specialized AI agents debate every stock. A Chairman synthesizes the final vote. The system trades autonomously with paper money across 5 global markets — no brokerage account required.

**Live Demo:** [ai-hedge-fund-liart.vercel.app](https://ai-hedge-fund-liart.vercel.app)

---

## Investment Thesis

AlphaCommittee hunts for stocks in a Stage 2 uptrend — where price is above a rising 200-day moving average, fundamental momentum is accelerating, and news sentiment is turning positive — the exact trifecta that historically precedes the largest market moves. Five specialized AI agents analyze every stock simultaneously from different angles (price action, financials, news, macro, and risk), then a Chairman synthesizes their votes into a conviction-weighted BUY / SELL / HOLD with price targets. The edge is consistency: the committee runs three times a day, never gets emotional, never ignores a signal, and operates across five global markets — US, Brazil, Argentina, Turkey, and Nigeria.

---

## What It Does

AlphaCommittee runs an autonomous investment committee 3× per trading day. For each stock in the watchlist, five Claude-powered agents independently analyze the ticker from different angles, cast a weighted vote, and the Chairman produces a final decision with a plain-English rationale, 1-month / 6-month / 1-year price targets, and a stop-loss level. When the market is open and the conviction score clears the threshold, the trade executes automatically against a $1M paper portfolio.

### The 5 Agents

| Agent | Role | Key Signals |
|---|---|---|
| 📈 **Technician** | Price action & momentum | RSI, MACD, SMA50/200, Stage 2 uptrend, ATR expansion, volume conviction, relative strength vs SPY |
| 📊 **Fundamentalist** | Company health & valuation | Revenue acceleration, EPS inflection, FCF turn, gross margin expansion, P/FCF, analyst targets |
| 📰 **Newshound** | News, sentiment & catalysts | Consecutive earnings beats, insider sentiment, analyst revisions, squeeze risk score, days-to-cover |
| 🌍 **Macro Watcher** | Market-wide conditions | VIX, yield curve, 10Y rate regime, SPY trend, sector rotation, Fed/CPI calendar |
| 🛡️ **Risk Manager** | Portfolio guardrails | Drawdown guard, stop-loss trigger (−8%), profit target (+75%), position limits, sector concentration |

### The Chairman

Receives all 5 votes plus current portfolio context (cash, open positions, drawdown) and produces:
- **BUY / SELL / HOLD** verdict with conviction score
- **3 plain-English bullets** — why, risk, and what to watch
- **Price targets** for 1 month, 6 months, and 1 year
- **Stop-loss level** — the exact price to exit

---

## Markets

The committee runs independently for 5 exchanges, each with its own paper portfolio, watchlist, trading hours, and currency:

| Market | Exchange | Currency | Starting Capital | Trading Hours (local) |
|---|---|---|---|---|
| 🇺🇸 US | NYSE / NASDAQ | USD | $1,000,000 | 10:00, 12:30, 15:00 ET |
| 🇧🇷 Brazil | B3 | BRL | R$5,000,000 | 11:00, 13:30, 16:00 BRT |
| 🇦🇷 Argentina | BYMA / ADRs | USD | $500,000 | 12:00, 14:00, 16:30 ART |
| 🇹🇷 Turkey | BIST | TRY | ₺30,000,000 | 10:30, 13:00, 16:30 TRT |
| 🇳🇬 Nigeria | NGX | NGN | ₦500,000,000 | 11:00, 12:30, 13:30 WAT |

Slack notifications are US-only. All other markets trade silently.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python · FastAPI · APScheduler · SQLAlchemy async |
| Database | PostgreSQL (Supabase) |
| Price Data | yfinance (free, global — `.SA` Brazil, `.IS` Turkey, `.LG` Nigeria) |
| Financials | FMP (Financial Modeling Prep API) |
| News & Sentiment | Finnhub API |
| AI | Anthropic Claude `claude-sonnet-4-6` |
| Notifications | Slack Web API (US trades only) |
| Frontend | React 18 · Tailwind CSS · Recharts · Vite |
| Backend Hosting | Railway (auto-deploys, runs scheduler 24/7) |
| Frontend Hosting | Vercel (auto-deploys on push to `main`) |

---

## Frontend

Everything lives in a single Portfolio view — no navigation bar.

**Top bar** — Market dropdown (🇺🇸🇧🇷🇦🇷🇹🇷🇳🇬), open/closed status indicator, 🔬 Analyze button, Refresh.

**Stats strip** — Portfolio value · Cash · Total P&L · Total trades (live-updated per market).

**Holdings tab** — Heatmap treemap where tile size = position value, color = unrealized P&L (green/red). Click any tile to see the latest committee session behind that position.

**Trades tab** — Paginated history of every buy and sell. Click any row for the full 5-agent breakdown.

**Analyze panel** (🔬 button) — Type any ticker and run a live on-demand analysis. Shows:
- Chairman verdict card with 3-bullet rationale
- Price targets grid (1m / 6m / 1y) with % from current price
- Stop-loss level
- Collapsible agent breakdown (each agent's 1-line signal)

---

## Slack Alerts (US only)

Every US BUY and SELL posts automatically to `#stock-market-news`:

```
🟢 BOUGHT 62 shares of AAPL @ $185.32
💰 Total: $11,489.84  |  Conviction score: 0.72

🏛️ Chairman's reasoning:
• 📈 Why: Price broke above its 200-day average on high volume — uptrend confirmed.
• ⚠️ Risk: Earnings in 3 weeks could reset the move if guidance disappoints.
• 👀 Watch: Hold above $182 — that's the key support level.

📊 Agent votes:
  • 📈 Technician: BUY 85%
  • 📊 Fundamentalist: BUY 72%
  • 📰 Newshound: HOLD 55%
  • 🌍 Macro Watcher: BUY 68%
  • 🛡️ Risk Manager: ✅ Approved
```

---

## Running Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt
cd frontend && npm install

# 2. Create .env (see .env.example)
# Required: ANTHROPIC_API_KEY, FINNHUB_API_KEY, FMP_API_KEY, DATABASE_URL
# Optional: SLACK_BOT_TOKEN, FRONTEND_URL

# 3. Run backend (auto-trades on market schedule — see Markets table above)
uvicorn backend.main:app --reload

# 4. Run frontend
cd frontend && npm run dev
# → http://localhost:5173
```

---

## Deployment

### Backend → Railway

1. Create a Railway project and connect your GitHub repo
2. Railway auto-detects `railway.toml` and builds with nixpacks
3. Set environment variables in Railway → Variables:

```
ANTHROPIC_API_KEY=sk-ant-...
FINNHUB_API_KEY=...
FMP_API_KEY=...
DATABASE_URL=postgresql+asyncpg://postgres.PROJECT_REF:PASSWORD@aws-1-REGION.pooler.supabase.com:5432/postgres
FRONTEND_URL=https://your-vercel-app.vercel.app
SLACK_BOT_TOKEN=xoxb-...          # optional — US trade alerts only
```

> **Database URL:** Use Supabase's **Session Pooler** URL (not direct connection).
> Direct connection is IPv6-only; Railway is IPv4-only. Get the pooler URL from
> Supabase → Connect → Session pooler, port `5432`.

4. Railway generates a public domain under Settings → Networking

#### Slack Bot Setup (optional)
1. [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → From scratch
2. **OAuth & Permissions** → add Bot Token Scope: `chat:write`
3. **Install to Workspace** → copy the `xoxb-...` token
4. In Slack: `/invite @YourBotName` in `#stock-market-news`
5. Add `SLACK_BOT_TOKEN` to Railway Variables

### Frontend → Vercel
1. Import the GitHub repo in Vercel
2. Set **Root Directory** to `frontend`
3. Framework: **Vite** (auto-detected)
4. Add environment variable: `VITE_API_URL=https://your-railway-app.up.railway.app`
5. Deploy — auto-redeploys on every push to `main`

### Database → Supabase
Tables are created automatically on first startup (`Base.metadata.create_all`).
Paper portfolio rows for all 5 markets are seeded idempotently on every boot.

---

## Risk Manager Rules

| Rule | Limit |
|---|---|
| Max open positions | 10 |
| Max single position size | 12% of portfolio |
| Stop-loss trigger | −8% from entry |
| Profit target (take partial) | +75% |
| Max drawdown before blocking BUYs | −12% |
| Max positions in same sector | 3 |

---

## API Cost Estimate

| Service | Cost |
|---|---|
| Anthropic Claude | ~$0.50/day (~$15/month) |
| Finnhub | Free tier |
| FMP | Free tier |
| yfinance | Free |
| Railway | ~$5/month |
| Vercel | Free |
| Supabase | Free tier |

**Total: ~$20/month** to run the full system across all 5 markets.
