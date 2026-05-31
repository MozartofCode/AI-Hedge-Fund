# AI Hedge Fund

An autonomous paper trading system powered by Claude AI. AI agents independently analyze
stocks and currency pairs, debate the evidence, and execute paper trades — starting with
$1,000,000 and no brokerage account needed.

---

## What It Does

**Stock Portfolio** — Five AI analysts each study a different angle of a stock (its price
chart, financial health, recent news, the overall economy, and risk) then each votes to
buy, sell, or hold. A Chairman AI reads all five opinions and makes the final call, like a
group of advisors debating before a boss decides.

**Forex Trading** — The system trades 10 currency pairs by finding currencies where one
country pays a much higher interest rate than the other — simply holding the higher-rate
currency earns money over time, the way a savings account earns interest. It also checks
price momentum and global economic signals, with automatic stop-losses so no single bad
trade can blow up the account.

---

## Architecture

```
                    ┌─────────────────────────────┐
                    │   React 18 + Tailwind CSS    │
                    │   Vercel (frontend)           │
                    └─────────────┬───────────────┘
                                  │ REST
                    ┌─────────────▼───────────────┐
                    │   FastAPI + APScheduler      │
                    │   Railway (backend)           │
                    └──────┬──────────────┬────────┘
                           │              │
            ┌──────────────▼──┐    ┌──────▼──────────────┐
            │  Stock Committee │    │  Forex Committee     │
            │                  │    │                      │
            │  Technician      │    │  FX Technician       │
            │  Fundamentalist  │    │  FX Carry            │
            │  Newshound       │    │  FX Macro            │
            │  Macro Watcher   │    │  FX Risk Manager     │
            │  Risk Manager    │    │  (pure logic)        │
            │  Chairman (AI)   │    │  Chairman (AI)       │
            └──────────────────┘    └──────────────────────┘
                           │              │
                    ┌──────▼──────────────▼────────┐
                    │   PostgreSQL — Supabase       │
                    └──────────────────────────────┘
```

**AI Models:** Claude Haiku for all agents · Claude Sonnet for on-demand Chairman synthesis
**Data:** yfinance (free) · Finnhub (news) · FMP (fundamentals)

---

## Features

- **Analyze any stock** — type a ticker or company name and get a full AI committee report
  in ~30 seconds, with plain-English explanations of every metric
- **Stock Portfolio** — autonomous paper trading across US, Brazil, Argentina, Turkey, and
  Nigeria markets; $1M starting balance; positions tracked live
- **Forex Trading** — 10 major currency pairs traded with carry, momentum, and macro signals;
  $1M starting balance; live rates strip with P&L
- **Daily budget guard** — Claude spend is capped (default $1.25/day) so there are no
  surprise bills
- **Plain-English results** — all agent rationales and metric labels are written for everyday
  investors, not finance professionals

---

## Cost Profile

| Component | Model | Cost/analysis |
|---|---|---|
| 4 stock agents | Claude Haiku | ~$0.002 |
| Chairman (on-demand) | Claude Sonnet | ~$0.006 |
| **Per stock analysis** | | **~$0.008** |
| Scheduled committee (daily) | All Haiku | ~$0.91/day |
| Forex committee (2x/day) | All Haiku | ~$0.09/day |
| **Daily total** | | **~$1.00/day** |

---

## Setup

### Environment Variables

**Backend (Railway):**
```
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@db.<project>.supabase.co:5432/postgres
FINNHUB_API_KEY=...
FMP_API_KEY=...
DAILY_BUDGET_USD=1.25
FRONTEND_URL=https://your-app.vercel.app
```

**Frontend (Vercel):**
```
VITE_API_URL=https://your-railway-backend.up.railway.app
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

**Railway (backend):**
1. Connect GitHub repo
2. Set env vars in Railway dashboard
3. Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`

**Vercel (frontend):**
1. Import repo, set root to `frontend/`
2. Set `VITE_API_URL` env var
3. Auto-deploys on push to main

---

## Project Structure

```
AI-Hedge-Fund/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── orchestrator.py          # Stock committee logic
│   ├── forex_orchestrator.py    # Forex committee logic
│   ├── scheduler.py             # Auto-trading schedule
│   ├── agents/                  # All AI agents
│   ├── broker/                  # Paper trading execution
│   ├── data/                    # Market data clients
│   ├── db/                      # Database models + CRUD
│   └── api/                     # FastAPI route handlers
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Analyze.jsx      # Stock analysis page
│       │   ├── Portfolio.jsx    # Stock portfolio page
│       │   └── ForexPortfolio.jsx  # Forex trading page
│       └── App.jsx
└── requirements.txt
```

---

## License

MIT
