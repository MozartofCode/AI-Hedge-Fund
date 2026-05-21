import pytz
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

ET = pytz.timezone("America/New_York")
scheduler = AsyncIOScheduler(timezone=ET)


async def _committee_job():
    from backend.orchestrator import run_full_committee
    from backend.broker.paper_broker import is_market_open
    now = datetime.now(ET).isoformat()
    if not is_market_open():
        print(f"[{now}] Market closed — skipping committee session")
        return
    print(f"[{now}] Starting committee session")
    results = await run_full_committee()
    print(f"[{now}] Committee complete — {len(results)} tickers processed")


async def _snapshot_job():
    from backend.broker.paper_broker import get_portfolio
    from backend.db.session import AsyncSessionLocal
    from backend.db.crud import save_portfolio_snapshot
    now = datetime.now(ET).isoformat()
    try:
        portfolio = await get_portfolio()
        async with AsyncSessionLocal() as db:
            await save_portfolio_snapshot(db, portfolio)
        print(f"[{now}] Portfolio snapshot saved — ${portfolio['total_value']:,.2f}")
    except Exception as e:
        print(f"[{now}] Snapshot failed: {e}")


def start_scheduler():
    # 3 committee sessions per trading day (Mon–Fri):
    #   10:00 AM ET  — morning after open settles
    #   12:30 PM ET  — midday check
    #    3:00 PM ET  — power-hour before close
    for hour, minute in [(10, 0), (12, 30), (15, 0)]:
        scheduler.add_job(
            _committee_job,
            trigger=CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone=ET),
            id=f"committee_{hour:02d}{minute:02d}",
            replace_existing=True,
        )

    # Portfolio snapshot every 30 min during market hours
    scheduler.add_job(
        _snapshot_job,
        trigger=CronTrigger(day_of_week="mon-fri", hour="9-16", minute="*/30", timezone=ET),
        id="portfolio_snapshot",
        replace_existing=True,
    )

    scheduler.start()
    print("Scheduler started — committee at 10:00am / 12:30pm / 3:00pm ET (Mon–Fri)")
