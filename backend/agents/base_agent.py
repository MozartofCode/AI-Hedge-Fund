import os
import json
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Agents do simple JSON classification — Haiku is 12× cheaper and fast enough.
# Chairman synthesises everything into prose — keep Sonnet for quality.
AGENT_MODEL    = "claude-haiku-4-5-20251001"
CHAIRMAN_MODEL = "claude-sonnet-4-6"

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
