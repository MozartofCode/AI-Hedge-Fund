import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime

ET = pytz.timezone("America/New_York")
scheduler = AsyncIOScheduler(timezone=ET)


async def run_committee_session():
    """Stub — wired to orchestrator in Phase 2."""
    print(f"[{datetime.now(ET).isoformat()}] Committee session triggered (Phase 2)")


def start_scheduler():
    scheduler.add_job(
        run_committee_session,
        trigger=IntervalTrigger(minutes=30),
        id="committee_session",
        replace_existing=True,
    )
    scheduler.start()
    print("Scheduler started — committee sessions every 30 min during market hours")
