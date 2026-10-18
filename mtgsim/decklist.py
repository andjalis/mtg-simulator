"""Parse plain-text decklists.

Accepts Arena / MTGO / Moxfield exports ("4 Lightning Bolt", "4x Lightning Bolt",
"4 Lightning Bolt (M10) 146") and pasted tables with section headings and
tab-separated columns ("2<TAB>Iymrith, Desert Doom<TAB>Blue"). Lines that don't
start with a count are treated as headings and skipped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

LINE = re.compile(r"^(\d+)\s*x?\s+(.+?)\s*(?:\([A-Za-z0-9]{2,6}\)\s*[\w-]*\s*)?(?:\*F\*)?$")
COUNT_THEN_NAME = re.compile(r"^\d+\s*x?\s+\S")
SIDEBOARD = re.compile(r"^(sideboard|companion|maybeboard)\b|^sb:", re.I)


@dataclass
class Decklist:
    main: dict[str, int] = field(default_factory=dict)
    sideboard: dict[str, int] = field(default_factory=dict)
    # card -> the "Bring in vs." note from a fourth table column, e.g. {"Duress": "Control"}
    bring_in: dict[str, str] = field(default_factory=dict)


def parse_full(text: str) -> Decklist:
    """Main deck, sideboard, and any per-card "bring in vs." notes."""
    out = Decklist()
    target = out.main
    for raw in text.splitlines():
        # Only a genuinely blank line separates an MTGO sideboard. Comments
        # may appear between main-deck sections, including after card 60.
        if raw.lstrip().startswith(("#", "//")):
            continue
        line = raw.split("//")[0] if "//" in raw and not re.search(r"\w\s//\s\w", raw) else raw
        line = line.split("#")[0].strip()
        if not line:
            if target is out.main and sum(out.main.values()) >= 60 and "\t" not in text:
                target = out.sideboard  # MTGO export: a blank line after the main deck starts the sideboard
            continue
        sb_line = re.match(r"^sb:\s*", line, re.I)
        if sb_line:
            line = line[sb_line.end():]
        elif line.casefold() in {"deck", "mainboard", "main deck"}:
            target = out.main
            continue
        elif SIDEBOARD.match(line):
            if line.lower().startswith("maybeboard"):
                break
            target = out.sideboard
            continue
        if not COUNT_THEN_NAME.match(line):
            continue  # a heading such as "Creatures (6)" or "Qty  Card Name  Color"
        note = ""
        if "\t" in line:
            # Empty cells still occupy columns: dropping them can turn a
            # color into a card name or discard the fourth-column note.
            cols = [c.strip() for c in line.split("\t")]
            if len(cols) < 2 or not cols[1]:
                continue
            line = f"{cols[0]} {cols[1]}"
            note = cols[3] if len(cols) > 3 else ""
        m = LINE.match(line)
        if not m or int(m[1]) == 0:
            continue
        name = m[2].split(" // ")[0].strip()  # double-faced / split cards by their front face
        dest = out.sideboard if sb_line else target
        dest[name] = dest.get(name, 0) + int(m[1])
        if note and dest is out.sideboard:
            out.bring_in[name] = note
    return out


def parse_decklist(text: str) -> dict[str, int]:
    """Return {card name: count} for the main deck; see parse_full for the sideboard."""
    return parse_full(text).main


def load_deck(path: str | Path) -> tuple[str, dict[str, int]]:
    path = Path(path)
    return path.stem, parse_decklist(path.read_text(encoding="utf-8"))


def load_deck_full(path: str | Path) -> tuple[str, Decklist]:
    path = Path(path)
    return path.stem, parse_full(path.read_text(encoding="utf-8"))
