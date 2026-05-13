import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv

load_dotenv()

from backend.db.models import Base
from backend.db.session import engine, get_db
from backend.db.crud import create_session, save_agent_vote, finalize_session, log_trade
from backend.api import portfolio, trades, debates, stats
from backend.scheduler import start_scheduler
from backend.broker.alpaca_client import is_market_open, place_order
from backend.agents.base_agent import get_stub_vote


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    start_scheduler()
    yield
    await engine.dispose()


app = FastAPI(title="AlphaCommittee API", version="0.2.0", lifespan=lifespan)

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
    return {"status": "ok", "market_open": is_market_open()}


@app.post("/api/run-committee")
async def run_committee(ticker: str = None):
    """Manually trigger a full committee session or a single-ticker run."""
    from backend.orchestrator import run_full_committee, run_committee_for_ticker
    from backend.broker.alpaca_client import get_portfolio
    from backend.db.session import AsyncSessionLocal
    from backend.db.crud import get_peak_portfolio_value

    if ticker:
        portfolio_data = get_portfolio()
        async with AsyncSessionLocal() as db:
            peak = await get_peak_portfolio_value(db)
        result = await run_committee_for_ticker(ticker.upper(), portfolio_data, peak)
        return result

    results = await run_full_committee()
    return {"sessions": results, "count": len(results)}


@app.post("/api/test-e2e")
async def test_end_to_end(ticker: str = "AAPL", db: AsyncSession = Depends(get_db)):
    """Phase 1 smoke test — still available for quick sanity checks."""
    vote = get_stub_vote(ticker)
    session = await create_session(db, ticker)
    await save_agent_vote(db, session.id, {**vote, "raw_data": {"phase": 1, "test": True}})

    order_result = None
    order_placed = False
    if is_market_open() and vote.get("action") == "BUY":
        try:
            order_result = place_order(ticker, "buy", vote.get("suggested_position_size_pct", 3))
            order_placed = True
            await log_trade(db, session.id, {
                "ticker": ticker, "side": "buy",
                "alpaca_order_id": order_result["alpaca_order_id"],
            })
        except Exception as e:
            order_result = {"error": str(e)}

    await finalize_session(db, session.id, {
        "decision": vote.get("action", "HOLD"),
        "chairman_rationale": f"[Phase 1 test] {vote.get('rationale', '')}",
        "weighted_score": vote.get("confidence", 0.0),
        "order_placed": order_placed,
        "order_id": order_result.get("alpaca_order_id") if order_result and order_placed else None,
    })

    return {
        "session_id": str(session.id),
        "ticker": ticker,
        "vote": vote,
        "order_result": order_result,
        "market_open": is_market_open(),
    }
