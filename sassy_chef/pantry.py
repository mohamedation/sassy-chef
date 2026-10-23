"""Persistent pantry + rolling shopping list."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class PantryItem:
    name: str
    quantity: str = "some"
    unit: str = ""
    notes: str = ""

    def key(self) -> str:
        return self.name.strip().lower()


@dataclass
class ShoppingItem:
    name: str
    quantity: str = "1"
    unit: str = ""
    reason: str = ""
    bought: bool = False

    def key(self) -> str:
        return self.name.strip().lower()


@dataclass
class PantryState:
    pantry: list[PantryItem] = field(default_factory=list)
    shopping: list[ShoppingItem] = field(default_factory=list)
    recent_meals: list[str] = field(default_factory=list)
    updated_at: str = ""

    def pantry_names(self) -> list[str]:
        return sorted({p.name for p in self.pantry}, key=str.lower)

    def open_shopping(self) -> list[ShoppingItem]:
        return [s for s in self.shopping if not s.bought]

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "pantry": [asdict(p) for p in self.pantry],
            "open_shopping_list": [asdict(s) for s in self.open_shopping()],
            "recent_meals": self.recent_meals[-14:],
        }


class PantryStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> PantryState:
        if not self.path.exists():
            return PantryState(updated_at=_now())
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return PantryState(
            pantry=[PantryItem(**i) for i in raw.get("pantry", [])],
            shopping=[ShoppingItem(**i) for i in raw.get("shopping", [])],
            recent_meals=list(raw.get("recent_meals", [])),
            updated_at=str(raw.get("updated_at", "")),
        )

    def save(self, state: PantryState) -> None:
        state.updated_at = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pantry": [asdict(p) for p in state.pantry],
            "shopping": [asdict(s) for s in state.shopping],
            "recent_meals": state.recent_meals[-30:],
            "updated_at": state.updated_at,
        }
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def seed_if_empty(self, state: PantryState) -> PantryState:
        """Starter staples so day-one plans aren't empty-fridge chaos."""
        if state.pantry:
            return state
        staples = [
            PantryItem("eggs", "6", "count"),
            PantryItem("milk", "1", "liter"),
            PantryItem("butter", "1", "stick"),
            PantryItem("olive oil", "1", "bottle"),
            PantryItem("salt", "1", "box"),
            PantryItem("black pepper", "1", "jar"),
            PantryItem("garlic", "1", "head"),
            PantryItem("onion", "2", "count"),
            PantryItem("rice", "1", "kg"),
            PantryItem("pasta", "500", "g"),
            PantryItem("canned tomatoes", "2", "cans"),
            PantryItem("bread", "1", "loaf"),
        ]
        state.pantry = staples
        return state


def items_from_plan(raw_items: list[dict[str, Any]]) -> list[ShoppingItem]:
    """Parse chef shopping suggestions into ShoppingItem rows (for print / assume-bought)."""
    out: list[ShoppingItem] = []
    seen: set[str] = set()
    for raw in raw_items:
        name = str(raw.get("name", "")).strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(
            ShoppingItem(
                name=name,
                quantity=str(raw.get("quantity", "1")),
                unit=str(raw.get("unit", "")),
                reason=str(raw.get("reason", "")),
                bought=False,
            )
        )
    return out


def assume_bought(state: PantryState, items: list[ShoppingItem]) -> int:
    """Lazy default: treat listed items as purchased — into pantry, shopping list cleared.

    Call with today's print list + any previously missed leftovers so a normal store
    run needs zero typing afterward.
    """
    by_key = {i.key(): i for i in items if i.name.strip()}
    for item in by_key.values():
        state.pantry = _upsert_pantry(
            state.pantry,
            PantryItem(name=item.name, quantity=item.quantity, unit=item.unit),
        )
    state.shopping = []
    return len(by_key)


def mark_missed(state: PantryState, names: list[str]) -> int:
    """Exception path: you did NOT buy these — pull out of pantry, park on shopping again."""
    # Preserve caller casing for display when item isn't in pantry yet
    wanted: dict[str, str] = {}
    for n in names:
        name = n.strip()
        if name:
            wanted[name.lower()] = name
    if not wanted:
        return 0

    count = 0
    pantry_by_key = {p.key(): p for p in state.pantry}
    open_keys = {s.key() for s in state.open_shopping()}

    for key, display in wanted.items():
        if key in open_keys:
            continue
        if key in pantry_by_key:
            p = pantry_by_key[key]
            state.shopping.append(
                ShoppingItem(
                    name=p.name,
                    quantity=p.quantity,
                    unit=p.unit,
                    reason="missed last shop",
                )
            )
            state.pantry = [x for x in state.pantry if x.key() != key]
        else:
            state.shopping.append(
                ShoppingItem(name=display, quantity="1", reason="missed last shop")
            )
        count += 1
    return count


def apply_pantry_updates(state: PantryState, updates: list[dict[str, Any]]) -> None:
    for raw in updates:
        name = str(raw.get("name", "")).strip()
        if not name:
            continue
        action = str(raw.get("action", "set")).lower()
        if action == "remove":
            state.pantry = [p for p in state.pantry if p.key() != name.lower()]
            continue
        state.pantry = _upsert_pantry(
            state.pantry,
            PantryItem(
                name=name,
                quantity=str(raw.get("quantity", "some")),
                unit=str(raw.get("unit", "")),
                notes=str(raw.get("notes", "")),
            ),
        )


def remember_meals(state: PantryState, day: date, meals: dict[str, Any]) -> None:
    labels = []
    for slot in ("breakfast", "lunch", "dinner"):
        meal = meals.get(slot) or {}
        title = meal.get("title")
        if title:
            labels.append(f"{day.isoformat()} {slot}: {title}")
    state.recent_meals.extend(labels)
    state.recent_meals = state.recent_meals[-30:]


def _upsert_pantry(items: list[PantryItem], item: PantryItem) -> list[PantryItem]:
    out = [p for p in items if p.key() != item.key()]
    out.append(item)
    return sorted(out, key=lambda p: p.name.lower())


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
