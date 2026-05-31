"""
FX Carry Agent — interest rate differential (carry trade) signal.

The carry trade is one of the most widely-used hedge fund forex strategies:
borrow in a low-interest-rate currency, invest in a high-rate currency.
e.g. long USDJPY: USD yields ~5.25%, JPY yields ~0.10% → +5.15% carry/year.

This agent combines carry with trend (carry works best in trending markets).
Receives momentum_score from fx_technician to assess trend strength.
"""
import json
from backend.agents.base_agent import call_claude
from backend.data.forex_client import CENTRAL_BANK_RATES, parse_pair_currencies

SYSTEM_PROMPT = """You are the FX Carry Specialist on an AI forex trading committee.
Return ONLY valid JSON — no markdown, no explanation:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "rationale": "1 plain-English sentence about the carry opportunity (e.g. 'Holding USDJPY long earns over 5% per year in interest rate differential, and the trend supports the carry trade.')",
  "suggested_position_size_pct": 0-8,
  "carry_signal": "positive" | "negative" | "neutral"
}

BUY = go long the base currency (earn positive carry).
SELL = go short the base currency (avoid paying negative carry).

carry_differential = base_currency_rate - quote_currency_rate (annualized %)

Carry signal thresholds:
- > +2.0%: Strong positive carry → BUY with high confidence (0.7-0.9)
- +0.5% to +2.0%: Mild positive carry → BUY with moderate confidence (0.55-0.7)
- -0.5% to +0.5%: Negligible carry → HOLD (carry alone doesn't justify position)
- -0.5% to -2.0%: Negative carry → SELL with moderate confidence (0.55-0.65)
- < -2.0%: Strong negative carry → SELL with high confidence (0.7-0.85)

IMPORTANT: Carry works best in trending markets. Adjust confidence:
- momentum_score > 0.65: +0.10 to confidence (trend supports carry)
- momentum_score 0.45-0.65: no adjustment (neutral trend, carry stands on its own)
- momentum_score < 0.45: -0.15 from confidence (counter-trend carry is risky)

Central bank divergence amplifier: if one bank is hiking and the other is cutting/pausing,
the carry differential is widening → increase confidence by 0.10."""


def get_vote(pair: str, momentum_score: float = 0.5) -> dict:
    try:
        base, quote = parse_pair_currencies(pair)

        base_rate  = CENTRAL_BANK_RATES.get(base,  0.0)
        quote_rate = CENTRAL_BANK_RATES.get(quote, 0.0)
        carry_diff = round(base_rate - quote_rate, 2)

        # Classify carry signal
        if carry_diff > 0.5:
            carry_signal = "positive"
        elif carry_diff < -0.5:
            carry_signal = "negative"
        else:
            carry_signal = "neutral"

        market_data = {
            "pair":                pair,
            "base_currency":       base,
            "quote_currency":      quote,
            "base_rate_pct":       base_rate,
            "quote_rate_pct":      quote_rate,
            "carry_differential":  carry_diff,
            "carry_signal":        carry_signal,
            "momentum_score":      round(momentum_score, 3),
            "interpretation": (
                f"Going long {base} earns {carry_diff:+.2f}% annually "
                f"vs holding {quote} ({base_rate}% - {quote_rate}%)"
            ),
        }

        vote = call_claude(
            SYSTEM_PROMPT,
            f"Carry trade analysis for {pair}: {json.dumps(market_data)}",
            "fx_carry",
        )
        # Inject carry data for orchestrator/frontend
        vote["carry_differential"] = carry_diff
        vote["base_rate"]          = base_rate
        vote["quote_rate"]         = quote_rate
        vote["carry_signal"]       = vote.get("carry_signal", carry_signal)
        return vote

    except Exception as e:
        print(f"[fx_carry] {pair} failed: {e}")
        return {
            "agent":  "fx_carry",
            "pair":   pair,
            "action": "HOLD",
            "confidence": 0.0,
            "rationale":  f"Carry data unavailable: {e}",
            "suggested_position_size_pct": 0,
            "carry_differential": 0.0,
            "carry_signal": "neutral",
        }
