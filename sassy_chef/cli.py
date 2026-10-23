"""Command-line interface for Sassy Chef."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from . import __version__
from .config import ROOT, Settings, ensure_dirs
from .ollama_client import OllamaClient, OllamaError
from .output import mailto_hint, render_cooking_md, render_shopping_md, write_daily_outputs
from .pantry import (
    PantryStore,
    apply_pantry_updates,
    assume_bought,
    items_from_plan,
    mark_missed,
    remember_meals,
)
from .planner import plan_day


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sassy-chef",
        description="Local AI daily meal planner with a sassy chef personality (Ollama + Gemma).",
    )
    parser.add_argument("--config", type=Path, default=None, help="Path to config.toml")
    parser.add_argument("--model", default=None, help="Override Ollama model (e.g. gemma3:4b)")
    parser.add_argument("--version", action="version", version=f"sassy-chef {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    plan_p = sub.add_parser("plan", help="Generate today's meals + shopping list")
    plan_p.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    plan_p.add_argument("--mailto", action="store_true", help="Print a mailto: link for the shopping list")
    plan_p.add_argument("--json", action="store_true", help="Also dump raw plan JSON to stdout")
    plan_p.add_argument("--no-pdf", action="store_true", help="Skip the printable PDF day sheet")

    pdf_p = sub.add_parser("pdf", help="Rebuild printable PDF from a saved plan (no model call)")
    pdf_p.add_argument("--date", default=None, help="YYYY-MM-DD (default: latest history / today)")

    show_p = sub.add_parser("show", help="Show pantry / shopping state")
    show_p.add_argument("what", choices=["pantry", "shopping", "all"], nargs="?", default="all")

    add_p = sub.add_parser("add", help="Add an item to pantry or shopping")
    add_p.add_argument("target", choices=["pantry", "shopping"])
    add_p.add_argument("name")
    add_p.add_argument("--qty", default="1")
    add_p.add_argument("--unit", default="")
    add_p.add_argument("--reason", default="")

    missed_p = sub.add_parser(
        "missed",
        help="Lazy exception: you did NOT buy these (back on shopping, off pantry)",
    )
    missed_p.add_argument("names", nargs="+", help="Item names you skipped")

    sub.add_parser("doctor", help="Check Ollama connectivity and model")

    args = parser.parse_args(argv)
    settings = Settings.load(args.config)
    if args.model:
        settings.model = args.model
    ensure_dirs(settings)

    store = PantryStore(settings.data_dir / "pantry.json")
    state = store.seed_if_empty(store.load())
    store.save(state)

    client = OllamaClient(settings.base_url, settings.model, settings.timeout_seconds)

    try:
        if args.command == "doctor":
            return cmd_doctor(client, settings)
        if args.command == "show":
            return cmd_show(state, args.what)
        if args.command == "add":
            return cmd_add(store, state, args)
        if args.command == "missed":
            return cmd_missed(store, state, args.names)
        if args.command == "plan":
            return cmd_plan(client, settings, store, state, args)
        if args.command == "pdf":
            return cmd_pdf(settings, store, state, args)
    except OllamaError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except ImportError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_doctor(client: OllamaClient, settings: Settings) -> int:
    print(f"config root : {ROOT}")
    print(f"ollama url  : {settings.base_url}")
    print(f"model       : {settings.model}")
    if not client.ping():
        print("status      : Ollama not reachable — run `ollama serve`")
        return 1
    models = client.list_models()
    print(f"status      : ok ({len(models)} model(s) listed)")
    if models:
        print("models      : " + ", ".join(models[:12]) + (" ..." if len(models) > 12 else ""))
    if settings.model not in models and not any(m.startswith(settings.model.split(":")[0]) for m in models):
        print(f"hint        : pull the model with: ollama pull {settings.model}")
    else:
        print("hint        : configured model looks available")
    return 0


def cmd_show(state, what: str) -> int:
    if what in ("pantry", "all"):
        print("## Pantry")
        if not state.pantry:
            print("(empty)")
        for p in state.pantry:
            qty = f"{p.quantity} {p.unit}".strip()
            print(f"- {p.name}: {qty}")
        print()
    if what in ("shopping", "all"):
        print("## Shopping (missed only — empty means you're fully lazy)")
        open_items = state.open_shopping()
        if not open_items:
            print("(clear — next plan assumes the printed list gets bought)")
        for s in open_items:
            qty = f"{s.quantity} {s.unit}".strip()
            reason = f" — {s.reason}" if s.reason else ""
            print(f"- [ ] {s.name}: {qty}{reason}")
    return 0


def cmd_add(store, state, args) -> int:
    from .pantry import ShoppingItem, apply_pantry_updates

    if args.target == "pantry":
        apply_pantry_updates(
            state,
            [{"name": args.name, "quantity": args.qty, "unit": args.unit, "action": "set"}],
        )
        print(f"Added to pantry: {args.name}")
    else:
        state.shopping.append(
            ShoppingItem(name=args.name, quantity=args.qty, unit=args.unit, reason=args.reason)
        )
        print(f"Added to shopping: {args.name}")
    store.save(state)
    return 0


def cmd_missed(store, state, names: list[str]) -> int:
    n = mark_missed(state, names)
    store.save(state)
    print(f"Noted {n} missed item(s) — back on shopping, removed from pantry")
    print("No extra work needed on days you buy everything.")
    return 0


def cmd_plan(client, settings, store, state, args) -> int:
    day = _parse_day(args.date)
    print(f"Asking Sassy Chef ({settings.model}) for {day.isoformat()}…", flush=True)
    plan = plan_day(client, settings, state, day)

    # Capture print list BEFORE optimistic buy (today + previously missed leftovers)
    prior_missed = list(state.open_shopping())
    today_items = items_from_plan(plan.get("shopping_to_buy_today") or [])
    # Dedupe: prior missed first, then today's new names
    print_keys = {i.key() for i in today_items}
    leftover_for_print = [i for i in prior_missed if i.key() not in print_keys]
    to_assume = today_items + leftover_for_print

    apply_pantry_updates(state, plan.get("pantry_updates") or [])
    n_bought = assume_bought(state, to_assume)
    remember_meals(state, day, plan)
    store.save(state)

    # Archive raw plan
    hist = settings.data_dir / "history" / f"{day.isoformat()}.json"
    hist.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    cooking_md = render_cooking_md(plan, day)
    # open_list empty after assume_bought; pass leftover_for_print for the sheet sections
    shopping_md = render_shopping_md(day, today_items, leftover_for_print)
    cooking_path, shopping_path, pdf_path = write_daily_outputs(
        settings.output_dir,
        day,
        cooking_md,
        shopping_md,
        plan=plan,
        today_items=today_items,
        open_list=leftover_for_print,
        write_pdf=not args.no_pdf,
    )

    print()
    print(cooking_md)
    print("---")
    print(shopping_md)
    print(f"Wrote {cooking_path}")
    print(f"Wrote {shopping_path}")
    if pdf_path:
        print(f"Wrote {pdf_path}  (print-ready day sheet)")
    print(f"Assumed bought → pantry ({n_bought} item(s)). Skipped something?  missed <item>")
    print(f"Pantry saved → {store.path}")

    if args.mailto:
        link = mailto_hint(f"Shopping list {day.isoformat()}", shopping_md)
        print()
        print("mailto:", link)

    if args.json:
        print()
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0


def cmd_pdf(settings, store, state, args) -> int:
    from .pantry import ShoppingItem

    day = _parse_day(args.date) if args.date else _latest_history_day(settings) or date.today()
    hist = settings.data_dir / "history" / f"{day.isoformat()}.json"
    if not hist.exists():
        print(f"error: no saved plan at {hist} — run `plan` first", file=sys.stderr)
        return 1

    plan = json.loads(hist.read_text(encoding="utf-8"))
    today_raw = plan.get("shopping_to_buy_today") or []
    today_items = [
        ShoppingItem(
            name=str(i.get("name", "")),
            quantity=str(i.get("quantity", "1")),
            unit=str(i.get("unit", "")),
            reason=str(i.get("reason", "")),
        )
        for i in today_raw
        if i.get("name")
    ]

    cooking_md = render_cooking_md(plan, day)
    shopping_md = render_shopping_md(day, today_items, state.open_shopping())
    _, _, pdf_path = write_daily_outputs(
        settings.output_dir,
        day,
        cooking_md,
        shopping_md,
        plan=plan,
        today_items=today_items,
        open_list=state.open_shopping(),
        write_pdf=True,
    )
    print(f"Wrote {pdf_path}")
    print(f"Also refreshed markdown in {settings.output_dir}")
    return 0


def _latest_history_day(settings) -> date | None:
    hist_dir = settings.data_dir / "history"
    if not hist_dir.is_dir():
        return None
    dates = sorted(hist_dir.glob("*.json"), reverse=True)
    if not dates:
        return None
    try:
        return datetime.strptime(dates[0].stem, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_day(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


if __name__ == "__main__":
    raise SystemExit(main())
