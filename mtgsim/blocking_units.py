"""Rank the parts of ignored rules text that block partly supported cards.

    python3 -m mtgsim.database_coverage --save results/database_coverage
    python3 -m mtgsim.blocking_units results/database_coverage/cards.csv --save results/blocking_units

A whole ignored line is a poor work unit: most lines are unique. This splits each line into the
part the parser rejects (an activated ability's cost or effect, a trigger's head or effect, or a
plain sentence), normalises numbers, mana symbols and colours, and ranks the parts by the cards
they would complete. Each unit is assigned to a work lane:

    effect      a sentence the effect parser does not match (spells, statics, other lines)
    ability     a sentence in an activated ability's effect whose cost already parses
    trigger     a trigger head ("Whenever ...,") the trigger grammar does not match
    cost        an activated ability cost part the cost parser does not model
    mechanic    a keyword or named mechanic line (banding, splice, Attractions, Rooms ...)

`sole` counts cards whose only blocking unit is this one: fixing it alone completes them.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .cards import parse as P

COLORS = r"\b(white|blue|black|red|green|colorless|multicolored|monocolored)\b"
COST_VERBS = ("Sacrifice", "Discard", "Pay", "Remove", "Exile", "Tap", "Return", "Mill", "Put", "Exert")
MECHANIC_HEADS = re.compile(r"crank this contraption|this siege|unlock this door|this room|attraction|spellbook|"
                            r"becomes prepared|visit|this class|this saga", re.I)
LANES = ("effect", "ability", "trigger", "cost", "mechanic")


def norm(text: str) -> str:
    s = text.strip().lower().rstrip(".")
    s = re.sub(r"\([^)]*\)", "", s)                   # reminder text
    s = re.sub(r"(\{[^}]+\})+", "{M}", s)
    s = re.sub(r"[+-]?\b(\d+|x)\b(?=/)", "N", s)
    s = re.sub(r"(?<=/)[+-]?(\d+|x)\b", "N", s)
    s = re.sub(r"\b\d+\b", "N", s)
    s = re.sub(r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\b", "N", s)
    s = re.sub(COLORS, "COLOR", s)
    return re.sub(r"\s+", " ", s).strip()


def _bad_sentences(body: str) -> list:
    try:
        effects, bad = P._parse_effects(body)
    except Exception:
        return [body]
    return list(bad) if bad else ([] if effects else [body])


def _keyword_line(line: str) -> bool:
    words = re.sub(r"\{[^}]+\}|\d+|—.*", "", line).split()
    return 0 < len(words) <= 3 and not re.search(r"\b(target|you|each|~|draw|deal|create)\b", line, re.I)


def units(line: str):
    """(lane, normalised unit) pairs that block one ignored line."""
    line = line.strip()
    if _keyword_line(line):
        return [("mechanic", norm(line))]
    ability = re.fullmatch(r"([^:\"•]+?): (.+)", line)
    if ability and (ability[1].startswith("{") or ability[1].split()[0] in COST_VERBS):
        out = [] if P._parse_ability_cost(ability[1]) else [("cost", norm(ability[1]))]
        out += [("ability", norm(s)) for s in _bad_sentences(ability[2])]
        return out or [("ability", norm(line))]
    trigger = re.match(r"(Whenever|When|At) ([^,]+), (.+)", line)
    if trigger:
        head = f"{trigger[1]} {trigger[2]}"
        out = []
        if P._parse_trigger_line(f"{head}, you gain 1 life.") is None:
            out.append(("mechanic" if MECHANIC_HEADS.search(head) else "trigger", norm(head)))
        out += [("effect", norm(s)) for s in _bad_sentences(trigger[3])]
        return out or [("trigger", norm(head))]
    lane = "mechanic" if MECHANIC_HEADS.search(line) else "effect"
    return [(lane, norm(s)) for s in _bad_sentences(line)] or [(lane, norm(line))]


def rank(cards_csv: Path):
    csv.field_size_limit(sys.maxsize)
    affected, sole, examples = defaultdict(set), Counter(), defaultdict(list)
    partial = 0
    with cards_csv.open(encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["status"] != "partial":
                continue
            partial += 1
            found = {u for line in row["ignored_text"].split("\n") if line.strip() for u in units(line)}
            for u in found:
                affected[u].add(row["name"])
                if len(examples[u]) < 3:
                    examples[u].append(row["name"])
            if len(found) == 1 and not row["simplifications"]:
                sole[next(iter(found))] += 1
    rows = sorted(affected, key=lambda u: (-sole[u], -len(affected[u]), u))
    return partial, [(u[0], u[1], sole[u], len(affected[u]), examples[u]) for u in rows]


def save(partial, rows, dest: Path, top: int):
    dest.mkdir(parents=True, exist_ok=True)
    with (dest / "units.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["lane", "unit", "sole", "affected_cards", "examples"])
        for lane, unit, n_sole, n_aff, ex in rows:
            writer.writerow([lane, unit, n_sole, n_aff, "; ".join(ex)])
    lines = [f"# Blocking units\n\n{partial:,} partly supported cards, {len(rows):,} distinct blocking units.\n",
             "| Lane | Units | Cards completed by fixing one unit |", "| --- | ---: | ---: |"]
    for lane in LANES:
        mine = [r for r in rows if r[0] == lane]
        lines.append(f"| {lane} | {len(mine):,} | {sum(r[2] for r in mine):,} |")
    for lane in LANES:
        lines += [f"\n## {lane}\n", "| Sole | Affected | Unit | Examples |", "| ---: | ---: | --- | --- |"]
        for _, unit, n_sole, n_aff, ex in [r for r in rows if r[0] == lane][:top]:
            cell = unit.replace("|", r"\|")
            lines.append(f"| {n_sole} | {n_aff} | {cell} | {'; '.join(ex)} |")
    (dest / "README.md").write_text("\n".join(lines) + "\n\n[All units](units.csv)\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cards_csv", type=Path, help="cards.csv from python3 -m mtgsim.database_coverage --save DIR")
    ap.add_argument("--save", type=Path, metavar="DIR", help="write README.md and units.csv")
    ap.add_argument("--top", type=int, default=40, help="rows per lane in the README (default 40)")
    args = ap.parse_args(argv)
    partial, rows = rank(args.cards_csv)
    if args.save:
        save(partial, rows, args.save, args.top)
    for lane in LANES:
        mine = [r for r in rows if r[0] == lane]
        print(f"{lane:9} {len(mine):6,} units, {sum(r[2] for r in mine):6,} cards completed by a single unit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
