import pytz
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

ET = pytz.timezone("America/New_York")
scheduler = AsyncIOScheduler(timezone=ET)


async def _committee_job():
    from backend.orchestrator import run_full_committee
    from backend.broker.alpaca_client import is_market_open
    now = datetime.now(ET).isoformat()
    if not is_market_open():
        print(f"[{now}] Market closed — skipping committee session")
        return
    print(f"[{now}] Starting committee session")
    results = await run_full_committee()
    print(f"[{now}] Committee complete — {len(results)} tickers processed")


async def _snapshot_job():
    from backend.broker.alpaca_client import get_portfolio
    from backend.db.session import AsyncSessionLocal
    from backend.db.crud import save_portfolio_snapshot
    now = datetime.now(ET).isoformat()
    try:
        portfolio = get_portfolio()
        async with AsyncSessionLocal() as db:
            await save_portfolio_snapshot(db, portfolio)
        print(f"[{now}] Portfolio snapshot saved — ${portfolio['total_value']:,.2f}")
    except Exception as e:
        print(f"[{now}] Snapshot failed: {e}")


def start_scheduler():
    scheduler.add_job(
        _committee_job,
        trigger=IntervalTrigger(minutes=30),
        id="committee_session",
        replace_existing=True,
    )
    scheduler.add_job(
        _snapshot_job,
        trigger=IntervalTrigger(minutes=15),
        id="portfolio_snapshot",
        replace_existing=True,
    )
    scheduler.start()
    print("Scheduler started — committee every 30 min, portfolio snapshot every 15 min")
