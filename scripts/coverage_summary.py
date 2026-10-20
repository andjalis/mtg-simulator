"""One-line coverage summary for reports: fully supported cards in Standard and in the whole card DB.

Run from the repo root: python3 -m scripts.coverage_summary
Offline; needs mtgsim/data/cards.sqlite3. "Fully supported" means every rules line matched a
template (the --coverage "full" status); it is a recognition count, not a rules-correctness claim.
"""
import sqlite3
import sys

from mtgsim.carddb import ALL_CARDS, CardDB
from mtgsim.coverage import FULL, card_coverage
from mtgsim.standard_coverage import SAVED, measure, standard_cards


def line(label, rep):
    full = rep.status[FULL]
    return (f"{label}: {full:,}/{rep.total:,} cards fully supported ({full / rep.total:.1%}), "
            f"{rep.sentence_share:.0%} of rules sentences handled")


def main():
    db = CardDB(offline=True)
    if db._all is None:
        sys.exit("Build the card database first: python3 -m mtgsim.build_carddb")
    fmt, names = standard_cards(SAVED)
    print(line("Standard", measure(names, db, fmt)))
    every = [r[0] for r in sqlite3.connect(f"file:{ALL_CARDS}?mode=ro", uri=True).execute(
        "SELECT name FROM cards ORDER BY name")]
    # A card whose text crashes the parser is a bug to fix, not a reason to lose the summary.
    crashed = []
    for name in every:
        try:
            card_coverage(db.get(name))
        except Exception as e:
            crashed.append((name, f"{type(e).__name__}: {e}"))
    bad = {n for n, _ in crashed}
    rep = measure([n for n in every if n not in bad], db)
    rep.total += len(crashed)
    print(line("All cards", rep) + (f"; {len(crashed)} cards crash the parser" if crashed else ""))
    for name, err in crashed[:10]:
        print(f"  crash: {name}: {err}")


if __name__ == "__main__":
    main()
