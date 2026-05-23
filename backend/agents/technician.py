"""
Technician agent — yfinance OHLCV + local indicator calculation.
Round 3 additions: ATR expansion ratio, volume conviction (up/down days),
SMA200 slope, Stage 2 uptrend flag, volume trend (institutional accumulation proxy).
"""
import json
import pandas as pd
import yfinance as yf
from backend.agents.base_agent import call_claude
from backend.data.indicators import (
    calc_rsi, calc_macd, calc_sma, calc_bbands,
    calc_atr, calc_volume_ratio, calc_adx, calc_roc,
)

SYSTEM_PROMPT = """You are the Technician on an AI investment committee hunting for 10X opportunities.
Return ONLY a valid JSON object — no markdown, no explanation, just JSON:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "1 plain-English sentence — name the single most important signal and what it means (e.g. 'Price is above its rising 200-day average with strong volume on up days — uptrend is healthy.')",
  "suggested_position_size_pct": 0-12,
  "momentum_score": 0.0-1.0
}

momentum_score: pure momentum grade — 1.0 = Stage 2 uptrend (above rising 200d MA, ADX>25, RS outperforming, high vol conviction), 0.0 = strong downtrend. 0.5 = neutral.

PRIORITY SIGNALS for 10X candidates (weight these heavily):

1. STAGE 2 UPTREND (most important): stage2_uptrend=True means price > 200d MA AND 200d MA is RISING. This is where ALL 10X moves happen. BUY with high confidence. Stage 2 ending (200d MA flattening/falling) = reduce exposure immediately.

2. ATR EXPANSION (early growth phase signal): atr_expansion_ratio > 1.3 means volatility expanding — typical of a stock entering explosive growth phase. Combine with positive momentum = strong BUY. Don't fear the volatility — it IS the opportunity.

3. VOLUME CONVICTION: vol_conviction_ratio (avg vol on up days / avg vol on down days):
   - > 2.0 = institutional money flowing in on strength = strong accumulation (very bullish)
   - > 1.5 = mild accumulation (bullish)
   - < 0.8 = distribution (bearish)

4. VOLUME TREND: vol_trend_pct (50d avg vol vs 150d avg vol):
   - > 20% = rising institutional interest (bullish)
   - < -20% = fading interest (bearish)

5. SMA200 SLOPE: sma200_slope_pct:
   - Rising (> +0.1%) = sustainable bull trend — ride it
   - Flat (0%) = caution
   - Falling (< -0.1%) = bear territory regardless of short-term price

6. RELATIVE STRENGTH vs SPY (rs_vs_spy_3m): > +10% means stock is outperforming market significantly = leadership stock (10X candidates always lead the market).

7. TREND FILTER: ADX > 25 = trending market (signals reliable). ADX < 20 = choppy (reduce confidence 40%).

8. MOMENTUM: RSI 50-70 in uptrend = healthy momentum. MACD histogram positive and expanding = BUY. ROC_20 > 10% = powerful momentum.

9. BREAKOUT: Near 52w high (< -3%) + volume_ratio > 1.5 = high-probability breakout. This is WHERE 10X candidates are often found.

10. WEEKLY RSI check: If daily RSI signals BUY but weekly RSI > 70, moderate confidence (higher-timeframe overbought).

Prefer high conviction on Stage 2 + volume confirmation. Low-ADX choppy markets = HOLD. Prefer SELL with low confidence over HOLD when bearish."""


