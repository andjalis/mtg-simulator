"""Card coverage: which cards in a deck the built-in engine plays fully, plays in a simplified
way, plays only partly (some rules text is ignored), or doesn't know at all."""
from __future__ import annotations

from dataclasses import dataclass, field

from .carddb import CardDB
from .cards import CardDef

FULL, SIMPLIFIED, PARTIAL, UNKNOWN = "full", "simplified", "partial", "unknown"


@dataclass
class CardCoverage:
    name: str
    copies: int
    status: str                                    # full, simplified, partial or unknown
    ignored: list = field(default_factory=list)    # rules text the engine ignores
    simplified: list = field(default_factory=list)  # rules text the engine plays loosely


def _faces(card: CardDef):
    yield card
    for face in (card.back, card.adventure):
        if face is not None:
            yield face


def card_coverage(card: CardDef, copies: int = 1) -> CardCoverage:
    ignored, simplified = [], []
    for i, face in enumerate(_faces(card)):
        prefix = f"{face.name}: " if i else ""
        ignored += [prefix + line for line in face.unsupported]
        simplified += [prefix + line for line in face.approximations]
    status = PARTIAL if ignored else SIMPLIFIED if simplified else FULL
    return CardCoverage(card.name, copies, status, ignored, simplified)


def deck_coverage(db: CardDB, counts: dict[str, int]) -> list[CardCoverage]:
    """One row per distinct card, the least supported first. Cards missing from the card
    database (and from Scryfall, unless offline) are reported as unknown instead of raising."""
    rows = []
    for name, n in counts.items():
        try:
            rows.append(card_coverage(db.get(name), n))
        except KeyError:
            rows.append(CardCoverage(name, n, UNKNOWN, ["not in the card database"]))
    order = {UNKNOWN: 0, PARTIAL: 1, SIMPLIFIED: 2, FULL: 3}
    return sorted(rows, key=lambda r: (order[r.status], -r.copies, r.name))


def summary(rows: list[CardCoverage]) -> dict[str, int]:
    """Copies of cards in each status, plus the total."""
    out = {FULL: 0, SIMPLIFIED: 0, PARTIAL: 0, UNKNOWN: 0}
    for r in rows:
        out[r.status] += r.copies
    out["total"] = sum(r.copies for r in rows)
    return out


def format_coverage(deck: str, rows: list[CardCoverage]) -> str:
    s = summary(rows)
    pct = 100 * (s[FULL] + s[SIMPLIFIED]) / s["total"] if s["total"] else 100
    parts = [f"{s[FULL]} fully supported"] + [f"{s[k]} {label}" for k, label in
                                              ((SIMPLIFIED, "simplified"), (PARTIAL, "partly supported"),
                                               (UNKNOWN, "unknown")) if s[k]]
    lines = [f"{deck}: {pct:.0f}% playable as written ({', '.join(parts)}; {s['total']} cards)"]
    labels = {UNKNOWN: "unknown", PARTIAL: "partial", SIMPLIFIED: "simplified"}
    for r in rows:
        if r.status == FULL:
            continue
        notes = r.ignored if r.status != SIMPLIFIED else r.simplified
        lines.append(f"  {r.copies:>2} {r.name} [{labels[r.status]}]")
        lines += [f"       ignored: {t}" if r.status != SIMPLIFIED else f"       simplified: {t}" for t in notes]
        if r.status == PARTIAL:
            lines += [f"       simplified: {t}" for t in r.simplified]
    return "\n".join(lines)
