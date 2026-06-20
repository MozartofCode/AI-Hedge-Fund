import os
import json
from datetime import date as _date
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# ── LLM clients ────────────────────────────────────────────────────────────────
# Two providers are supported:
#   • "anthropic" (Claude)  — Haiku fallback for the committee when Groq is off.
#   • "groq"      (Llama …) — used for the automatic/scheduled trader (free/cheap).
# Pick the automatic trader's provider with SCHEDULED_PROVIDER ("groq" | "anthropic").
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))   # legacy alias
anthropic_client = client

try:
    from groq import Groq
    _groq_key = os.getenv("GROQ_API_KEY")
    groq_client = Groq(api_key=_groq_key) if _groq_key else None
except ImportError:
    groq_client = None

# Agents do simple JSON classification — Haiku is 12× cheaper and fast enough.
# Chairman (scheduled): Haiku — same JSON structure, 15× cheaper, fine for batch runs.
AGENT_MODEL             = "claude-haiku-4-5-20251001"
CHAIRMAN_SCHEDULE_MODEL = "claude-haiku-4-5-20251001"    # scheduled batch runs (Claude fallback)

# ── Groq config (automatic trader) ─────────────────────────────────────────────
# llama-3.3-70b-versatile is fast, supports JSON mode, and is on Groq's free tier.
GROQ_AGENT_MODEL    = os.getenv("GROQ_AGENT_MODEL",    "llama-3.3-70b-versatile")
GROQ_CHAIRMAN_MODEL = os.getenv("GROQ_CHAIRMAN_MODEL", "llama-3.3-70b-versatile")

# Which provider the AUTOMATIC/scheduled trader uses. Default "groq" to save money.
SCHEDULED_PROVIDER  = os.getenv("SCHEDULED_PROVIDER", "groq").lower()


def scheduled_agent_config() -> tuple[str, str]:
    """(model, provider) the scheduled trader's data agents should use."""
    if SCHEDULED_PROVIDER == "groq" and groq_client is not None:
        return GROQ_AGENT_MODEL, "groq"
    return AGENT_MODEL, "anthropic"


def scheduled_chairman_config() -> tuple[str, str]:
    """(model, provider) the scheduled trader's Chairman should use."""
    if SCHEDULED_PROVIDER == "groq" and groq_client is not None:
        return GROQ_CHAIRMAN_MODEL, "groq"
    return CHAIRMAN_SCHEDULE_MODEL, "anthropic"

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


def _track_cost(model: str, provider: str = "anthropic") -> None:
    # Groq usage is free / negligible — only Claude spend counts toward the cap.
    if provider != "anthropic":
        return
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


def call_llm(
    system_prompt: str,
    user_prompt: str,
    agent_name: str,
    max_tokens: int = 150,
    model: str = None,
    provider: str = "anthropic",
) -> dict:
    """
    Provider-agnostic LLM call returning a parsed JSON vote dict.
    provider: "anthropic" (Claude) or "groq" (Llama via Groq).
    If model is None it defaults to the right model for the provider.
    """
    provider = (provider or "anthropic").lower()
    if model is None:
        model = GROQ_AGENT_MODEL if provider == "groq" else AGENT_MODEL

    # Hard daily budget cap applies to PAID Claude calls only.
    if provider == "anthropic" and is_over_daily_budget():
        vote = _HOLD_FALLBACK.copy()
        vote["agent"]    = agent_name
        vote["rationale"] = (
            f"Daily budget cap ${DAILY_BUDGET_USD:.2f} reached "
            f"(est. spent ${get_daily_spend():.4f}). Defaulting to HOLD."
        )
        print(f"[budget] cap reached — skipping {agent_name} call (spent ${get_daily_spend():.4f})")
        return vote

    try:
        if provider == "groq":
            if groq_client is None:
                raise RuntimeError("GROQ_API_KEY not set — cannot use the Groq provider")
            resp = groq_client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0.3,
                response_format={"type": "json_object"},   # force valid JSON
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            )
            raw = (resp.choices[0].message.content or "").strip()
        else:
            message = anthropic_client.messages.create(
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
        _track_cost(model, provider)
        return vote
    except Exception as e:
        vote = _HOLD_FALLBACK.copy()
        vote["agent"] = agent_name
        vote["rationale"] = f"Agent error: {e}"
        return vote


def call_claude(
    system_prompt: str,
    user_prompt: str,
    agent_name: str,
    max_tokens: int = 150,
    model: str = None,
    provider: str = "anthropic",
) -> dict:
    """Backwards-compatible wrapper. Delegates to call_llm."""
    return call_llm(system_prompt, user_prompt, agent_name, max_tokens, model, provider)