def get_vote(ticker: str) -> dict:
    try:
        hist = yf.Ticker(ticker).history(period="252d")
        if hist.empty or len(hist) < 50:
            raise ValueError(f"Insufficient price history for {ticker}")

        closes  = hist["Close"]
        volumes = hist["Volume"]
        high    = hist["High"]
        low     = hist["Low"]

        rsi                            = calc_rsi(closes)
        macd, macd_signal, macd_hist   = calc_macd(closes)
        sma50                          = calc_sma(closes, 50)
        sma200                         = calc_sma(closes, 200)
        bb_upper, bb_middle, bb_lower  = calc_bbands(closes)
        atr                            = calc_atr(hist)
        volume_ratio                   = calc_volume_ratio(volumes)
        adx                            = calc_adx(hist)
        roc_20                         = calc_roc(closes, period=20)

        current_price     = round(float(closes.iloc[-1]), 4)
        week52_high       = round(float(high.max()), 4)
        week52_low        = round(float(low.min()), 4)
        pct_from_52w_high = round((current_price - week52_high) / week52_high * 100, 2) if week52_high else None
        pct_from_52w_low  = round((current_price - week52_low)  / week52_low  * 100, 2) if week52_low  else None
        atr_pct           = round(atr / current_price * 100, 2) if atr and current_price else None

        # ── Weekly RSI ────────────────────────────────────────────────────────
        rsi_weekly = None
        try:
            closes_weekly = closes.resample("W-FRI").last().dropna()
            rsi_weekly = calc_rsi(closes_weekly, period=14) if len(closes_weekly) >= 15 else None
        except Exception:
            pass

        # ── SMA200 slope: % change of 200d MA over last 21 trading days ──────
        # sma200 = closes.iloc[-200:].mean()
        # sma200_21d_ago = closes.iloc[-221:-21].mean()  (exactly 200 bars, ending 21 days ago)
        sma200_slope_pct = None
        try:
            if len(closes) >= 221 and sma200:
                sma200_21d_ago = float(closes.iloc[-221:-21].mean())
                if sma200_21d_ago > 0:
                    sma200_slope_pct = round((sma200 - sma200_21d_ago) / sma200_21d_ago * 100, 3)
        except Exception:
            pass

        # ── Stage 2 uptrend: price > 200d MA AND 200d MA is rising ───────────
        stage2_uptrend = bool(
            sma200 is not None and current_price > sma200
            and sma200_slope_pct is not None and sma200_slope_pct > 0
        )

        # ── ATR expansion ratio (current 14d ATR vs 50d avg of 14d ATR) ──────
        # > 1.3 = volatility expanding = early growth phase signal
        atr_expansion_ratio = None
        try:
            tr = pd.concat([
                high - low,
                (high - closes.shift()).abs(),
                (low  - closes.shift()).abs(),
            ], axis=1).max(axis=1)
            atr_rolling = tr.rolling(14).mean().dropna()
            if len(atr_rolling) >= 51:
                atr_50d_avg = float(atr_rolling.iloc[-51:-1].mean())
                atr_current = float(atr_rolling.iloc[-1])
                if atr_50d_avg > 0:
                    atr_expansion_ratio = round(atr_current / atr_50d_avg, 2)
        except Exception:
            pass

        # ── Volume conviction: avg volume on up-days vs down-days (20d) ──────
        # > 2.0 = institutional accumulation (strong bullish)
        vol_conviction_ratio = None
        try:
            last20 = hist.tail(21)  # 21 rows → 20 pairs after shift
            price_change = last20["Close"].diff().dropna()
            up_vol   = last20["Volume"].iloc[1:][price_change > 0]
            down_vol = last20["Volume"].iloc[1:][price_change < 0]
            if not up_vol.empty and not down_vol.empty:
                vol_conviction_ratio = round(float(up_vol.mean() / down_vol.mean()), 2)
        except Exception:
            pass

        # ── Volume trend: 50d avg vol vs 150d avg vol ─────────────────────────
        # Positive = rising institutional interest = accumulation
        vol_trend_pct = None
        try:
            if len(volumes) >= 150:
                avg_vol_50  = float(volumes.iloc[-50:].mean())
                avg_vol_150 = float(volumes.iloc[-150:].mean())
                if avg_vol_150 > 0:
                    vol_trend_pct = round((avg_vol_50 - avg_vol_150) / avg_vol_150 * 100, 1)
        except Exception:
            pass

        # ── Relative strength vs SPY (3-month) ───────────────────────────────
        rs_vs_spy_3m = None
        try:
            spy_closes = yf.Ticker("SPY").history(period="90d")["Close"]
            if len(spy_closes) >= 60 and len(closes) >= 60:
                spy_ret   = (spy_closes.iloc[-1] - spy_closes.iloc[0]) / spy_closes.iloc[0] * 100
                stock_ret = (closes.iloc[-1] - closes.iloc[-len(spy_closes)]) / closes.iloc[-len(spy_closes)] * 100
                rs_vs_spy_3m = round(float(stock_ret - spy_ret), 2)
        except Exception:
            pass

        # ── Last 5 bars ───────────────────────────────────────────────────────
        recent = hist.tail(5)
        price_action = [
            {"date": str(idx.date()), "close": round(float(row["Close"]), 4), "volume": int(row["Volume"])}
            for idx, row in recent.iterrows()
        ]

        market_data = {
            "ticker":                ticker,
            "current_price":         current_price,
            # Core momentum
            "rsi_14":                rsi,
            "rsi_weekly":            rsi_weekly,
            "macd":                  macd,
            "macd_signal":           macd_signal,
            "macd_hist":             macd_hist,
            "adx_14":                adx,
            "roc_20":                roc_20,
            # Moving averages
            "sma_50":                sma50,
            "sma_200":               sma200,
            "sma200_slope_pct":      sma200_slope_pct,
            # ★ 10X signals
            "stage2_uptrend":        stage2_uptrend,
            "atr_expansion_ratio":   atr_expansion_ratio,
            "vol_conviction_ratio":  vol_conviction_ratio,
            "vol_trend_pct":         vol_trend_pct,
            "rs_vs_spy_3m":          rs_vs_spy_3m,
            # Bands & volatility
            "bb_upper":              bb_upper,
            "bb_middle":             bb_middle,
            "bb_lower":              bb_lower,
            "atr_14":                atr,
            "atr_pct_of_price":      atr_pct,
            # Volume
            "volume_ratio_20d":      volume_ratio,
            # 52-week range
            "week52_high":           week52_high,
            "week52_low":            week52_low,
            "pct_from_52w_high":     pct_from_52w_high,
            "pct_from_52w_low":      pct_from_52w_low,
            "recent_price_action":   price_action,
        }

        vote = call_claude(
            SYSTEM_PROMPT,
            f"Technical analysis for {ticker}: {json.dumps(market_data)}",
            "technician",
        )
        # Inject current price so orchestrator can pass it to Chairman
        vote["current_price"] = current_price
        return vote
    except Exception as e:
        return {
            "agent": "technician", "ticker": ticker,
            "action": "HOLD", "confidence": 0.0,
            "rationale": f"Data fetch failed: {e}",
            "suggested_position_size_pct": 0,
            "current_price": None,
        }
