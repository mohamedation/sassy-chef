"""Load config.toml with sensible defaults."""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.toml"


@dataclass
class Settings:
    model: str = "gemma3:4b"
    base_url: str = "http://127.0.0.1:11434"
    timeout_seconds: int = 180
    servings: int = 2
    diet: str = ""
    preferences: str = "simple recipes, reuse leftovers"
    cuisine_hint: str = ""
    data_dir: Path = ROOT / "data"
    output_dir: Path = ROOT / "output"

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        cfg_path = path or DEFAULT_CONFIG
        data: dict = {}
        if cfg_path.exists():
            with cfg_path.open("rb") as f:
                data = tomllib.load(f)

        ollama = data.get("ollama", {})
        chef = data.get("chef", {})
        paths = data.get("paths", {})

        def resolve(p: str) -> Path:
            path_obj = Path(p)
            return path_obj if path_obj.is_absolute() else ROOT / path_obj

        return cls(
            model=str(ollama.get("model", cls.model)),
            base_url=str(ollama.get("base_url", cls.base_url)).rstrip("/"),
            timeout_seconds=int(ollama.get("timeout_seconds", cls.timeout_seconds)),
            servings=int(chef.get("servings", cls.servings)),
            diet=str(chef.get("diet", cls.diet)),
            preferences=str(chef.get("preferences", cls.preferences)),
            cuisine_hint=str(chef.get("cuisine_hint", cls.cuisine_hint)),
            data_dir=resolve(str(paths.get("data_dir", "data"))),
            output_dir=resolve(str(paths.get("output_dir", "output"))),
        )


def ensure_dirs(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "history").mkdir(parents=True, exist_ok=True)


# tomllib is stdlib on 3.11+; keep a clear error on ancient Pythons
if sys.version_info < (3, 11):
    raise SystemExit("Sassy Chef needs Python 3.11+")
