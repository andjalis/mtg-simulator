"""Parse plain-text decklists.

Accepts Arena / MTGO / Moxfield exports ("4 Lightning Bolt", "4x Lightning Bolt",
"4 Lightning Bolt (M10) 146") and pasted tables with section headings and
tab-separated columns ("2<TAB>Iymrith, Desert Doom<TAB>Blue"). Lines that don't
start with a count are treated as headings and skipped.
"""
from __future__ import annotations

import re
from pathlib import Path

LINE = re.compile(r"^(\d+)\s*x?\s+(.+?)\s*(?:\([A-Za-z0-9]{2,6}\)\s*[\w-]*\s*)?(?:\*F\*)?$")
COUNT_THEN_NAME = re.compile(r"^\d+\s*x?\s+\S")
SIDEBOARD = re.compile(r"^(sideboard|companion|maybeboard)\b|^sb:", re.I)


def parse_decklist(text: str) -> dict[str, int]:
    """Return {card name: count} for the main deck; the sideboard is ignored."""
    deck: dict[str, int] = {}
    for raw in text.splitlines():
        line = raw.split("//")[0] if "//" in raw and not re.search(r"\w\s//\s\w", raw) else raw
        line = line.split("#")[0].strip()
        if not line:
            if sum(deck.values()) >= 60 and "\t" not in text:
                break  # MTGO export: a blank line after the main deck starts the sideboard
            continue
        if SIDEBOARD.match(line):
            break
        if not COUNT_THEN_NAME.match(line):
            continue  # a heading such as "Creatures (6)" or "Qty  Card Name  Color"
        if "\t" in line:
            cols = [c.strip() for c in line.split("\t") if c.strip()]
            line = f"{cols[0]} {cols[1]}"
        m = LINE.match(line)
        if not m:
            continue
        name = m[2].split(" // ")[0].strip()  # double-faced / split cards by their front face
        deck[name] = deck.get(name, 0) + int(m[1])
    return deck


def load_deck(path: str | Path) -> tuple[str, dict[str, int]]:
    path = Path(path)
    return path.stem, parse_decklist(path.read_text(encoding="utf-8"))
