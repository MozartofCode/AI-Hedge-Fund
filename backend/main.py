import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
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
        # Advance the paper_portfolio PK sequence past any rows that were inserted
        # with an explicit id (old single-row schema used id=1 directly, which
        # bypasses the sequence and leaves it at 1 — causing conflicts on new inserts).
        await conn.execute(text(
            "SELECT setval("
            "  pg_get_serial_sequence('paper_portfolio', 'id'),"
            "  COALESCE((SELECT MAX(id) FROM paper_portfolio), 0),"
            "  true"   # 'true' = last-value-already-used, so nextval returns MAX+1
            ")"
        ))
    # Seed paper portfolio rows for all markets (idempotent)
    async with AsyncSessionLocal() as db:
        for mkt_code, cfg in MARKETS.items():
            await init_paper_portfolio(
                db,
                market=mkt_code,
                starting_cash=cfg["starting_cash"],
            )
    start_scheduler()
    yield
    await engine.dispose()


app = FastAPI(title="AlphaCommittee API", version="0.3.0", lifespan=lifespan)

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
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
async def run_committee(ticker: str = None, market: str = Query('US')):
    """Manually trigger a full committee session or a single-ticker run."""
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


@app.post("/api/analyze")
async def analyze(ticker: str, market: str = Query('US')):
    """
    Run all 5 agents + Chairman for a single ticker.
    Analysis only — no order placed, works when market is closed.
    """
    from backend.orchestrator import analyze_ticker
    result = await analyze_ticker(ticker.upper().strip(), market.upper())
    return result


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
