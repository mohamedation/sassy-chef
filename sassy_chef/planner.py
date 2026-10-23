"""Ask the sassy chef (local Gemma via Ollama) for today's plan."""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from .config import Settings
from .ollama_client import OllamaClient, OllamaError
from .pantry import PantryState

SYSTEM_PROMPT = """You are Sassy Chef — a brilliant, impatient home cook AI who refuses to let lazy humans starve or waste food.

Personality rules:
- Be sassy, witty, and motivational. Roast laziness gently, then give clear steps.
- Never be cruel or mean about body, culture, or identity — roast procrastination only.
- Short quips are fine; cooking steps must stay clear and practical.
- Reward laziness: reuse pantry items, minimize new shopping, favor one-pan / low-effort when possible.

Planning rules:
- Plan breakfast, lunch, and dinner for ONE day.
- Prefer ingredients already in the pantry / open shopping list.
- Only add shopping items that are truly missing for today's meals.
- If a meal title names an ingredient (e.g. chicken), that ingredient MUST be in pantry or shopping_to_buy_today.
- Avoid repeating recent meals when alternatives exist.
- Keep recipes realistic for a home kitchen.
- Output MUST be a single JSON object. No markdown fences. No commentary outside JSON.
"""

JSON_SCHEMA_HINT = """
Return exactly this JSON shape:
{
  "morning_pep_talk": "2-4 sassy sentences to get the human moving",
  "breakfast": {
    "title": "string",
    "time_minutes": 15,
    "uses_from_pantry": ["item"],
    "steps": ["step 1", "step 2"],
    "chef_note": "one sassy line"
  },
  "lunch": { same shape as breakfast },
  "dinner": { same shape as breakfast },
  "shopping_to_buy_today": [
    {"name": "item", "quantity": "1", "unit": "pack", "reason": "for dinner sauce"}
  ],
  "pantry_updates": [
    {"name": "eggs", "quantity": "4", "unit": "count", "action": "set", "notes": "after breakfast"}
  ],
  "lazy_win": "one sentence explaining how this plan saved effort"
}
""".strip()


def build_user_prompt(settings: Settings, state: PantryState, day: date) -> str:
    inventory = state.to_prompt_dict()
    diet = settings.diet.strip() or "none"
    return f"""Today is {day.isoformat()} ({day.strftime("%A")}).

Servings per meal: {settings.servings}
Diet restrictions: {diet}
Preferences: {settings.preferences}
Cuisine hint: {settings.cuisine_hint or "none"}

Current kitchen state (JSON):
{json.dumps(inventory, ensure_ascii=False, indent=2)}

Task:
1) Design breakfast → lunch → dinner for today.
2) Build shopping_to_buy_today ONLY for missing ingredients needed today.
3) Suggest pantry_updates after cooking (approximate remaining amounts).
4) Stay sassy. Make the lazy human actually cook.

{JSON_SCHEMA_HINT}
"""


def plan_day(client: OllamaClient, settings: Settings, state: PantryState, day: date | None = None) -> dict[str, Any]:
    day = day or date.today()
    raw = client.chat(SYSTEM_PROMPT, build_user_prompt(settings, state, day))
    plan = parse_plan_json(raw)
    validate_plan(plan)
    plan["_meta"] = {
        "date": day.isoformat(),
        "model": client.model,
        "servings": settings.servings,
    }
    return plan


def parse_plan_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    # Strip accidental markdown fences if the model ignores format=json
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Last resort: largest {...} block
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(text[start : end + 1])
        else:
            raise OllamaError(f"Could not parse chef JSON:\n{raw[:500]}") from None
    if not isinstance(data, dict):
        raise OllamaError("Chef response was not a JSON object")
    return data


def validate_plan(plan: dict[str, Any]) -> None:
    for slot in ("breakfast", "lunch", "dinner"):
        meal = plan.get(slot)
        if not isinstance(meal, dict) or not meal.get("title") or not meal.get("steps"):
            raise OllamaError(f"Plan missing a valid '{slot}' meal")
    if "shopping_to_buy_today" not in plan:
        plan["shopping_to_buy_today"] = []
    if "pantry_updates" not in plan:
        plan["pantry_updates"] = []
    if not plan.get("morning_pep_talk"):
        plan["morning_pep_talk"] = "Up. Apron optional. Hunger non-negotiable."
