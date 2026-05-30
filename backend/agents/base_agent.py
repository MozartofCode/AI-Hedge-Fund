import os
import json
from datetime import date as _date
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Agents do simple JSON classification — Haiku is 12× cheaper and fast enough.
# Chairman (on-demand): Sonnet for quality prose when user explicitly requests analysis.
# Chairman (scheduled): Haiku — same JSON structure, 15× cheaper, fine for batch runs.
AGENT_MODEL             = "claude-haiku-4-5-20251001"
CHAIRMAN_MODEL          = "claude-sonnet-4-6"            # on-demand analysis (full quality)
CHAIRMAN_SCHEDULE_MODEL = "claude-haiku-4-5-20251001"    # scheduled batch runs (cost-optimised)

# ── Daily budget guard ────────────────────────────────────────────────────────
# Approximate cost per call (input ~1 500 tok + typical output).
# Haiku:  $0.80/MTok in + $4.00/MTok out  → ~$0.0018/call
# Sonnet: $3.00/MTok in + $15.00/MTok out → ~$0.010/call (scheduled 350-tok output)
#                                           → ~$0.014/call (on-demand 600-tok output)
_COST_ESTIMATE = {
    "claude-haiku-4-5-20251001": 0.0018,
    "claude-sonnet-4-6":         0.012,    # average of scheduled vs on-demand
}
DAILY_BUDGET_USD = float(os.getenv("DAILY_BUDGET_USD", "1.00"))

_budget: dict = {"date": "", "spent": 0.0}


def _track_cost(model: str) -> None:
    today = str(_date.today())
    if _budget["date"] != today:
        _budget["date"]  = today
        _budget["spent"] = 0.0
    _budget["spent"] = round(_budget["spent"] + _COST_ESTIMATE.get(model, 0.002), 6)


def is_over_daily_budget() -> bool:
    """Return True if today's estimated Claude spend has reached the daily cap."""
    today = str(_date.today())
    if _budget["date"] != today:
        return False
    return _budget["spent"] >= DAILY_BUDGET_USD


def get_daily_spend() -> float:
    """Return today's estimated spend in USD (resets at midnight UTC)."""
    today = str(_date.today())
    return round(_budget["spent"], 4) if _budget["date"] == today else 0.0


_HOLD_FALLBACK = {
    "action": "HOLD",
    "confidence": 0.0,
    "rationale": "Agent failed to produce a vote — defaulting to HOLD.",
    "suggested_position_size_pct": 0,
}

STUB_SYSTEM_PROMPT = """You are a stub AI trading agent used for Phase 1 end-to-end testing.
Return ONLY a valid JSON object with no markdown, no explanation — just the JSON:
{
  "action": "BUY",
  "confidence": 0.75,
  "rationale": "Test vote from base agent stub.",
  "suggested_position_size_pct": 3
}"""


def call_claude(
    system_prompt: str,
    user_prompt: str,
    agent_name: str,
    max_tokens: int = 150,
    model: str = AGENT_MODEL,
) -> dict:
    # Hard daily budget cap — return HOLD fallback rather than overspend.
    if is_over_daily_budget():
        vote = _HOLD_FALLBACK.copy()
        vote["agent"]    = agent_name
        vote["rationale"] = (
            f"Daily budget cap ${DAILY_BUDGET_USD:.2f} reached "
            f"(est. spent ${get_daily_spend():.4f}). Defaulting to HOLD."
        )
        print(f"[budget] cap reached — skipping {agent_name} call (spent ${get_daily_spend():.4f})")
        return vote

    try:
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        vote = json.loads(raw)
        vote["agent"] = agent_name
        _track_cost(model)
        return vote
    except Exception as e:
        vote = _HOLD_FALLBACK.copy()
        vote["agent"] = agent_name
        vote["rationale"] = f"Agent error: {e}"
        return vote


def get_stub_vote(ticker: str) -> dict:
    return call_claude(
        system_prompt=STUB_SYSTEM_PROMPT,
        user_prompt=f"Provide a test vote for ticker: {ticker}",
        agent_name="base_agent_stub",
    )
