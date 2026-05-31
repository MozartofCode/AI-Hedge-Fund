"""
FX Macro Agent — dollar index trend, risk-on/off, safe-haven flows, commodity signals.

Key signals hedge funds watch:
- DXY trend: rising DXY = headwind for EUR/GBP/AUD, tailwind for USD/JPY
- VIX/risk-off: VIX > 20 → buy safe havens (JPY, CHF); sell risk currencies (AUD, NZD, MXN)
- Oil prices: rising oil = bullish CAD and AUD (commodity exporters)
- Gold: rising gold = mild USD negative
Uses the shared macro snapshot from forex_client (cached 30 min).
"""
import json
from backend.agents.base_agent import call_claude
from backend.data.forex_client import get_macro_snapshot, parse_pair_currencies

SYSTEM_PROMPT = """You are the FX Macro Analyst on an AI forex trading committee.
Return ONLY valid JSON — no markdown, no explanation:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "1 plain-English sentence about the macro backdrop for this currency pair (e.g. 'The US dollar is strengthening on rising interest rate expectations, which makes selling euros against dollars look attractive.')",
  "suggested_position_size_pct": 0-8,
  "risk_sentiment": "risk_on" | "risk_off" | "neutral"
}

BUY = long the base currency. SELL = short the base currency.

USD PAIRS (EURUSD, GBPUSD, AUDUSD, NZDUSD — USD is the quote currency):
- DXY rising → USD strengthening → SELL (sell base, hold USD)
- DXY falling → USD weakening → BUY (buy base against weak USD)

USD-BASE PAIRS (USDJPY, USDCHF, USDCAD, USDMXN — USD is the base currency):
- DXY rising → BUY (buy USD, it's appreciating)
- DXY falling → SELL (sell USD)

CROSS PAIRS (EURJPY, GBPJPY — no USD):
- Risk-off (VIX > 20) → JPY strengthens → SELL EURJPY/GBPJPY
- Risk-on (VIX < 15, SPY healthy) → JPY weakens → BUY EURJPY/GBPJPY

SAFE HAVEN RULE:
- risk_sentiment=risk_off: favor JPY and CHF (they rally in fear). Avoid AUD, NZD, MXN.
- risk_sentiment=risk_on: favor AUD, NZD (higher yield, risk-on currencies). Sell JPY.

COMMODITY RULE:
- oil_20d_roc > +5%: bullish for CAD (Canada exports oil) and AUD (global growth proxy)
- gold_20d_roc > +5%: mild USD negative signal"""


# Classify each pair's relationship to USD and commodity sensitivity
_PAIR_CONTEXT = {
    "EURUSD": {"type": "usd_quote",  "safe_haven_base": False, "safe_haven_quote": False},
    "GBPUSD": {"type": "usd_quote",  "safe_haven_base": False, "safe_haven_quote": False},
    "USDJPY": {"type": "usd_base",   "safe_haven_base": False, "safe_haven_quote": True},
    "AUDUSD": {"type": "usd_quote",  "safe_haven_base": False, "safe_haven_quote": False,  "commodity": "oil_gold"},
    "USDCHF": {"type": "usd_base",   "safe_haven_base": False, "safe_haven_quote": True},
    "USDCAD": {"type": "usd_base",   "safe_haven_base": False, "safe_haven_quote": False,  "commodity": "oil"},
    "NZDUSD": {"type": "usd_quote",  "safe_haven_base": False, "safe_haven_quote": False},
    "EURJPY": {"type": "cross",      "safe_haven_base": False, "safe_haven_quote": True},
    "GBPJPY": {"type": "cross",      "safe_haven_base": False, "safe_haven_quote": True},
    "USDMXN": {"type": "usd_base",   "safe_haven_base": False, "safe_haven_quote": False},
}


def get_vote(pair: str) -> dict:
    try:
        macro = get_macro_snapshot()
        base, quote = parse_pair_currencies(pair)
        ctx = _PAIR_CONTEXT.get(pair.upper(), {"type": "unknown"})

        # Build DXY directional signal for this pair
        dxy_trend = macro.get("dxy_trend", "flat")
        if ctx["type"] == "usd_quote":
            dxy_impact = "bearish" if dxy_trend == "rising" else ("bullish" if dxy_trend == "falling" else "neutral")
        elif ctx["type"] == "usd_base":
            dxy_impact = "bullish" if dxy_trend == "rising" else ("bearish" if dxy_trend == "falling" else "neutral")
        else:
            dxy_impact = "neutral"  # cross pairs

        # Risk-sentiment signal
        risk = macro.get("risk_sentiment", "neutral")
        risk_impact = "neutral"
        if ctx.get("safe_haven_quote"):          # JPY/CHF as quote (e.g. USDJPY, USDCHF)
            risk_impact = "bearish" if risk == "risk_off" else ("bullish" if risk == "risk_on" else "neutral")
        elif ctx["type"] == "cross" and ctx.get("safe_haven_quote"):
            risk_impact = "bearish" if risk == "risk_off" else "bullish"
        elif pair.upper() in ("AUDUSD", "NZDUSD", "USDMXN"):
            risk_impact = "bullish" if risk == "risk_on" else ("bearish" if risk == "risk_off" else "neutral")

        # Commodity signal
        commodity_impact = "neutral"
        commodity = ctx.get("commodity")
        oil_roc  = macro.get("oil_20d_roc") or 0
        gold_roc = macro.get("gold_20d_roc") or 0
        if commodity == "oil" and ctx["type"] == "usd_base":   # USDCAD
            commodity_impact = "bearish" if oil_roc > 5 else ("bullish" if oil_roc < -5 else "neutral")
        elif commodity == "oil_gold" and ctx["type"] == "usd_quote":  # AUDUSD
            commodity_impact = "bullish" if (oil_roc > 5 or gold_roc > 5) else "neutral"

        market_data = {
            "pair":             pair,
            "base_currency":    base,
            "quote_currency":   quote,
            "pair_type":        ctx.get("type"),
            "dxy_current":      macro.get("dxy_current"),
            "dxy_trend":        dxy_trend,
            "dxy_1w_change_pct": macro.get("dxy_1w_change_pct"),
            "dxy_impact_on_pair": dxy_impact,
            "vix":              macro.get("vix"),
            "risk_sentiment":   risk,
            "risk_impact_on_pair": risk_impact,
            "oil_20d_roc":      macro.get("oil_20d_roc"),
            "gold_20d_roc":     macro.get("gold_20d_roc"),
            "commodity_impact": commodity_impact,
            "spy_above_200d":   macro.get("spy_above_200d"),
        }

        vote = call_claude(
            SYSTEM_PROMPT,
            f"Macro analysis for {pair}: {json.dumps(market_data)}",
            "fx_macro",
        )
        vote["risk_sentiment"] = vote.get("risk_sentiment", risk)
        return vote

    except Exception as e:
        print(f"[fx_macro] {pair} failed: {e}")
        return {
            "agent":  "fx_macro",
            "pair":   pair,
            "action": "HOLD",
            "confidence": 0.0,
            "rationale":  f"Macro data unavailable: {e}",
            "suggested_position_size_pct": 0,
            "risk_sentiment": "neutral",
        }
