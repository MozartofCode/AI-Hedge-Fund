# AI Hedge Fund

An autonomous multi-agent trading analysis system powered by Claude AI. Five specialized agents independently analyze a stock from different angles, then a Chairman synthesizes all votes into a final conviction-weighted recommendation.

---

## Architecture

```
User → FastAPI Backend → 5 Parallel Agents → Chairman → Report
                              │
              ┌───────────────┼───────────────┐
         Technician    Fundamentalist    Sentiment
              │               │               │
         Multi-TF TA     FMP Financials   (placeholder)
         yfinance          FMP DCF
              │
       ┌──────┼──────┐
    Weekly  Daily  Monthly
```

**Backend:** FastAPI + SQLAlchemy (async) + PostgreSQL — deployed on Railway  
**Frontend:** React 18 + Tailwind CSS + Recharts — deployed on Vercel  
**AI:** Anthropic Claude (Haiku for agents, Sonnet for Chairman synthesis)

---

## Agents

### 1. Technician — Multi-Timeframe ICT/SMC Engine

Fetches 3 timeframes from yfinance and runs a full technical suite:

**Daily (2 years)**
- Order Blocks — identifies bullish/bearish institutional candles with body size and wick ratio filters
- Liquidity Sweeps — detects stop hunts above swing highs / below swing lows + equal highs/lows
- Market Structure — classifies HH+HL (uptrend), LL+LH (downtrend), BOS (break of structure), CHoCH (change of character)
- Fibonacci Retracement — swing high/low over 120-day window; nearest level + position %
- Volume Profile — vectorized 20-bin POC/VAH/VAL
- Anchored VWAP — anchored to highest-volume day in the window
- Stochastic RSI — K line + signal (overbought/oversold/neutral/bullish cross/bearish cross)
- RSI (14) + MACD signal

**Weekly (5 years)**
- EMA alignment (20/50/200) — strongly_bullish / bullish / mixed / bearish / strongly_bearish
- OBV divergence
- MACD signal
- Anchored VWAP + Volume Profile (52-week)

**Monthly (10 years)**
- Market Structure (macro trend)
- RSI divergence (bullish/bearish/none)
- MACD signal

### 2. Fundamentalist — Fair Value Engine

Fetches quarterly financials from FMP and computes:

- **Revenue growth** — YoY and QoQ acceleration
- **EPS growth** — YoY
- **Gross / Operating / Net margins**
- **FCF Yield** — trailing 4-quarter FCF / market cap
- **Debt/Equity ratio**
- **Trust-weighted analyst consensus** — winsorized, bootstrap 95% CI; firms weighted by historical accuracy (Goldman Sachs 1.30x to Wedbush 0.85x)
- **DCF intrinsic value** — from FMP model
- **Valuation signal** — STRONG BUY / BUY / OUTPERFORM / HOLD / UNDERPERFORM / SELL / STRONG SELL

### 3. Sentiment Agent *(stub — Phase 2)*

Placeholder for news sentiment + social signal integration.

### 4. Macro Agent *(stub — Phase 2)*

Placeholder for yield curve, DXY, VIX, sector rotation.

### 5. Insider Agent *(stub — Phase 2)*

Placeholder for SEC Form 4 insider transaction parsing.

---

## Chairman (Synthesis)

After all agents vote, the Chairman (Claude Sonnet) receives every agent's action, confidence, rationale, and suggested_position_size_pct. It produces:

- Overall recommendation (BUY / HOLD / SELL)
- Conviction score (0–100)
- Weighted position size %
- Narrative synthesis paragraph
- Bull case / Bear case / Key risks

**Cost optimization:** If all agent votes are HOLD with confidence < 0.4, the Chairman call is skipped and a default HOLD response is returned — saving ~$0.003/request.

**Daily cap:** Budget guard limits Chairman calls to ~$4/day.

---

## Dynamic Screener

