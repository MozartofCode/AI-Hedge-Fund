"""
Calculate technical indicators from a pandas Close price Series.
No API key required — pure math on yfinance OHLCV data.
"""
import pandas as pd


def calc_rsi(closes: pd.Series, period: int = 14):
    if len(closes) < period + 1:
        return None
    delta = closes.diff()
    gain = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs = gain / loss
    rsi = (100 - (100 / (1 + rs))).iloc[-1]
    return round(float(rsi), 4) if not pd.isna(rsi) else None


def calc_macd(closes: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    if len(closes) < slow + signal:
        return None, None, None
    ema_fast   = closes.ewm(span=fast,   adjust=False).mean()
    ema_slow   = closes.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist        = macd_line - signal_line

    def _last(s):
        v = s.iloc[-1]
        return round(float(v), 6) if not pd.isna(v) else None

    return _last(macd_line), _last(signal_line), _last(hist)


def calc_sma(closes: pd.Series, period: int):
    if len(closes) < period:
        return None
    val = closes.rolling(period).mean().iloc[-1]
    return round(float(val), 4) if not pd.isna(val) else None


def calc_bbands(closes: pd.Series, period: int = 20, num_std: float = 2.0):
    if len(closes) < period:
        return None, None, None
    sma   = closes.rolling(period).mean()
    std   = closes.rolling(period).std()
    upper = (sma + num_std * std).iloc[-1]
    mid   = sma.iloc[-1]
    lower = (sma - num_std * std).iloc[-1]

    def _r(v):
        return round(float(v), 4) if not pd.isna(v) else None

    return _r(upper), _r(mid), _r(lower)


def calc_atr(hist: pd.DataFrame, period: int = 14):
    """Average True Range — measures volatility independent of price level."""
    if len(hist) < period + 1:
        return None
    high  = hist["High"]
    low   = hist["Low"]
    close = hist["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    return round(float(atr), 4) if not pd.isna(atr) else None


def calc_volume_ratio(volumes: pd.Series, period: int = 20):
    """Current volume vs N-day average. >1.5 = notable spike, <0.5 = quiet."""
    if len(volumes) < period + 1:
        return None
    avg  = volumes.rolling(period).mean().iloc[-1]
    curr = volumes.iloc[-1]
    if avg <= 0:
        return None
    return round(float(curr / avg), 2)


def calc_adx(hist: pd.DataFrame, period: int = 14):
    """
    Average Directional Index — trend strength (not direction).
    >25 = trending market (signals reliable), <20 = choppy (signals noisy).
    """
    if len(hist) < period * 2 + 1:
        return None
    high  = hist["High"]
    low   = hist["Low"]
    close = hist["Close"]

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)

    up_move   = high.diff()
    down_move = -low.diff()
    plus_dm   = up_move.where(  (up_move > down_move) & (up_move > 0),   0.0)
    minus_dm  = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    alpha    = 1.0 / period
    atr_w    = tr.ewm(       alpha=alpha, adjust=False).mean()
    plus_di  = 100 * plus_dm.ewm( alpha=alpha, adjust=False).mean() / atr_w
    minus_di = 100 * minus_dm.ewm(alpha=alpha, adjust=False).mean() / atr_w

    denom = (plus_di + minus_di).replace(0, float("nan"))
    dx    = 100 * (plus_di - minus_di).abs() / denom
    adx   = dx.ewm(alpha=alpha, adjust=False).mean().iloc[-1]
    return round(float(adx), 2) if not pd.isna(adx) else None


def calc_roc(closes: pd.Series, period: int = 20):
    """Rate of Change — % price change over N periods. Positive = upward momentum."""
    if len(closes) < period + 1:
        return None
    base = closes.iloc[-(period + 1)]
    roc  = (closes.iloc[-1] - base) / base * 100
    return round(float(roc), 2) if not pd.isna(roc) else None
