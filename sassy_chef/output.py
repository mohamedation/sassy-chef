"""Render daily cooking + shopping markdown (email / notes friendly)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .pantry import ShoppingItem


def meal_block(slot: str, meal: dict[str, Any]) -> str:
    title = meal.get("title", "Untitled")
    mins = meal.get("time_minutes", "?")
    uses = meal.get("uses_from_pantry") or []
    steps = meal.get("steps") or []
    note = meal.get("chef_note", "")

    lines = [
        f"## {slot.title()}: {title}",
        "",
        f"_About {mins} minutes_",
        "",
    ]
    if uses:
        lines.append("**Uses from pantry:** " + ", ".join(str(u) for u in uses))
        lines.append("")
    lines.append("### Steps")
    lines.append("")
    for i, step in enumerate(steps, 1):
        lines.append(f"{i}. {step}")
    lines.append("")
    if note:
        lines.append(f"> Chef: {note}")
        lines.append("")
    return "\n".join(lines)


def render_cooking_md(plan: dict[str, Any], day: date) -> str:
    meta = plan.get("_meta") or {}
    model = meta.get("model", "local-model")
    servings = meta.get("servings", "?")
    parts = [
        f"# Sassy Chef — {day.isoformat()} ({day.strftime('%A')})",
        "",
        f"_Servings: {servings} · Model: `{model}`_",
        "",
        "## Morning pep talk",
        "",
        plan.get("morning_pep_talk", ""),
        "",
        meal_block("breakfast", plan.get("breakfast") or {}),
        meal_block("lunch", plan.get("lunch") or {}),
        meal_block("dinner", plan.get("dinner") or {}),
        "## Lazy win",
        "",
        plan.get("lazy_win", "You didn't have to think. That's the point."),
        "",
    ]
    return "\n".join(parts).rstrip() + "\n"


def render_shopping_md(
    day: date,
    today_items: list[ShoppingItem],
    open_list: list[ShoppingItem],
) -> str:
    lines = [
        f"# Shopping list — {day.isoformat()}",
        "",
        "_Copy into email, Google Keep, Tasks, or a notes app._",
        "",
        "_Lazy default: these are assumed bought after you run `plan`. "
        "Only if you skipped something: `python -m sassy_chef missed <item>`._",
        "",
        "## Buy today (for today's meals)",
        "",
    ]
    if today_items:
        for item in today_items:
            qty = f"{item.quantity} {item.unit}".strip()
            reason = f" — {item.reason}" if item.reason else ""
            lines.append(f"- [ ] **{item.name}** ({qty}){reason}")
    else:
        lines.append("_Nothing new — pantry already covers today. Flex._")

    lines.extend(["", "## Still on the rolling list", ""])
    # Avoid duplicating today's items in the rolling section
    today_keys = {i.key() for i in today_items}
    leftover = [i for i in open_list if i.key() not in today_keys]
    if leftover:
        for item in leftover:
            qty = f"{item.quantity} {item.unit}".strip()
            reason = f" — {item.reason}" if item.reason else ""
            lines.append(f"- [ ] **{item.name}** ({qty}){reason}")
    else:
        lines.append("_Clear. Don't invent errands._")

    lines.append("")
    return "\n".join(lines)


def write_daily_outputs(
    output_dir: Path,
    day: date,
    cooking_md: str,
    shopping_md: str,
    plan: dict[str, Any] | None = None,
    today_items: list[ShoppingItem] | None = None,
    open_list: list[ShoppingItem] | None = None,
    write_pdf: bool = True,
) -> tuple[Path, Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = day.isoformat()
    cooking_path = output_dir / f"{stamp}-cooking.md"
    shopping_path = output_dir / f"{stamp}-shopping.md"
    cooking_path.write_text(cooking_md, encoding="utf-8")
    shopping_path.write_text(shopping_md, encoding="utf-8")
    # Convenience aliases for "today"
    (output_dir / "today-cooking.md").write_text(cooking_md, encoding="utf-8")
    (output_dir / "today-shopping.md").write_text(shopping_md, encoding="utf-8")

    pdf_path: Path | None = None
    if write_pdf and plan is not None:
        from .pdf import write_day_pdf

        pdf_path = output_dir / f"{stamp}-day.pdf"
        write_day_pdf(
            pdf_path,
            plan,
            day,
            today_items or [],
            open_list or [],
        )
        (output_dir / "today-day.pdf").write_bytes(pdf_path.read_bytes())
    return cooking_path, shopping_path, pdf_path


def mailto_hint(subject: str, body: str) -> str:
    """Return a mailto URL (truncated body) — useful for one-click email drafts."""
    from urllib.parse import quote

    # Keep URL short enough for most clients
    clipped = body if len(body) < 1500 else body[:1500] + "\n\n[truncated — see markdown file]"
    return f"mailto:?subject={quote(subject)}&body={quote(clipped)}"
