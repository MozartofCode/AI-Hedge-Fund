import yfinance as yf

MAX_POSITIONS             = 25     # raised 10→25 — run a full diversified portfolio
MAX_SINGLE_POSITION_PCT   = 12.0   # hard ceiling per trade
MAX_DRAWDOWN_PCT          = 15.0   # allow more breathing room in volatile markets
MAX_SAME_SECTOR_POSITIONS = 5      # raised 3→5 — allow thematic concentration in hot sectors
STOP_LOSS_PCT             = 8.0    # exit if down 8% from entry
PROFIT_TARGET_PCT         = 75.0   # let winners RUN — don't kill 10X plays at +20%
TRAILING_START_PCT        = 20.0   # start trailing once position is up 20%
TRAILING_STOP_TRAIL       = 20.0   # sell if price falls 20% from its 60-day high
BASE_POSITION_PCT         = 3.0    # smaller base — fits more positions
MAX_CONVICTION_PCT        = 12.0   # ceiling for high-conviction trades

# Sector map — 50-ticker US watchlist + non-US ADRs
_SECTOR_MAP = {
    # Mega-cap tech / AI infrastructure
    "AAPL":  "Technology",
    "NVDA":  "Technology",
    "MSFT":  "Technology",
    "GOOGL": "Technology",
    "META":  "Technology",
    "AMD":   "Technology",
    "QQQ":   "Technology",
    "ARM":   "Technology",
    "AVGO":  "Technology",
    "SMCI":  "Technology",
    # Cloud / cybersecurity / software
    "CRWD":  "Technology",
    "NET":   "Technology",
    "DDOG":  "Technology",
    "PLTR":  "Technology",
    "GTLB":  "Technology",
    "APP":   "Technology",
    "TTD":   "Technology",
    "MNDY":  "Technology",
    "DUOL":  "Technology",
    "SOUN":  "Technology",
    # Space / deep tech / quantum
    "RKLB":  "Aerospace & Defense",
    "LUNR":  "Aerospace & Defense",
    "IONQ":  "Technology",
    "JOBY":  "Aerospace & Defense",
    "ASTS":  "Technology",
    "RXRX":  "Healthcare",
    # Consumer / e-commerce
    "AMZN":  "Consumer Discretionary",
    "TSLA":  "Consumer Discretionary",
    "CELH":  "Consumer Staples",
    "HIMS":  "Healthcare",
    "CAVA":  "Consumer Discretionary",
    # Fintech / crypto
    "HOOD":  "Financials",
    "SOFI":  "Financials",
    "AFRM":  "Financials",
    "UPST":  "Financials",
    "NU":    "Financials",
    "COIN":  "Financials",
    "MARA":  "Financials",
    "MSTR":  "Financials",
    # Financials
    "JPM":   "Financials",
    "GS":    "Financials",
    # Healthcare
    "LLY":   "Healthcare",
    # Social / community
    "RDDT":  "Technology",
    "AXON":  "Technology",
    # Energy / clean tech
    "XOM":   "Energy",
    "CLSK":  "Energy",
    # Broad market
    "SPY":   "Broad Market",
    # Argentina ADRs
    "YPF":   "Energy",
    "GGAL":  "Financials",
    "BMA":   "Financials",
    "PAM":   "Energy",
    "LOMA":  "Materials",
    "TGS":   "Energy",
    "CEPU":  "Utilities",
    "SUPV":  "Financials",
    "DESP":  "Consumer Discretionary",
    "BIOX":  "Agriculture",
    "GLOB":  "Technology",
    "MELI":  "Consumer Discretionary",
    "ARCO":  "Consumer Discretionary",
    "IRS":   "Real Estate",
    "CAAP":  "Industrials",
}


def get_vote(ticker: str, portfolio: dict, peak_value: float = None) -> dict:
    """
    Pure logic — no IO, no Claude call.
    Returns force_sell=True for stop-loss triggers.
    Returns take_profit=True for profit-target triggers.
    Returns veto=True to block BUYs.

    NOTE: profit target is now 75% — we want to hold 10X candidates.
    The committee's regular SELL votes handle normal exits.
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
                        f"Forced exit (threshold: -{STOP_LOSS_PCT}%)."
                    ),
                    "portfolio_drawdown_pct": drawdown_pct,
                }

            # ── ★ Trailing stop: protect profits once up 20% ──────────────────
            if pl_pct >= TRAILING_START_PCT:
                try:
                    hist_60d    = yf.Ticker(ticker).history(period="60d")[["Close","High"]].dropna()
                    if not hist_60d.empty:
                        recent_high = float(hist_60d["High"].max())
                        cur_price   = float(hist_60d["Close"].iloc[-1])
                        trail_px    = recent_high * (1 - TRAILING_STOP_TRAIL / 100)
                        if cur_price > 0 and cur_price <= trail_px:
                            drop_from_high = round((cur_price / recent_high - 1) * 100, 1)
                            return {
                                "agent": "risk_manager", "ticker": ticker,
                                "veto": False, "force_sell": True, "take_profit": False,
                                "approved_position_size_pct": BASE_POSITION_PCT,
                                "reason": (
                                    f"Trailing stop triggered: {ticker} up {pl_pct:.1f}% from entry "
                                    f"but dropped {drop_from_high:.1f}% from its 60d high of "
                                    f"${recent_high:.2f}. Locking in profits."
                                ),
                                "portfolio_drawdown_pct": drawdown_pct,
                            }
                except Exception:
                    pass   # never let a data fetch error block risk operations

            if pl_pct >= PROFIT_TARGET_PCT:
                return {
                    "agent": "risk_manager", "ticker": ticker,
                    "veto": False, "force_sell": False, "take_profit": True,
                    "approved_position_size_pct": BASE_POSITION_PCT,
                    "reason": (
                        f"Profit target reached: {ticker} is up {pl_pct:.1f}% from entry. "
                        f"Taking profits (threshold: +{PROFIT_TARGET_PCT}%). "
                        "For strong uptrends the committee may override this."
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
