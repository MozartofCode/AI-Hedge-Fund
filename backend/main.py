import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv

load_dotenv()

from backend.db.models import Base
from backend.db.session import engine, get_db, AsyncSessionLocal
from backend.db.crud import create_session, save_agent_vote, finalize_session, log_trade, init_paper_portfolio
from backend.api import portfolio, trades, debates, stats
from backend.scheduler import start_scheduler
from backend.markets import MARKETS, is_market_open
from backend.agents.base_agent import get_stub_vote


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Seed paper portfolio rows for all markets (idempotent)
    async with AsyncSessionLocal() as db:
        for mkt_code, cfg in MARKETS.items():
            await init_paper_portfolio(
                db,
                market=mkt_code,
                starting_cash=cfg["starting_cash"],
            )
    # In-process scheduler only works on an always-on host. On free/sleeping
    # hosts set ENABLE_SCHEDULER=false and drive trades via the GitHub Actions
    # cron that POSTs to /api/run-committee instead.
    if os.getenv("ENABLE_SCHEDULER", "true").lower() == "true":
        start_scheduler()
    else:
        print("[startup] ENABLE_SCHEDULER=false — in-process scheduler disabled "
              "(expecting external cron to call /api/run-committee)")
    yield
    await engine.dispose()


app = FastAPI(title="AlphaCommittee API", version="0.3.0", lifespan=lifespan)

# CORS: allow the configured frontend URL, local dev, and ANY *.vercel.app
# deployment (so production + preview/branch deploys all work without redeploying
# the backend). allow_origin_regex matches the full origin string.
_FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
_ALLOWED_ORIGIN_REGEX = r"https://([a-z0-9-]+\.)*vercel\.app|http://localhost(:\d+)?"
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_FRONTEND_URL],
    allow_origin_regex=_ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router, prefix="/api")
app.include_router(trades.router, prefix="/api")
app.include_router(debates.router, prefix="/api")
app.include_router(stats.router, prefix="/api")


@app.get("/api/health")
async def health():
    markets_open = {code: is_market_open(code) for code in MARKETS}
    return {
        "status": "ok",
        "market_open": markets_open.get("US", False),   # backward compat
        "markets_open": markets_open,
    }


@app.post("/api/run-committee")
async def run_committee(ticker: str = None, market: str = Query('US'), request: Request = None):
    """Manually/externally trigger a full committee session or a single-ticker run.

    If CRON_SECRET is set, callers must send a matching X-Cron-Secret header.
    Used by the free GitHub Actions cron to drive trading without an always-on host.
    """
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret:
        provided = request.headers.get("X-Cron-Secret") if request else None
        if provided != cron_secret:
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
    try:
        from backend.orchestrator import run_full_committee, run_committee_for_ticker
        from backend.broker.paper_broker import get_portfolio
        from backend.db.crud import get_peak_portfolio_value

        mkt = market.upper()
        if ticker:
            portfolio_data = await get_portfolio(mkt)
            async with AsyncSessionLocal() as db:
                peak = await get_peak_portfolio_value(db, mkt)
            result = await run_committee_for_ticker(ticker.upper(), portfolio_data, peak, mkt)
            return result

        results = await run_full_committee(mkt)
        return {"market": mkt, "sessions": results, "count": len(results)}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/api/search")
async def search(q: str = Query(""), market: str = Query('US')):
    """Search for tickers by name or symbol — for name-to-ticker resolution."""
    try:
        from backend.data.fmp_client import search_ticker
        results = search_ticker(q.strip(), limit=8)
        return results
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/analyze")
async def analyze(ticker: str, market: str = Query('US')):
    """
    Run all 5 agents + Chairman for a single ticker.
    Analysis only — no order placed, works when market is closed.
    """
    try:
        from backend.orchestrator import analyze_ticker
        result = await analyze_ticker(ticker.upper().strip(), market.upper())
        return result
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/test-e2e")
async def test_end_to_end(
    ticker: str = "AAPL",
    market: str = Query('US'),
    db: AsyncSession = Depends(get_db),
):
    """Phase 1 smoke test — still available for quick sanity checks."""
    from backend.broker.paper_broker import place_order
    mkt  = market.upper()
    vote = get_stub_vote(ticker)
    session = await create_session(db, ticker, mkt)
    await save_agent_vote(db, session.id, {**vote, "raw_data": {"phase": 1, "test": True}})

    order_result = None
    order_placed = False
    if is_market_open(mkt) and vote.get("action") == "BUY":
        try:
            order_result = await place_order(ticker, "buy", vote.get("suggested_position_size_pct", 3), mkt)
            order_placed = True
            await log_trade(db, session.id, {
                "ticker": ticker, "side": "buy",
                "qty": order_result.get("qty"),
                "filled_price": order_result.get("price"),
                "filled_at": None,
                "order_id": order_result.get("order_id"),
            }, mkt)
        except Exception as e:
            order_result = {"error": str(e)}

    await finalize_session(db, session.id, {
        "decision": vote.get("action", "HOLD"),
        "chairman_rationale": f"[Phase 1 test] {vote.get('rationale', '')}",
        "weighted_score": vote.get("confidence", 0.0),
        "order_placed": order_placed,
        "order_id": order_result.get("order_id") if order_result and order_placed else None,
    })

    return {
        "session_id": str(session.id),
        "ticker": ticker,
        "market": mkt,
        "vote": vote,
        "order_result": order_result,
        "market_open": is_market_open(mkt),
    }
