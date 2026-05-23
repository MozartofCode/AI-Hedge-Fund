MAX_POSITIONS            = 7      # was 3 — deploy more capital
MAX_SINGLE_POSITION_PCT  = 10.0
MAX_DRAWDOWN_PCT         = 10.0   # portfolio-level drawdown guard
MAX_SAME_SECTOR_POSITIONS = 2
STOP_LOSS_PCT            = 8.0    # exit position if down 8% from entry
PROFIT_TARGET_PCT        = 20.0   # take profits if up 20% from entry
BASE_POSITION_PCT        = 5.0
MAX_CONVICTION_PCT       = 10.0   # ceiling for high-conviction trades

# Sector map — covers expanded 15-ticker watchlist
_SECTOR_MAP = {
    "AAPL":  "Technology",
    "NVDA":  "Technology",
    "MSFT":  "Technology",
    "GOOGL": "Technology",
    "META":  "Technology",
    "AMD":   "Technology",
    "QQQ":   "Technology",
    "AMZN":  "Consumer Discretionary",
    "TSLA":  "Consumer Discretionary",
    "JPM":   "Financials",
    "GS":    "Financials",
    "UNH":   "Healthcare",
    "LLY":   "Healthcare",
    "XOM":   "Energy",
    "SPY":   "Broad Market",
}


def get_vote(ticker: str, portfolio: dict, peak_value: float = None) -> dict:
    """
    Pure logic — no IO, no Claude call.
    Returns force_sell=True for stop-loss triggers.
    Returns take_profit=True for profit-target triggers.
    Returns veto=True to block BUYs.
    """
    try:
        total_value = portfolio.get("total_value", 0)
        positions   = portfolio.get("positions", [])

        # ── Portfolio-level drawdown check ────────────────────────────────────
        drawdown_pct = 0.0
        if peak_value and peak_value > 0 and total_value > 0:
            drawdown_pct = round((total_value - peak_value) / peak_value * 100, 2)

        if drawdown_pct <= -MAX_DRAWDOWN_PCT:
            return {
                "agent": "risk_manager", "ticker": ticker,
                "veto": True, "force_sell": False, "take_profit": False,
                "approved_position_size_pct": 0,
                "reason": (
                    f"Portfolio drawdown {drawdown_pct:.1f}% exceeds -{MAX_DRAWDOWN_PCT}% limit. "
                    "New BUYs blocked until recovery."
                ),
                "portfolio_drawdown_pct": drawdown_pct,
            }

        # ── Per-position stop loss / profit target ────────────────────────────
        existing = next((p for p in positions if p["ticker"] == ticker), None)
        if existing:
            pl_pct = round(existing.get("unrealized_plpc", 0) * 100, 2)

            if pl_pct <= -STOP_LOSS_PCT:
                return {
                    "agent": "risk_manager", "ticker": ticker,
                    "veto": False, "force_sell": True, "take_profit": False,
                    "approved_position_size_pct": BASE_POSITION_PCT,
                    "reason": (
                        f"Stop loss triggered: {ticker} is down {pl_pct:.1f}% from entry. "
                        f"Forced exit to limit losses (threshold: -{STOP_LOSS_PCT}%)."
                    ),
                    "portfolio_drawdown_pct": drawdown_pct,
                }

            if pl_pct >= PROFIT_TARGET_PCT:
                return {
                    "agent": "risk_manager", "ticker": ticker,
                    "veto": False, "force_sell": False, "take_profit": True,
                    "approved_position_size_pct": BASE_POSITION_PCT,
                    "reason": (
                        f"Profit target reached: {ticker} is up {pl_pct:.1f}% from entry. "
                        f"Taking profits (threshold: +{PROFIT_TARGET_PCT}%)."
                    ),
                    "portfolio_drawdown_pct": drawdown_pct,
                }

        # ── Duplicate position check (blocks BUY only) ────────────────────────
        if any(p["ticker"] == ticker for p in positions):
            return {
                "agent": "risk_manager", "ticker": ticker,
                "veto": True, "force_sell": False, "take_profit": False,
                "approved_position_size_pct": 0,
                "reason": f"Position already open for {ticker}. Blocking duplicate BUY.",
                "portfolio_drawdown_pct": drawdown_pct,
            }

        # ── Max open positions check ──────────────────────────────────────────
        if len(positions) >= MAX_POSITIONS:
            return {
                "agent": "risk_manager", "ticker": ticker,
                "veto": True, "force_sell": False, "take_profit": False,
                "approved_position_size_pct": 0,
                "reason": f"Max {MAX_POSITIONS} open positions reached ({len(positions)} open).",
                "portfolio_drawdown_pct": drawdown_pct,
            }

        # ── Sector concentration check ────────────────────────────────────────
        ticker_sector = _SECTOR_MAP.get(ticker.upper())
        if ticker_sector and ticker_sector != "Broad Market":
            same_sector = [p for p in positions if _SECTOR_MAP.get(p["ticker"].upper()) == ticker_sector]
            if len(same_sector) >= MAX_SAME_SECTOR_POSITIONS:
                held = ", ".join(p["ticker"] for p in same_sector)
                return {
                    "agent": "risk_manager", "ticker": ticker,
                    "veto": True, "force_sell": False, "take_profit": False,
                    "approved_position_size_pct": 0,
                    "reason": (
                        f"Sector concentration limit: already holding {len(same_sector)} "
                        f"{ticker_sector} position(s) ({held}). "
                        f"Max {MAX_SAME_SECTOR_POSITIONS} per sector."
                    ),
                    "portfolio_drawdown_pct": drawdown_pct,
                }

        # ── Approved ──────────────────────────────────────────────────────────
        current_exposure_pct = (
            round(sum(p.get("market_value", 0) for p in positions) / total_value * 100, 2)
            if total_value > 0 else 0
        )

        return {
            "agent": "risk_manager", "ticker": ticker,
            "veto": False, "force_sell": False, "take_profit": False,
            "approved_position_size_pct": BASE_POSITION_PCT,
            "reason": (
                f"Approved. Portfolio exposure {current_exposure_pct:.1f}%, "
                f"{len(positions)}/{MAX_POSITIONS} positions open. "
                f"Drawdown {drawdown_pct:.1f}%. "
                f"Sector: {ticker_sector or 'unknown'}."
            ),
            "portfolio_drawdown_pct": drawdown_pct,
        }

    except Exception as e:
        return {
            "agent": "risk_manager", "ticker": ticker,
            "veto": True, "force_sell": False, "take_profit": False,
            "approved_position_size_pct": 0,
            "reason": f"Risk manager error: {e}. Vetoing as precaution.",
            "portfolio_drawdown_pct": 0,
        }
