# Sassy Chef

Local AI that plans your day of cooking so you don't have to think before coffee.

Every morning it writes **breakfast → shopping list → lunch → dinner**, keeps a rolling pantry + shopping list on disk, and dumps everything as markdown you can paste into email, Google Keep, or Tasks.

Built for [Hacktoberfest 2026 Week 3 — Slow and Steady](https://dev.to/challenges/hacktoberfest-week3-2026-10-19): open-weight AI that rewards laziness. Runs entirely offline with **Gemma 3 via Ollama** (default `gemma3:4b`).

## Why open / local

- Your fridge and habits never leave your machine
- No API bill for a daily habit
- Swap models in one config line (`gemma3:4b` → `gemma3:12b`, etc.)
- Works when the internet doesn't

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com) running locally
- A pulled model (default Gemma):

```bash
ollama serve          # if not already running
ollama pull gemma3:4b
```

PDF day sheets need one package (`fpdf2`). The meal planner itself is stdlib + Ollama.

## Quick start

```bash
cd sassy-chef
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m sassy_chef doctor          # check Ollama + model
python -m sassy_chef plan            # generate today (+ PDF)
```

Outputs land in `output/`:

| File | What |
|------|------|
| `YYYY-MM-DD-cooking.md` | Pep talk + breakfast / lunch / dinner steps |
| `YYYY-MM-DD-shopping.md` | Today's buys + rolling open list |
| `YYYY-MM-DD-day.pdf` | **Printable 1–2 page day sheet** (meals + checkboxes) |
| `today-*.md` / `today-day.pdf` | Same content, stable names for scripts / print |

Pantry state lives in `data/pantry.json` (seeded with staples on first run).

## Commands

```bash
python -m sassy_chef plan                  # today (+ markdown + PDF)
python -m sassy_chef plan --date 2026-10-24
python -m sassy_chef plan --model gemma3:12b
python -m sassy_chef plan --mailto         # print a mailto: draft link
python -m sassy_chef plan --no-pdf         # markdown only

python -m sassy_chef pdf                   # reprint PDF from last saved plan
python -m sassy_chef pdf --date 2026-10-23

python -m sassy_chef show                  # pantry + missed-only shopping
python -m sassy_chef add pantry "yogurt" --qty 1 --unit tub
python -m sassy_chef missed spinach        # ONLY if you didn't buy it
```

Print `output/today-day.pdf` (A4, tight layout: pep talk, three meals, shopping checkboxes).

## Config

Edit `config.toml`:

```toml
[ollama]
model = "gemma3:4b"          # change anytime
base_url = "http://127.0.0.1:11434"

[chef]
servings = 2
diet = ""                    # e.g. "vegetarian"
preferences = "simple recipes, under 45 minutes when possible, reuse leftovers"
```

## How the shopping brain works (lazy by default)

1. Load pantry + any *missed* leftovers + recent meals
2. Ask Sassy Chef for today's three meals using what you already have
3. Print today's shopping list (markdown + PDF)
4. **Assume the list was bought** → items move into pantry, shopping clears
5. Apply approximate pantry updates after cooking

You do **nothing** on a normal day. Only if you skipped something:

```bash
python -m sassy_chef missed spinach
```

That pulls it out of the pantry and parks it for the next plan's list.

## Optional: cron every morning

```cron
30 7 * * * cd /path/to/sassy-chef && python -m sassy_chef plan >> /tmp/sassy-chef.log 2>&1
```

Then open `output/today-cooking.md` with breakfast.

## Challenge fit

| Theme beat | How |
|------------|-----|
| Rewards laziness | One command → full day of food + list |
| Open-weight AI | Gemma via Ollama |
| Local / private | No cloud inference |
| Partner category | **Best Use of Gemma** |

## License

MIT — cook freely.
