"""Ranks and the ladder: pools of opponent decks under decks/ranks/<n>-<rank>/.

    python3 -m mtgsim MY_DECK.txt --ladder            # climb Bronze -> Grandmaster until a rank is failed
    python3 -m mtgsim MY_DECK.txt --rank master       # play every deck in one or more ranks
    python3 -m mtgsim --list-ranks

Each rank is a folder of decklists; drop a file in to add an opponent. The first
comment lines of each decklist say what it is and where it came from.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RANKS_DIR = Path(__file__).resolve().parent.parent / "decks" / "ranks"
PASS_RATE = 0.5  # a deck clears a rank with at least this win rate against the rank's pool as a whole


@dataclass(frozen=True)
class Rank:
    key: str     # "grandmaster"
    label: str   # "Grandmaster"
    folder: str  # "7-grandmaster"
    about: str

    @property
    def path(self) -> Path:
        return RANKS_DIR / self.folder

    def decks(self) -> list[Path]:
        return sorted(self.path.glob("*.txt"))


RANKS = [
    Rank("bronze", "Bronze", "1-bronze", "Badly built piles: vanilla overcosted creatures, five colours, 32 lands"),
    Rank("silver", "Silver", "2-silver", "Starter-style decks with filler cards"),
    Rank("gold", "Gold", "3-gold", "Focused, well-built budget decks with simple cards"),
    Rank("platinum", "Platinum", "4-platinum", "Top Standard decks of 2022 (older card pool)"),
    Rank("diamond", "Diamond", "5-diamond", "Current Standard tournament decks from the edge of the metagame; "
                                            "use --engine forge"),
    Rank("master", "Master", "6-master", "Strong current Standard decks just outside the top archetypes; "
                                         "use --engine forge"),
    Rank("grandmaster", "Grandmaster", "7-grandmaster", "The most-played, best-performing current Standard decks "
                                                        "(metagame of 2026-10-15); use --engine forge"),
]


def resolve_ranks(values: list[str]) -> list[Rank]:
    """Turn ["grandmaster", "2"] or ["all"] into ranks in ladder order, rejecting unknown names."""
    wanted = set()
    for v in values:
        v = v.lower().replace("-", "").replace("_", "").replace(" ", "")
        if v == "all":
            wanted.update(r.key for r in RANKS)
            continue
        match = [r for i, r in enumerate(RANKS, 1) if v in (r.key, str(i)) or (v == "gm" and r.key == "grandmaster")]
        if not match:
            names = ", ".join(f"{i} {r.key}" for i, r in enumerate(RANKS, 1))
            raise ValueError(f"unknown rank {v!r}; ranks are {names}, or all")
        wanted.add(match[0].key)
    return [r for r in RANKS if r.key in wanted]


def list_ranks() -> str:
    from .rating import load_ratings
    ratings = load_ratings()
    out = [f"Ladder: a deck clears a rank with a win rate of at least {PASS_RATE:.0%} against its pool."]
    if ratings:
        out.append("Numbers are each deck's fitted rating (decks/ranks/ratings.json, python3 -m mtgsim.calibrate).")
    for i, r in enumerate(RANKS, 1):
        out.append(f"{i}. {r.label} ({r.key}): {r.about}")
        for p in r.decks():
            fitted = ratings.get(f"{r.key}/{p.stem}")
            out.append(f"     {p.stem}" + (f"  {fitted}" if fitted is not None else ""))
    return "\n".join(out)
