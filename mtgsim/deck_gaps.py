"""Rank the rules text the engine ignores in the ladder and meta decks by how much it matters.

    python3 -m mtgsim.deck_gaps
    python3 -m mtgsim.deck_gaps --save results/deck-gap-priority

Every main-deck card in `decks/ranks/` and the metagame archetypes is measured with the same
classification as `--coverage`. Each ignored line is scored by the main-deck copies it appears in,
weighted by the deck's rank and its metagame share, so a line in four copies of a Grandmaster card
counts for more than one copy in a Bronze pile. "Unlocks" counts the copies that would become fully
template-matched if that line were the only fix. Lines that need a rules layer the engine does not
have yet (copy effects, control change, type and ability changes, replacement effects, face-down
permanents, day/night) are marked blocked and listed apart from the candidates.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .carddb import CardDB
from .coverage import _faces, card_coverage
from .decklist import load_deck
from .standard_coverage import families

ROOT = Path(__file__).resolve().parent.parent
RANKS = ROOT / "decks" / "ranks"
METAGAME = Path(__file__).resolve().parent / "data" / "metagame.json"

# Rank folder prefix 1..7 sets the base weight; metagame share (percent, averaged over sources)
# adds share/5, so a 14% archetype counts about three ranks heavier.
SHARE_DIVISOR = 5.0

# Wording that needs a general rules layer the engine lacks (README "Not yet" and the rules
# architecture notes). Lines matching any of these are not batch candidates.
BLOCKED = [
    ("copy effects", r"\bcop(?:y|ies)\b"),
    ("control change", r"\bgain control\b|\bexchange control\b"),
    ("type/ability change", r"\bloses? all abilities\b|\bis (?:a|an|every) [a-z ]*(?:in addition|type)\b"
                            r"|\bbecomes? (?:a|an) (?!\d)[a-z ]*(?:creature|artifact|enchantment|land)\b(?! token)"),
    # "deals 5 damage instead" style upgrades are conditional modes, not replacement effects.
    ("replacement effects", r"\bif [^.]* would\b|\binstead of\b|\bas [^.]* enters\b"),
    ("face-down permanents", r"\bface[- ]down\b|\bmanifest\b|\bcloak\b|\bdisguise\b|\bmorph\b"),
    ("day/night", r"\bday\b.*\bnight\b|\bdaybound\b|\bnightbound\b"),
    ("auras/equipment attach", r"^enchant\b|\battach\b|^equip\b"),
    ("casualty", r"\bcasualty\b"),
]
_BLOCKED_RE = [(name, re.compile(rx)) for name, rx in BLOCKED]


def blocked_by(line: str) -> list[str]:
    return [name for name, rx in _BLOCKED_RE if rx.search(line)]


def normalise(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip().lower()


@dataclass
class DeckRef:
    path: Path
    rank: int
    share: float

    @property
    def weight(self) -> float:
        return self.rank + self.share / SHARE_DIVISOR

    @property
    def label(self) -> str:
        return self.path.relative_to(ROOT).as_posix()


@dataclass
class LineGap:
    line: str
    score: float = 0.0
    copies: int = 0
    unlocks: int = 0
    decks: set[str] = field(default_factory=set)
    cards: set[str] = field(default_factory=set)

    def as_dict(self):
        return {"line": self.line, "score": round(self.score, 1), "copies": self.copies,
                "unlock_copies": self.unlocks, "decks": len(self.decks), "cards": sorted(self.cards),
                "families": families(self.line), "blocked_by": blocked_by(self.line)}


def deck_refs(ranks: Path = RANKS, metagame: Path = METAGAME) -> list[DeckRef]:
    shares = {}
    if metagame.exists():
        for arch in json.loads(metagame.read_text()).get("archetypes", []):
            values = list(arch.get("share", {}).values())
            if arch.get("file") and values:
                shares[arch["file"]] = sum(values) / len(values)
    refs = []
    for path in sorted(ranks.glob("*/*.txt")):
        rank = int(path.parent.name.split("-", 1)[0])
        refs.append(DeckRef(path, rank, shares.get(path.name, 0.0)))
    return refs


def measure(db: CardDB, refs: list[DeckRef]) -> dict:
    gaps: dict[str, LineGap] = {}
    totals = {"decks": len(refs), "copies": 0, "full_copies": 0, "partial_copies": 0}
    missing = set()
    for ref in refs:
        _, counts = load_deck(ref.path)
        for name, n in counts.items():
            totals["copies"] += n
            try:
                card = db.get(name)
            except KeyError:
                missing.add(name)
                continue
            row = card_coverage(card, n)
            lines = {normalise(line) for face in _faces(card) for line in face.unsupported if line.strip()}
            if not lines:
                totals["full_copies"] += n * (row.status == "full")
                continue
            totals["partial_copies"] += n
            for line in lines:
                gap = gaps.setdefault(line, LineGap(line))
                gap.score += n * ref.weight
                gap.copies += n
                gap.decks.add(ref.label)
                gap.cards.add(card.name)
                if len(lines) == 1 and not row.simplified:
                    gap.unlocks += n
    ordered = sorted(gaps.values(), key=lambda g: (-g.score, -g.unlocks, g.line))
    return {"measured_on": datetime.now(timezone.utc).date().isoformat(), "totals": totals,
            "missing_cards": sorted(missing),
            "weighting": f"score = sum of main-deck copies x (rank 1-7 + metagame share % / {SHARE_DIVISOR:g})",
            "candidates": [g.as_dict() for g in ordered if not blocked_by(g.line)],
            "blocked": [g.as_dict() for g in ordered if blocked_by(g.line)]}


def format_report(report: dict, top: int = 40) -> str:
    t = report["totals"]
    out = ["# Deck gap priority (O4)\n",
           f"Measured {report['measured_on']} over {t['decks']} ladder and meta decks: "
           f"{t['full_copies']} of {t['copies']} main-deck copies fully template-matched, "
           f"{t['partial_copies']} partly supported.\n",
           f"Weighting: {report['weighting']}. Unlock copies become fully matched if this line alone is fixed. "
           "Blocked lines need a general rules layer the engine lacks and are not batch candidates.\n"]
    for title, key in (("Candidates", "candidates"), ("Blocked by missing layers", "blocked")):
        out += [f"## {title}\n", "| # | Score | Copies | Unlocks | Decks | Line | Cards | Family / blocker |",
                "| ---: | ---: | ---: | ---: | ---: | --- | --- | --- |"]
        for i, g in enumerate(report[key][:top], 1):
            tag = ", ".join(g["blocked_by"] or g["families"]) or "-"
            cards = "; ".join(g["cards"][:3]) + ("; ..." if len(g["cards"]) > 3 else "")
            line = g["line"].replace("|", "\\|")
            out.append(f"| {i} | {g['score']} | {g['copies']} | {g['unlock_copies']} | {g['decks']} | {line} | {cards} | {tag} |")
        out.append("")
    if report["missing_cards"]:
        out.append("Not in the card database: " + ", ".join(report["missing_cards"]) + "\n")
    return "\n".join(out)


def save_report(report: dict, dest: Path, top: int = 40) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "README.md").write_text(format_report(report, top))
    (dest / "summary.json").write_text(json.dumps(report, indent=1) + "\n")
    with open(dest / "ranked.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["status", "score", "copies", "unlock_copies", "decks", "line", "cards", "families", "blocked_by"])
        for key in ("candidates", "blocked"):
            for g in report[key]:
                w.writerow([key, g["score"], g["copies"], g["unlock_copies"], g["decks"], g["line"],
                            "; ".join(g["cards"]), "; ".join(g["families"]), "; ".join(g["blocked_by"])])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m mtgsim.deck_gaps", description=__doc__.splitlines()[0])
    ap.add_argument("--save", type=Path, help="write README.md, summary.json and ranked.csv here")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    report = measure(CardDB(), deck_refs())
    if args.save:
        save_report(report, args.save, args.top)
    print(json.dumps(report, indent=1) if args.json else format_report(report, args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
