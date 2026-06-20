import pytz
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.markets import MARKETS

scheduler = AsyncIOScheduler()

# One midday US session per day — keeps Claude spend under $1/day.
# To trade more often, add tuples (e.g. [(10, 0), (12, 30), (15, 0)]); each
# extra session roughly doubles the daily Claude cost.
_MARKET_SESSIONS = {
    "US": [(11, 30)],
}


def _make_committee_job(market_code: str):
    async def _job():
        from backend.orchestrator import run_full_committee
        from backend.markets import is_market_open
        tz  = pytz.timezone(MARKETS[market_code]["timezone"])
        now = datetime.now(tz).isoformat()
        if not is_market_open(market_code):
            print(f"[{now}] [{market_code}] Market closed — skipping")
            return
        print(f"[{now}] [{market_code}] Starting committee session")
        results = await run_full_committee(market_code)
        print(f"[{now}] [{market_code}] Committee complete — {len(results)} tickers processed")
    _job.__name__ = f"_committee_job_{market_code}"
    return _job


def _make_snapshot_job(market_code: str):
    async def _job():
        from backend.broker.paper_broker import get_portfolio
        from backend.db.session import AsyncSessionLocal
        from backend.db.crud import save_portfolio_snapshot
        from backend.markets import is_market_open
        tz  = pytz.timezone(MARKETS[market_code]["timezone"])
        now = datetime.now(tz).isoformat()
        if not is_market_open(market_code):
            return
        try:
            portfolio = await get_portfolio(market_code)
            async with AsyncSessionLocal() as db:
                await save_portfolio_snapshot(db, portfolio, market_code)
            print(f"[{now}] [{market_code}] Snapshot saved — {portfolio['total_value']:,.2f}")
        except Exception as e:
            print(f"[{now}] [{market_code}] Snapshot failed: {e}")
    _job.__name__ = f"_snapshot_job_{market_code}"
    return _job


def start_scheduler():
    for mkt_code, sessions in _MARKET_SESSIONS.items():
        tz = pytz.timezone(MARKETS[mkt_code]["timezone"])
        job_fn = _make_committee_job(mkt_code)

        for idx, (hour, minute) in enumerate(sessions):
            scheduler.add_job(
                job_fn,
                trigger=CronTrigger(
                    day_of_week="mon-fri",
                    hour=hour,
                    minute=minute,
                    timezone=tz,
                ),
                id=f"committee_{mkt_code}_{idx}",
                replace_existing=True,
            )

        # Snapshot every 30 min during trading hours
        open_h  = MARKETS[mkt_code]["open"].hour
        close_h = MARKETS[mkt_code]["close"].hour
        snap_fn = _make_snapshot_job(mkt_code)
        scheduler.add_job(
            snap_fn,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=f"{open_h}-{close_h}",
                minute="*/30",
                timezone=tz,
            ),
            id=f"snapshot_{mkt_code}",
            replace_existing=True,
        )

    scheduler.start()
    markets_str = ", ".join(
        f"{c}({', '.join(f'{h:02d}:{m:02d}' for h, m in s)})"
        for c, s in _MARKET_SESSIONS.items()
    )
    print(f"Scheduler started — sessions: {markets_str}")
