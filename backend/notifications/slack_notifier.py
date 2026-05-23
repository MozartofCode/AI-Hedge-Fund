"""
Slack notifier — posts trade alerts to #stock-market-news.
Uses the Slack Web API with a Bot Token (SLACK_BOT_TOKEN env var).
If the token is not set, notifications are silently skipped so the
trading system never fails because of a missing Slack config.
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SLACK_CHANNEL_ID = "C0B24NY7XH6"   # #stock-market-news
SLACK_API_URL    = "https://slack.com/api/chat.postMessage"

_AGENT_ICONS = {
    "technician":     "📈",
    "fundamentalist": "📊",
    "newshound":      "📰",
    "macro_watcher":  "🌍",
    "risk_manager":   "🛡️",
}


def _build_message(
    ticker: str,
    side: str,
    qty: int,
    price: float,
    chairman_rationale: str,
    agent_votes: list,
    weighted_score: float,
) -> str:
    """Build a formatted Slack mrkdwn message."""
    side_upper  = side.upper()
    notional    = qty * price
    side_emoji  = "🟢" if side_upper == "BUY" else "🔴"
    side_label  = f"*BOUGHT*" if side_upper == "BUY" else f"*SOLD*"

    lines = [
        f"{side_emoji} {side_label} *{qty} shares of {ticker}* @ ${price:,.2f}",
        f"💰 Total: *${notional:,.2f}*  |  Conviction score: *{weighted_score:.2f}*",
        "",
        f"🏛️ *Chairman's reasoning:*",
        f"> {chairman_rationale}",
        "",
        "📊 *Agent votes:*",
    ]

    for vote in agent_votes:
        name    = vote.get("agent_name", vote.get("agent", ""))
        action  = vote.get("action", "HOLD")
        conf    = vote.get("confidence", 0.0)
        icon    = _AGENT_ICONS.get(name, "🤖")
        veto    = vote.get("veto", False)

        if name == "risk_manager":
            status = "⛔ VETOED" if veto else "✅ Approved"
            lines.append(f"  • {icon} *Risk Manager:* {status}")
        else:
            conf_pct = round((conf or 0) * 100)
            bar      = "█" * (conf_pct // 10) + "░" * (10 - conf_pct // 10)
            lines.append(f"  • {icon} *{name.replace('_', ' ').title()}:* {action} {conf_pct}% `{bar}`")

    return "\n".join(lines)


async def notify_trade(
    ticker: str,
    side: str,
    qty: int,
    price: float,
    chairman_rationale: str,
    agent_votes: list,
    weighted_score: float = 0.0,
) -> None:
    """
    Post a trade alert to #stock-market-news.
    Silently no-ops if SLACK_BOT_TOKEN is not configured.
    """
    token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    if not token:
        print("[Slack] SLACK_BOT_TOKEN not set — skipping notification")
        return

    text = _build_message(
        ticker=ticker,
        side=side,
        qty=int(round(qty)),
        price=price,
        chairman_rationale=chairman_rationale,
        agent_votes=agent_votes,
        weighted_score=weighted_score,
    )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                SLACK_API_URL,
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "channel":  SLACK_CHANNEL_ID,
                    "text":     text,
                    "mrkdwn":   True,
                    "unfurl_links": False,
                },
            )
            data = resp.json()
            if data.get("ok"):
                print(f"[Slack] Trade alert sent for {ticker} {side.upper()}")
            else:
                print(f"[Slack] API error: {data.get('error', 'unknown')}")
    except Exception as e:
        print(f"[Slack] Notification failed (non-fatal): {e}")
