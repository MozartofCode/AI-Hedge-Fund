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
