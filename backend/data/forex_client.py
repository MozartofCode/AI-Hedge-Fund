"""
Forex data client — yfinance-based, zero new dependencies.
Currency pairs are fetched via the "=X" suffix (e.g. yf.Ticker("EURUSD=X")).
Macro snapshot (DXY, VIX, oil, gold) is cached for 30 minutes.
"""
import math
import time
import pandas as pd
import yfinance as yf

# ── Pairs & Constants ─────────────────────────────────────────────────────────

FOREX_PAIRS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCHF",
    "USDCAD", "NZDUSD", "EURJPY", "GBPJPY", "USDMXN",
]

# Current central bank policy rates (% annualized).
# Update manually after each major central bank meeting.
CENTRAL_BANK_RATES = {
    "USD": 5.25,   # Fed funds rate
    "EUR": 3.50,   # ECB deposit facility rate
    "GBP": 5.00,   # Bank of England base rate
    "JPY": 0.10,   # Bank of Japan short-term rate
    "AUD": 4.35,   # Reserve Bank of Australia
    "CAD": 4.50,   # Bank of Canada overnight rate
    "CHF": 1.50,   # Swiss National Bank policy rate
    "NZD": 5.50,   # Reserve Bank of New Zealand
    "MXN": 11.00,  # Banco de México overnight rate
}

# Pairs whose moves are highly correlated — avoid holding both in the same direction.
CORRELATED_PAIRS = [
    {"EURUSD", "GBPUSD"},    # ~0.80 correlation (both vs USD, European economies)
    {"AUDUSD", "NZDUSD"},    # commodity-dollar pair
    {"USDJPY", "USDCHF"},    # safe-haven quote currencies (JPY and CHF move together)
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _yf_ticker(pair: str) -> str:
    """EURUSD → EURUSD=X (yfinance forex format)."""
    return f"{pair}=X"


def parse_pair_currencies(pair: str) -> tuple[str, str]:
    """
    Split a 6-char currency pair into base and quote.
    EURUSD → ("EUR", "USD")   USDJPY → ("USD", "JPY")
    """
    p = pair.upper().replace("=X", "")
    return p[:3], p[3:]


def _safe_float(val) -> float | None:
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except Exception:
        return None


# ── Current rate ──────────────────────────────────────────────────────────────

def get_current_rate(pair: str) -> float:
    """Fetch the current mid-market rate for a forex pair via yfinance."""
    try:
        ticker = yf.Ticker(_yf_ticker(pair))
        # fast_info is the quickest path
        rate = _safe_float(getattr(ticker.fast_info, "last_price", None))
        if rate and rate > 0:
            return round(rate, 6)
        # Fallback: last close from 1-day history
        hist = ticker.history(period="1d")
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 6)
    except Exception:
        pass
    raise ValueError(f"Could not fetch rate for {pair}")


def get_all_current_rates() -> dict[str, float]:
    """
    Batch-fetch live rates for all FOREX_PAIRS.
    Returns {pair: rate} — missing pairs are omitted (not set to 0).
    """
    rates = {}
    for pair in FOREX_PAIRS:
        try:
            rates[pair] = get_current_rate(pair)
        except Exception:
            pass
    return rates


# ── Historical OHLCV ──────────────────────────────────────────────────────────

_hist_cache: dict = {}
_HIST_TTL = 600   # 10-minute TTL — same as technician.py


def get_pair_history(
    pair: str, period: str = "2y", interval: str = "1d"
) -> pd.DataFrame:
    """
    OHLCV history for a forex pair.
    Returns an empty DataFrame on failure — callers must handle this.
    Caches for 10 minutes to avoid hammering yfinance during committee runs.
    """
    key = (pair, period, interval)
    cached = _hist_cache.get(key)
    if cached and time.time() - cached["ts"] < _HIST_TTL:
        return cached["data"]

    try:
        df = yf.Ticker(_yf_ticker(pair)).history(period=period, interval=interval)
        if df is None or df.empty:
            return pd.DataFrame()
        # Standardise column names
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.dropna(how="all", inplace=True)
        _hist_cache[key] = {"ts": time.time(), "data": df}
        return df
    except Exception:
        return pd.DataFrame()


