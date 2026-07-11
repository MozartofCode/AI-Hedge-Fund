import os
import json
from dotenv import load_dotenv

load_dotenv()

# ── LLM client ────────────────────────────────────────────────────────────────
# Groq (Llama) is the sole LLM provider — free tier, used by every agent and
# the Chairman.
try:
    from groq import Groq
    _groq_key = os.getenv("GROQ_API_KEY")
    groq_client = Groq(api_key=_groq_key) if _groq_key else None
except ImportError:
    groq_client = None

# llama-3.3-70b-versatile is fast, supports JSON mode, and is on Groq's free tier.
AGENT_MODEL             = os.getenv("GROQ_AGENT_MODEL",    "llama-3.3-70b-versatile")
CHAIRMAN_SCHEDULE_MODEL = os.getenv("GROQ_CHAIRMAN_MODEL", "llama-3.3-70b-versatile")


def scheduled_agent_config() -> tuple[str, str]:
    """(model, provider) the scheduled trader's data agents should use."""
    return AGENT_MODEL, "groq"


def scheduled_chairman_config() -> tuple[str, str]:
    """(model, provider) the scheduled trader's Chairman should use."""
    return CHAIRMAN_SCHEDULE_MODEL, "groq"


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
    provider: str = "groq",
) -> dict:
    """
    Groq (Llama) LLM call returning a parsed JSON vote dict.
    If model is None it defaults to AGENT_MODEL.
    """
    if model is None:
        model = AGENT_MODEL

    try:
        if groq_client is None:
            raise RuntimeError("GROQ_API_KEY not set — cannot call the LLM")
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

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        vote = json.loads(raw)
        vote["agent"] = agent_name
        return vote
    except Exception as e:
        vote = _HOLD_FALLBACK.copy()
        vote["agent"] = agent_name
        vote["rationale"] = f"Agent error: {e}"
        return vote