Runs on a configurable schedule (APScheduler). Screens a watchlist of tickers, runs the full agent pipeline on each, stores results in PostgreSQL. Frontend polls /api/screener/results for the latest batch.

---

## UI

**Analyze Page** — Claude-style landing:
- Time-based greeting ("Good morning / afternoon / evening, Investor.") driven by EST/EDT via Intl.DateTimeFormat
- 2x2 suggestion cards for one-click analysis (NVDA, TSLA, RKLB, AAPL)
- Search box with ticker resolution

**Results Page** — Tabbed breakdown:
- Overview: conviction gauge, price, recommendation
- Technical: multi-timeframe signals, Order Blocks, Liquidity, Structure
- Fundamental: revenue/EPS growth, margins, FCF yield, analyst consensus
- Chairman Report: full prose synthesis

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL (or use Railway's managed Postgres)

### Environment Variables

**Backend (.env or Railway dashboard):**

```
ANTHROPIC_API_KEY=sk-ant-...
FMP_API_KEY=...              # financialmodelingprep.com — free tier works for most endpoints
DATABASE_URL=postgresql+asyncpg://...
```

> FMP Free Tier Note: DCF valuations and individual analyst price targets require a paid FMP plan. On the free tier, these fields will be empty but all other fundamental metrics (revenue, EPS, margins, analyst consensus) will still populate.

**Frontend (.env.local or Vercel dashboard):**

```
VITE_API_BASE_URL=https://your-railway-app.railway.app
```

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

### Deployment

**Railway (backend):**
1. Connect GitHub repo
2. Set env vars in Railway dashboard
3. Railway auto-deploys on push to main

**Vercel (frontend):**
1. Import repo, set root to frontend/
2. Set VITE_API_BASE_URL env var
3. Vercel auto-deploys on push to main

---

## Project Structure

```
AI-Hedge-Fund/
├── backend/
│   ├── agents/
│   │   ├── base_agent.py          # call_claude() wrapper, model constants
│   │   ├── technician.py          # Multi-TF ICT/SMC technical engine
│   │   ├── fundamentalist.py      # Fair value + FMP financials engine
│   │   ├── sentiment_agent.py     # Stub
│   │   ├── macro_agent.py         # Stub
│   │   └── insider_agent.py       # Stub
│   ├── data/
│   │   └── fmp_client.py          # FMP API wrapper (quarterly statements, DCF, targets)
│   ├── routers/
│   │   ├── analyze.py             # POST /api/analyze — runs agent pipeline
│   │   └── screener.py            # GET /api/screener/results
│   ├── models.py                  # SQLAlchemy ORM models
│   ├── database.py                # Async engine + session factory
│   ├── chairman.py                # Chairman synthesis + cost guard
│   ├── scheduler.py               # APScheduler screener job
│   └── main.py                    # FastAPI app factory
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Analyze.jsx        # Claude-style landing + search
│   │   │   └── Results.jsx        # Tabbed analysis report
│   │   ├── components/
│   │   │   └── SearchBox.jsx
│   │   └── App.jsx
│   ├── package.json
│   └── vite.config.js
├── requirements.txt
└── README.md
```

---

## Cost Profile

| Component        | Model         | Tokens    | Cost/call |
|------------------|---------------|-----------|-----------|
| Technician       | Claude Haiku  | ~150 out  | ~$0.0003  |
| Fundamentalist   | Claude Haiku  | ~150 out  | ~$0.0003  |
| Sentiment (stub) | —             | —         | —         |
| Macro (stub)     | —             | —         | —         |
| Insider (stub)   | —             | —         | —         |
| Chairman         | Claude Sonnet | ~600 out  | ~$0.003   |
| **Per analysis** |               |           | **~$0.004**|

At 1,000 analyses/day: ~$4/day. The Chairman skip-on-HOLD optimization cuts costs further for low-signal periods.

---

## License

MIT
