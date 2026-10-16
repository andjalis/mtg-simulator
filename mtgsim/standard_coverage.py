"""Coverage across all of Standard: how much of the format the built-in engine can play.

    python3 -m mtgsim.standard_coverage                   # from the saved set lists (offline)
    python3 -m mtgsim.standard_coverage --forge ~/forge   # from a Forge install or git checkout
    python3 -m mtgsim.standard_coverage --forge ~/forge --save DIR   # refresh the saved set lists
    python3 -m mtgsim.standard_coverage --cards           # also list every partly supported card

The Standard set list comes from Forge's format file (res/formats/Sanctioned/Standard.txt) and
the cards of each set from its edition file (res/editions/*.txt, the [cards] section). Coverage
reads card text only (`mtgsim.coverage`), no games are played. The card database must be built
first (`python3 -m mtgsim.build_carddb`).

Reported: cards fully supported / simplified / partly supported / unknown, how many partly
supported cards miss only one line, a rough share of rules sentences the engine handles, and the
rules-text families ignored most often (counted by cards), so a template PR can show its effect.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .carddb import CardDB
from .coverage import FULL, PARTIAL, SIMPLIFIED, UNKNOWN, card_coverage

SAVED = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "forge_scripts" / "standard"
BASICS = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}

# Rules-text families, matched against each ignored line (lower case). A line can belong to
# several families; each family counts a card once.
FAMILIES = [
    ("tokens", r"\btokens?\b"),
    ("graveyard", r"\bgraveyards?\b"),
    ("counters", r"\bcounters?\b(?! target)"),
    ("exile", r"\bexiled?\b"),
    ("sacrifice", r"\bsacrifices?\b"),
    ("auras/enchant", r"^enchant\b|\baura\b|\benchanted\b"),
    ("equipment", r"\bequip(?:ped|ment)?\b"),
    ("can't restrictions", r"\bcan't\b"),
    ("copy effects", r"\bcop(?:y|ies)\b"),
    ("library search", r"\bsearch (?:your|their|target player's) library\b"),
    ("transform", r"\btransforms?\b"),
    ("X costs", r"\{x\}|\bx costs\b|\bx is\b|\bwhere x\b"),
    ("cost reduction", r"\bcosts? \{?\d*\}? ?less\b|\bcosts? (?:\{\d\} )?less to cast\b"),
    ("mana restrictions", r"^mana restriction ignored\b|\bspend this mana only\b"),
    ("+1/+1 static (anthems)", r"\b(?:other )?creatures you control get \+"),
    ("activated abilities", r"^[^\"]*\{t\}[^:\"]*:|^\{[^}]+\}(?:, [^:]+)?:"),
    ("triggered (whenever/when)", r"^(?:whenever|when)\b"),
    ("modal (choose)", r"\bchoose (?:one|two|three|any number|up to)\b"),
] + [(f"set: {name}", rf"\b{name}\b") for name in (
    "saddle", "station", "craft", "warp", "gift", "exhaust", "plot", "bargain", "disguise",
    "max speed", "room", "earthbend", "manifest dread", "offspring", "forage", "harmonize",
    "mobilize", "flurry", "renew", "endure", "behold", "airbend", "waterbend", "firebend",
    "impending", "eerie", "survival", "valiant", "expend", "threshold", "descend", "discover",
    "map", "food", "role", "collect evidence", "suspect", "cloak", "case", "spree", "crime",
)]
_FAMILY_RE = [(name, re.compile(rx)) for name, rx in FAMILIES]


def families(line: str) -> list[str]:
    low = line.lower()
    return [name for name, rx in _FAMILY_RE if rx.search(low)]


# ---------------------------------------------------------------- Forge format and edition files

def forge_res(path: Path) -> Path:
    """The res folder of a Forge install (DIR/res), a git checkout (DIR/forge-gui/res), a res
    folder itself, or a saved snapshot."""
    path = Path(path).expanduser()
    for cand in (path, path / "res", path / "forge-gui" / "res"):
        if (cand / "formats").is_dir() and (cand / "editions").is_dir():
            return cand
    raise FileNotFoundError(f"No formats/ and editions/ folders under {path}")


def parse_format(text: str) -> dict:
    """Name, set codes and banned cards of a Forge format file."""
    out = {"name": "", "sets": [], "banned": []}
    for line in text.splitlines():
        key, _, val = line.partition(":")
        if key == "Name":
            out["name"] = val.strip()
        elif key == "Sets":
            out["sets"] = [s.strip() for s in val.split(",") if s.strip()]
        elif key == "Banned":
            out["banned"] = [s.strip() for s in val.split(";") if s.strip()]
    return out


def find_format(res: Path, name: str = "Standard") -> dict:
    for f in sorted((res / "formats").rglob("*.txt")):
        fmt = parse_format(f.read_text(encoding="utf-8", errors="replace"))
        if fmt["name"].lower() == name.lower():
            return fmt
    raise KeyError(f"No format named {name} under {res / 'formats'}")


_CARD_LINE = re.compile(r"^\S+\s+(?:[CURMSLT]\s+)?(.+?)(?:\s+@.*)?$")


def parse_edition(text: str) -> tuple[str, str, list[str]]:
    """(set code, set name, card names in the [cards] section, in collector order)."""
    code = name = ""
    cards, section = [], None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line.strip("[]").strip().lower()
            continue
        if section == "metadata":
            key, _, val = line.partition("=")
            if key == "Code":
                code = val.strip()
            elif key == "Name":
                name = val.strip()
        elif section == "cards" and line:
            m = _CARD_LINE.match(line)
            if m:
                cards.append(m[1].strip())
    return code, name, cards


def editions(res: Path, codes) -> dict[str, tuple[str, list[str]]]:
    """Set code -> (set name, card names) for the given codes."""
    want, out = set(codes), {}
    for f in sorted((res / "editions").glob("*.txt")):
        code, name, cards = parse_edition(f.read_text(encoding="utf-8", errors="replace"))
        if code in want:
            out[code] = (name, cards)
    return out


def standard_cards(res: Path, fmt_name: str = "Standard") -> tuple[dict, list[str]]:
    """(format, distinct non-basic card names in its sets, sorted)."""
    fmt = find_format(res, fmt_name)
    sets = editions(res, fmt["sets"])
    missing = [c for c in fmt["sets"] if c not in sets]
    if missing:
        raise KeyError(f"No edition file for set(s) {', '.join(missing)}")
    names = {n for _, cards in sets.values() for n in cards} - BASICS
    return fmt, sorted(names)


def save_snapshot(res: Path, dest: Path, fmt_name: str = "Standard") -> int:
    """Write the format file and trimmed edition files (code, name, [cards] names) to dest, so the
    report can be reproduced without a Forge install. Returns the number of edition files."""
    fmt = find_format(res, fmt_name)
    (dest / "formats").mkdir(parents=True, exist_ok=True)
    (dest / "editions").mkdir(parents=True, exist_ok=True)
    for old in (dest / "editions").glob("*.txt"):
        old.unlink()
    (dest / "formats" / f"{fmt['name']}.txt").write_text(
        f"[format]\nName:{fmt['name']}\nSets:{', '.join(fmt['sets'])}\nBanned:{'; '.join(fmt['banned'])}\n",
        encoding="utf-8")
    sets = editions(res, fmt["sets"])
    for code, (name, cards) in sets.items():
        body = "".join(f"{i} {c}\n" for i, c in enumerate(cards, 1))
        (dest / "editions" / f"{code}.txt").write_text(
            f"[metadata]\nCode={code}\nName={name}\n\n[cards]\n{body}", encoding="utf-8")
    return len(sets)


# ---------------------------------------------------------------- the report

def _sentences(text: str) -> int:
    text = re.sub(r"\([^)]*\)", "", text)
    return len([s for s in re.split(r"(?<=[.!?])\s+|\n+", text) if re.search(r"\w", s)])


@dataclass
class Report:
    fmt: dict
    total: int = 0
    status: Counter = field(default_factory=Counter)
    one_line: int = 0                                  # partly supported cards missing one line
    sentences: int = 0
    ignored_sentences: int = 0
    families: Counter = field(default_factory=Counter)  # family -> cards
    partial: dict = field(default_factory=dict)        # card name -> ignored lines

    @property
    def sentence_share(self) -> float:
        return 1 - self.ignored_sentences / self.sentences if self.sentences else 1.0


def measure(names, db: CardDB, fmt: dict | None = None) -> Report:
    rep = Report(fmt or {})
    for name in names:
        rep.total += 1
        try:
            card = db.get(name)
        except KeyError:
            rep.status[UNKNOWN] += 1
            continue
        cov = card_coverage(card)
        rep.status[cov.status] += 1
        faces = [card] + [f for f in (card.back, card.adventure) if f is not None]
        rep.sentences += sum(_sentences(f.oracle) for f in faces) or 1
        if cov.status != PARTIAL:
            continue
        rep.partial[name] = cov.ignored
        rep.ignored_sentences += sum(max(1, _sentences(line)) for line in cov.ignored)
        if len(cov.ignored) == 1:
            rep.one_line += 1
        for fam in {f for line in cov.ignored for f in families(line)}:
            rep.families[fam] += 1
    rep.ignored_sentences = min(rep.ignored_sentences, rep.sentences)
    return rep


def format_report(rep: Report, top: int = 25, cards: bool = False) -> str:
    sets = rep.fmt.get("sets", [])
    head = f"{rep.fmt.get('name', 'Format')}: {rep.total:,} distinct non-basic cards"
    if sets:
        head += f" from {len(sets)} sets ({sets[0]} to {sets[-1]})"
    lines = [head, "", f"{'Status':<52}{'Cards':>7}{'Share':>8}"]
    labels = [(FULL, "Fully supported (every line matched by a template)"),
              (SIMPLIFIED, "Simplified (all lines matched, some played loosely)"),
              (PARTIAL, "Partly supported (at least one line ignored)"),
              (UNKNOWN, "Unknown to the card database")]
    for key, label in labels:
        n = rep.status[key]
        lines.append(f"{label:<52}{n:>7,}{100 * n / rep.total if rep.total else 0:>7.1f}%")
    lines += ["", f"Partly supported cards that miss only one line: {rep.one_line:,}",
              f"Rules sentences handled (rough): {100 * rep.sentence_share:.0f}% "
              f"({rep.sentences - rep.ignored_sentences:,} of {rep.sentences:,})",
              "", f"Most ignored families (cards with at least one ignored line in the family, top {top}):"]
    for fam, n in rep.families.most_common(top):
        lines.append(f"  {fam:<34}{n:>6,}")
    if cards:
        lines += ["", "Partly supported cards:"]
        for name, ignored in sorted(rep.partial.items()):
            lines.append(f"  {name}")
            lines += [f"       ignored: {t}" for t in ignored]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m mtgsim.standard_coverage", description=__doc__.split("\n\n")[0])
    ap.add_argument("--forge", metavar="DIR", help="a Forge install or git checkout (default: the saved set lists)")
    ap.add_argument("--format", default="Standard", help="Forge format name (default Standard)")
    ap.add_argument("--save", metavar="DIR", nargs="?", const=str(SAVED),
                    help=f"with --forge: save the format and set lists for offline use (default {SAVED})")
    ap.add_argument("--top", type=int, default=25, help="how many families to list")
    ap.add_argument("--cards", action="store_true", help="also list every partly supported card")
    args = ap.parse_args(argv)
    try:
        res = forge_res(Path(args.forge)) if args.forge else SAVED
        if args.save:
            if not args.forge:
                ap.error("--save needs --forge")
            n = save_snapshot(res, Path(args.save), args.format)
            print(f"Saved the {args.format} format and {n} set lists to {args.save}", file=sys.stderr)
        fmt, names = standard_cards(res, args.format)
    except (FileNotFoundError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    db = CardDB(offline=True)
    if db._all is None:
        print("error: no card database; run python3 -m mtgsim.build_carddb first", file=sys.stderr)
        return 2
    print(format_report(measure(names, db, fmt), args.top, args.cards))
    return 0


if __name__ == "__main__":
    sys.exit(main())
