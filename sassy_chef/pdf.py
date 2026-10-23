"""Compact 1–2 page printable day sheet (A4)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .pantry import ShoppingItem

# Common Linux / macOS / Windows font paths for Unicode (sassy punctuation)
_FONT_CANDIDATES = [
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
]
_BOLD_CANDIDATES = [
    Path("/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    Path("C:/Windows/Fonts/arialbd.ttf"),
]


def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p.is_file():
            return p
    return None


def write_day_pdf(
    path: Path,
    plan: dict[str, Any],
    day: date,
    today_items: list[ShoppingItem],
    open_list: list[ShoppingItem],
) -> Path:
    """Write a print-ready day card. Raises ImportError if fpdf2 is missing."""
    try:
        from fpdf import FPDF
    except ImportError as e:
        raise ImportError(
            "PDF export needs fpdf2. Install with: pip install fpdf2"
        ) from e

    meta = plan.get("_meta") or {}
    servings = meta.get("servings", "?")
    model = meta.get("model", "")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_margins(12, 12, 12)
    pdf.add_page()

    regular = _first_existing(_FONT_CANDIDATES)
    bold = _first_existing(_BOLD_CANDIDATES)
    if regular:
        pdf.add_font("Body", "", str(regular))
        pdf.add_font("Body", "B", str(bold or regular))
        family = "Body"
    else:
        family = "Helvetica"

    # Header
    pdf.set_font(family, "B", 16)
    pdf.cell(0, 8, "Sassy Chef", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(family, "", 10)
    subtitle = f"{day.strftime('%A')}  ·  {day.isoformat()}  ·  {servings} servings"
    if model:
        subtitle += f"  ·  {model}"
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 5, subtitle, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    _rule(pdf)

    # Pep talk
    _section(pdf, family, "Morning pep talk")
    pdf.set_font(family, "", 9)
    pdf.multi_cell(0, 4.2, str(plan.get("morning_pep_talk", "")).strip())
    pdf.ln(2)

    # Meals — compact
    for slot in ("breakfast", "lunch", "dinner"):
        _meal(pdf, family, slot, plan.get(slot) or {})

    # Shopping
    _rule(pdf)
    _section(pdf, family, "Shopping — buy today")
    pdf.set_font(family, "", 7)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(
        0,
        3.4,
        "Assumed bought after plan. Only if you skipped something:  sassy_chef missed <item>",
    )
    pdf.set_text_color(0, 0, 0)
    today_keys = {i.key() for i in today_items}
    if today_items:
        for item in today_items:
            _checkbox_line(pdf, family, item)
    else:
        pdf.set_font(family, "", 9)
        pdf.multi_cell(0, 4.2, "Nothing new — pantry covers today.")

    leftover = [i for i in open_list if i.key() not in today_keys]
    if leftover:
        pdf.ln(1)
        pdf.set_font(family, "B", 10)
        pdf.cell(0, 5, "Also grab (previously missed)", new_x="LMARGIN", new_y="NEXT")
        for item in leftover:
            _checkbox_line(pdf, family, item)

    # Lazy win footer
    lazy = str(plan.get("lazy_win", "")).strip()
    if lazy:
        pdf.ln(2)
        _rule(pdf)
        pdf.set_font(family, "B", 9)
        pdf.cell(0, 5, "Lazy win", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(family, "", 8)
        pdf.set_text_color(50, 50, 50)
        pdf.multi_cell(0, 3.8, lazy)
        pdf.set_text_color(0, 0, 0)

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return path


def _rule(pdf) -> None:
    y = pdf.get_y() + 1.5
    pdf.set_draw_color(180, 180, 180)
    pdf.set_line_width(0.3)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.set_y(y + 2.5)


def _section(pdf, family: str, title: str) -> None:
    pdf.set_font(family, "B", 11)
    pdf.cell(0, 6, title, new_x="LMARGIN", new_y="NEXT")


def _meal(pdf, family: str, slot: str, meal: dict[str, Any]) -> None:
    title = str(meal.get("title", "Untitled"))
    mins = meal.get("time_minutes", "?")
    steps = meal.get("steps") or []
    note = str(meal.get("chef_note", "")).strip()
    uses = meal.get("uses_from_pantry") or []

    pdf.set_x(pdf.l_margin)
    pdf.set_font(family, "B", 10)
    pdf.multi_cell(0, 5.5, f"{slot.title()}: {title}  ·  ~{mins} min")

    if uses:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(family, "", 8)
        pdf.set_text_color(80, 80, 80)
        pdf.multi_cell(0, 3.6, "Pantry: " + ", ".join(str(u) for u in uses))
        pdf.set_text_color(0, 0, 0)

    pdf.set_font(family, "", 9)
    # Cap steps so the sheet stays printable (1–2 pages)
    for i, step in enumerate(steps[:6], 1):
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 4.0, f"{i}. {step}")
    if len(steps) > 6:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(family, "", 8)
        pdf.multi_cell(0, 3.5, f"… +{len(steps) - 6} more steps in the markdown file")

    if note:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(family, "", 8)
        pdf.set_text_color(90, 40, 40)
        pdf.multi_cell(0, 3.6, f"Chef: {note}")
        pdf.set_text_color(0, 0, 0)
    pdf.ln(1.5)


def _checkbox_line(pdf, family: str, item: ShoppingItem) -> None:
    qty = f"{item.quantity} {item.unit}".strip()
    reason = f" — {item.reason}" if item.reason else ""
    label = f"{item.name} ({qty}){reason}" if qty else f"{item.name}{reason}"
    pdf.set_font(family, "", 9)
    pdf.set_x(pdf.l_margin)
    x, y = pdf.l_margin, pdf.get_y()
    box = 3.2
    pdf.rect(x, y + 0.6, box, box)
    text_w = pdf.w - pdf.r_margin - x - box - 2
    pdf.set_xy(x + box + 2, y)
    pdf.multi_cell(text_w, 4.2, label)
    pdf.set_x(pdf.l_margin)