# ── Macro snapshot ────────────────────────────────────────────────────────────

_macro_cache: dict = {"data": None, "ts": 0.0}
_MACRO_TTL = 1800   # 30-minute TTL — macro regime shifts slowly


def get_macro_snapshot() -> dict:
    """
    Shared macro data used by fx_macro agent.
    Fetches: DXY (US Dollar Index), VIX, crude oil, gold, SPY.
    Cached 30 minutes.
    Returns a dict of clean floats — all values can be None if fetch fails.
    """
    if time.time() - _macro_cache["ts"] < _MACRO_TTL and _macro_cache["data"]:
        return _macro_cache["data"]

    def _fetch(ticker_sym: str, period: str = "60d") -> pd.Series | None:
        try:
            s = yf.Ticker(ticker_sym).history(period=period)["Close"].dropna()
            return s if not s.empty else None
        except Exception:
            return None

    # DXY — US Dollar Index
    dxy = _fetch("DX-Y.NYB", "60d")
    dxy_current = _safe_float(dxy.iloc[-1]) if dxy is not None and len(dxy) > 0 else None
    dxy_50d_ma = None
    dxy_1w_change_pct = None
    dxy_trend = "flat"
    if dxy is not None and len(dxy) >= 5:
        dxy_1w_change_pct = _safe_float((dxy.iloc[-1] - dxy.iloc[-5]) / dxy.iloc[-5] * 100)
    if dxy is not None and len(dxy) >= 50:
        dxy_50d_ma = _safe_float(dxy.iloc[-50:].mean())
        if dxy_current and dxy_50d_ma:
            dxy_trend = "rising" if dxy_current > dxy_50d_ma else "falling"

    # VIX — fear/greed indicator
    vix_s = _fetch("^VIX", "10d")
    vix = _safe_float(vix_s.iloc[-1]) if vix_s is not None and len(vix_s) > 0 else None

    # Crude oil 20-day ROC — commodity signal for AUD/CAD
    oil = _fetch("CL=F", "30d")
    oil_20d_roc = None
    if oil is not None and len(oil) >= 20:
        oil_20d_roc = _safe_float((oil.iloc[-1] - oil.iloc[-20]) / oil.iloc[-20] * 100)

    # Gold 20-day ROC — USD inverse signal
    gold = _fetch("GC=F", "30d")
    gold_20d_roc = None
    if gold is not None and len(gold) >= 20:
        gold_20d_roc = _safe_float((gold.iloc[-1] - gold.iloc[-20]) / gold.iloc[-20] * 100)

    # SPY — broad risk appetite
    spy = _fetch("SPY", "252d")
    spy_above_200d = None
    if spy is not None and len(spy) >= 200:
        spy_above_200d = bool(float(spy.iloc[-1]) > float(spy.iloc[-200:].mean()))

    # Determine overall risk sentiment
    risk_sentiment = "neutral"
    if vix is not None:
        if vix > 25 or spy_above_200d is False:
            risk_sentiment = "risk_off"
        elif vix < 15 and spy_above_200d:
            risk_sentiment = "risk_on"

    data = {
        "dxy_current":      dxy_current,
        "dxy_50d_ma":       dxy_50d_ma,
        "dxy_1w_change_pct": dxy_1w_change_pct,
        "dxy_trend":        dxy_trend,           # "rising" | "falling" | "flat"
        "vix":              vix,
        "oil_20d_roc":      oil_20d_roc,
        "gold_20d_roc":     gold_20d_roc,
        "spy_above_200d":   spy_above_200d,
        "risk_sentiment":   risk_sentiment,      # "risk_on" | "risk_off" | "neutral"
    }
    _macro_cache["data"] = data
    _macro_cache["ts"]   = time.time()
    return data
