# 🏛️ AlphaCommittee — AI Hedge Fund

> 5 specialized AI agents debate every stock. A Chairman orchestrates the final vote. The system trades autonomously with $1M of paper money — no brokerage account required.

---

## Live Demo

- **Frontend:** [ai-hedge-fund-liart.vercel.app](https://ai-hedge-fund-liart.vercel.app)
- **Backend:** [web-production-71c39.up.railway.app](https://web-production-71c39.up.railway.app)

---

## What It Does

AlphaCommittee runs a simulated investment committee 3 times every trading day. For each of 10 watchlist stocks, five Claude-powered agents independently analyze the ticker from different angles, cast a weighted vote, and a Chairman agent synthesizes them into a final BUY / SELL / HOLD decision. If the market is open and the score clears the threshold, the trade executes automatically — and a Slack alert fires instantly.

**The 5 agents:**
| Agent | Role | Signals |
|---|---|---|
| 📈 Technician | Price action & momentum | RSI, MACD, SMA50/200, Bollinger Bands, ATR, volume ratio, 52-week high/low |
| 📊 Fundamentalist | Company health & valuation | P/E, P/FCF, gross margin, revenue growth, FCF trend, D/E, analyst ratings |
| 📰 Newshound | News, sentiment & catalysts | News sentiment score, insider MSPR, earnings surprise, analyst upgrades/downgrades, article volume |
| 🌍 Macro Watcher | Market-wide risk | VIX, yield curve (10Y−3M), USD strength, sector rotation, Fed/CPI calendar |
| 🛡️ Risk Manager | Portfolio guardrails | Drawdown guard, position limits, duplicate check, sector concentration limit |

**The Chairman** receives all 5 votes plus current portfolio context (cash, open positions) and produces the final decision with a written rationale.

---

## Tech Stack

- **Backend:** Python · FastAPI · APScheduler · SQLAlchemy async
- **Database:** PostgreSQL (Supabase)
- **Prices:** yfinance (free, no API key)
- **AI:** Anthropic Claude (`claude-sonnet-4-6`)
- **Notifications:** Slack Web API (trade alerts → `#stock-market-news`)
- **Frontend:** React 18 · Tailwind CSS · Recharts · Vite
- **Backend Hosting:** Railway (auto-deploys from `main`, runs scheduler 24/7)
- **Frontend Hosting:** Vercel (auto-deploys from `main`)

---

## Frontend (3 Pages)

**Portfolio** — Live heatmap where tile size = position value and color = unrealized P&L. Auto-refreshes every 60 seconds with live prices.

**Trades** — Full paginated history of every buy and sell. Click any row to open a popup showing the full 5-agent committee logic and Chairman rationale behind that trade.

**Analyze** — Type any ticker and get a live 5-agent analysis with step-by-step progress, a verdict banner, and individual agent cards showing confidence bars and rationale.

---

## Slack Alerts

Every BUY and SELL posts automatically to `#stock-market-news`:

```
🟢 BOUGHT 62 shares of AAPL @ $185.32
💰 Total: $11,489.84  |  Conviction score: 0.72

🏛️ Chairman's reasoning:
> Apple's RSI at 58 with a MACD crossover, growing FCF, and calm
> macro conditions (VIX 14, yield curve positive) justify entry.

📊 Agent votes:
  • 📈 Technician: BUY 85% ████████░░
  • 📊 Fundamentalist: BUY 72% ███████░░░
  • 📰 Newshound: HOLD 55% █████░░░░░
  • 🌍 Macro Watcher: BUY 68% ██████░░░░
  • 🛡️ Risk Manager: ✅ Approved
```

Requires `SLACK_BOT_TOKEN` in Railway env vars (see Deployment section).

---

## Running Locally

```bash
# 1. Install dependencies
pip install -r requirements.txt
cd frontend && npm install

# 2. Create .env (see .env.example)
# Required: ANTHROPIC_API_KEY, FINNHUB_API_KEY, FMP_API_KEY, DATABASE_URL
# Optional: SLACK_BOT_TOKEN (trade alerts), FRONTEND_URL (CORS)

# 3. Run backend (auto-trades at 10am / 12:30pm / 3pm ET on weekdays)
uvicorn backend.main:app --reload

# 4. Run frontend
cd frontend && npm run dev
# → http://localhost:5173
```

---

## Deployment

### Backend → Railway

The backend runs on Railway and handles all automation. The APScheduler fires committee sessions at **10:00am, 12:30pm, and 3:00pm ET (Mon–Fri)** without any cron job or separate worker.

**Setup:**
1. Create a new Railway project and connect your GitHub repo
2. Railway auto-detects the `railway.toml` and uses nixpacks to build
3. Set these environment variables in Railway → Variables:

```
ANTHROPIC_API_KEY=sk-ant-...
FINNHUB_API_KEY=...
FMP_API_KEY=...
DATABASE_URL=postgresql+asyncpg://postgres.PROJECT_REF:PASSWORD@aws-1-REGION.pooler.supabase.com:5432/postgres
FRONTEND_URL=https://your-vercel-app.vercel.app
SLACK_BOT_TOKEN=xoxb-...          # optional — enables trade alerts in #stock-market-news
```

> **Important:** Use Supabase's **Session Pooler** URL (not the direct connection URL).
> The direct connection is IPv6-only; Railway is IPv4-only. Get the pooler URL from
> Supabase → Connect → Session pooler. Use port `5432` on `aws-1-*.pooler.supabase.com`.

4. Railway generates a public domain under Settings → Networking

#### Slack Bot Setup (optional)
1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → From scratch
2. Under **OAuth & Permissions** → add Bot Token Scope: `chat:write`
3. **Install to Workspace** → copy the `xoxb-...` token
4. In Slack, run `/invite @YourBotName` in `#stock-market-news`
5. Add `SLACK_BOT_TOKEN` to Railway Variables — Railway will redeploy automatically

### Frontend → Vercel
1. Import the GitHub repo in Vercel
2. Set **Root Directory** to `frontend`
3. Framework preset: **Vite** (auto-detected)
4. Add environment variable:
```
VITE_API_URL=https://your-railway-app.up.railway.app
```
5. Deploy — Vercel auto-redeploys on every push to `main`

### Database → Supabase
Tables are created automatically on first startup. For a fresh database:
```bash
alembic upgrade head
```

---

## Agent Signal Reference

### 📈 Technician
| Signal | Interpretation |
|---|---|
| RSI < 30 | Oversold → bullish |
| RSI > 70 | Overbought → bearish |
| MACD histogram turning positive | Momentum building → bullish |
| Price within 3% of 52w high + volume spike | Breakout signal → bullish |
| Volume ratio > 1.3× | Confirms the move; low-volume signals are discounted |
| ATR % of price | High = volatile, reduce position size confidence |

### 📊 Fundamentalist
| Signal | Interpretation |
|---|---|
| P/FCF < 20 | Healthy valuation |
| P/FCF > 40 | Expensive |
| Gross margin > 50% | Pricing power / moat |
| Revenue growth > 10% QoQ | Growth company |
| Earnings within 2 days | Avoid new positions |

### 🌍 Macro Watcher
| Signal | Interpretation |
|---|---|
| VIX > 25 | Risk-off — all confidence scores cut 20% |
| Yield curve inverted (10Y−3M < 0) | Recession signal → risk-off |
| USD +1% in a week | Equity headwind |
| High-impact event within 2 days | Risk-off |

### 🛡️ Risk Manager (hard rules, no Claude)
| Rule | Limit |
|---|---|
| Max open positions | 3 |
| Max single position | 10% of portfolio |
| Max drawdown before blocking BUYs | −8% |
| Max positions in the same sector | 2 |

---

## API Cost

~$0.45/day (~$13/month) for Anthropic. All other data sources are free.
