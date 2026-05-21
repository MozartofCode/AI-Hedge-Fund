MAX_POSITIONS = 3
MAX_SINGLE_POSITION_PCT = 10.0
MAX_DRAWDOWN_PCT = 8.0
BASE_POSITION_PCT = 5.0


def get_vote(ticker: str, portfolio: dict, peak_value: float = None) -> dict:
    """
    Pure logic — no IO, no Claude call.
    portfolio must be provided by the orchestrator (already fetched).
    """
    try:
        total_value = portfolio.get("total_value", 0)
        positions = portfolio.get("positions", [])

        # Drawdown check
        drawdown_pct = 0.0
        if peak_value and peak_value > 0 and total_value > 0:
            drawdown_pct = round((total_value - peak_value) / peak_value * 100, 2)

        if drawdown_pct <= -MAX_DRAWDOWN_PCT:
            return {
                "agent": "risk_manager", "ticker": ticker,
                "veto": True, "approved_position_size_pct": 0,
                "reason": (
                    f"Portfolio drawdown {drawdown_pct:.1f}% exceeds -{MAX_DRAWDOWN_PCT}% limit. "
                    "New BUYs blocked until recovery."
                ),
                "portfolio_drawdown_pct": drawdown_pct,
            }

        # Duplicate position check
        if any(p["ticker"] == ticker for p in positions):
            return {
                "agent": "risk_manager", "ticker": ticker,
                "veto": True, "approved_position_size_pct": 0,
                "reason": f"Position already open for {ticker}. Blocking duplicate BUY.",
                "portfolio_drawdown_pct": drawdown_pct,
            }

        # Max open positions check
        if len(positions) >= MAX_POSITIONS:
            return {
                "agent": "risk_manager", "ticker": ticker,
                "veto": True, "approved_position_size_pct": 0,
                "reason": f"Max {MAX_POSITIONS} open positions reached ({len(positions)} open).",
                "portfolio_drawdown_pct": drawdown_pct,
            }

        # Approved
        approved_pct = min(BASE_POSITION_PCT, MAX_SINGLE_POSITION_PCT)
        current_exposure_pct = (
            round(sum(p.get("market_value", 0) for p in positions) / total_value * 100, 2)
            if total_value > 0 else 0
        )

        return {
            "agent": "risk_manager", "ticker": ticker,
            "veto": False,
            "approved_position_size_pct": approved_pct,
            "reason": (
                f"Approved. Portfolio exposure {current_exposure_pct:.1f}%, "
                f"{len(positions)}/{MAX_POSITIONS} positions open. "
                f"Drawdown {drawdown_pct:.1f}%."
            ),
            "portfolio_drawdown_pct": drawdown_pct,
        }
    except Exception as e:
        return {
            "agent": "risk_manager", "ticker": ticker,
            "veto": True, "approved_position_size_pct": 0,
            "reason": f"Risk manager error: {e}. Vetoing as precaution.",
            "portfolio_drawdown_pct": 0,
        }
