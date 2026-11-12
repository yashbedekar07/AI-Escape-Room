"""The LLM narrator: turns the engine's factual Result into atmospheric text.

The narrator never sees the player's raw message or any puzzle solution. It only receives a
neutral summary of the attempted action and the Result decided by Python, so it has nothing
to leak and no instructions from the player to follow. If the LLM fails, or its text contains
numbers that are not in the Result, the plain Result message is shown instead.
"""

import re

from google.genai import types

from llm import MODEL, get_client
from rules import Result

NARRATOR_PROMPT = """You are the narrator of a text-based escape room game set in a locked library.
You receive the RESULT of the player's last action, decided by the game engine.
Rewrite it as 2-4 atmospheric sentences, speaking to the player as "you".

Strict rules:
- The RESULT is the only truth. Do not add objects, items, events or outcomes that are not in it.
- If the OUTCOME is FAILED, describe the failure. Never say that a lock opens, the door opens or
  the player escapes unless the RESULT says so.
- Copy every number exactly as it appears in the RESULT, and do not add any other numbers.
- Do not give hints or solutions beyond what the RESULT contains.
"""


def describe_attempt(action: dict) -> str:
    """Neutral summary of the action, built from the parsed fields only."""
    parts = [action["action"].replace("_", " ")]
    if action.get("item"):
        parts.append(f"item={action['item']}")
    if action.get("target"):
        parts.append(f"target={action['target']}")
    if action.get("code"):
        parts.append(f"code={action['code']}")
    return ", ".join(parts)


def _plain_text(result: Result) -> str:
    return result.message.replace("The player", "You").replace("the player", "you")


def is_safe(narration: str, result: Result) -> bool:
    """Reject narration that invents numbers (e.g. a hallucinated code)."""
    allowed = set(re.findall(r"\d", result.message + (result.clue or "")))
    return set(re.findall(r"\d", narration)) <= allowed


def narrate(action: dict, result: Result) -> tuple[str, str]:
    """Return (text, source) where source is "llm" or "fallback"."""
    prompt = (
        f"PLAYER ATTEMPTED: {describe_attempt(action)}\n"
        f"OUTCOME: {'SUCCESS' if result.success else 'FAILED'}\n"
        f"RESULT: {result.message}"
    )
    if result.clue:
        prompt += f"\nCLUE DISCOVERED (include it word for word): {result.clue}"

    try:
        response = get_client().models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=NARRATOR_PROMPT, temperature=0.7),
        )
        text = (response.text or "").strip()
        if text and is_safe(text, result):
            return text, "llm"
    except Exception:
        pass
    return _plain_text(result), "fallback"
