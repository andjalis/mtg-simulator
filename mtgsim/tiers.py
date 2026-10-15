"""Test tiers and the ladder: sets of opponent decks under decks/tiers/<n>-<name>/.

    python3 -m mtgsim MY_DECK.txt --ladder            # climb trash -> pro until a tier is failed
    python3 -m mtgsim MY_DECK.txt --tier pro          # play every deck in one or more tiers
    python3 -m mtgsim --list-tiers

Each tier is a folder of decklists; drop a file in to add an opponent. The first
comment lines of each decklist say what it is and where it came from.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

TIERS_DIR = Path(__file__).resolve().parent.parent / "decks" / "tiers"
PASS_RATE = 0.5  # a deck clears a tier with at least this win rate against the tier as a whole


@dataclass(frozen=True)
class Tier:
    key: str     # "semipro"
    label: str   # "Semi-pro"
    folder: str  # "4-semipro"
    about: str

    @property
    def path(self) -> Path:
        return TIERS_DIR / self.folder

    def decks(self) -> list[Path]:
        return sorted(self.path.glob("*.txt"))


TIERS = [
    Tier("trash", "Trash", "1-trash", "Badly built piles: vanilla overcosted creatures, five colours, 32 lands"),
    Tier("beginner", "Beginner", "2-beginner", "Starter-style decks with filler cards"),
    Tier("advanced", "Advanced", "3-advanced", "Focused, well-built budget decks with simple cards"),
    Tier("semipro", "Semi-pro", "4-semipro", "Top Standard decks of 2022 (older card pool)"),
    Tier("pro", "Pro", "5-pro", "The best current Standard tournament decks (metagame of 2026-10-15); "
                                "use --engine forge, the built-in engine ignores much of their text"),
]


def resolve_tiers(values: list[str]) -> list[Tier]:
    """Turn ["pro", "2"] or ["all"] into tiers in ladder order, rejecting unknown names."""
    wanted = set()
    for v in values:
        v = v.lower().replace("-", "").replace("_", "")
        if v == "all":
            wanted.update(t.key for t in TIERS)
            continue
        match = [t for i, t in enumerate(TIERS, 1) if v in (t.key, str(i))]
        if not match:
            names = ", ".join(f"{i} {t.key}" for i, t in enumerate(TIERS, 1))
            raise ValueError(f"unknown tier {v!r}; tiers are {names}, or all")
        wanted.add(match[0].key)
    return [t for t in TIERS if t.key in wanted]


def list_tiers() -> str:
    out = [f"Ladder: a deck clears a tier with a win rate of at least {PASS_RATE:.0%} against it."]
    for i, t in enumerate(TIERS, 1):
        out.append(f"{i}. {t.label} ({t.key}): {t.about}")
        out += [f"     {p.stem}" for p in t.decks()]
    return "\n".join(out)
