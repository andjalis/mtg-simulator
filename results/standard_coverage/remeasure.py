"""Reproduce the saved-snapshot measurement and unmatched-line rankings.

Run from the repo root: python3 -m results.standard_coverage.remeasure
Writes remeasure.json and remeasure.txt beside this script. No network access.
"""
import hashlib
import json
import platform
from collections import defaultdict
from pathlib import Path

from mtgsim.carddb import ALL_CARDS, BUILTIN, CACHE, CardDB
from mtgsim.standard_coverage import SAVED, format_report, measure, standard_cards


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main(output_stem="remeasure"):
    db = CardDB(offline=True)
    if db._all is None:
        raise SystemExit("Build the card database before measuring coverage")
    try:
        fmt, names = standard_cards(SAVED)
        rep = measure(names, db, fmt)
        all_lines, single_lines = defaultdict(set), defaultdict(set)
        for name, ignored in rep.partial.items():
            card = db.get(name)
            # Coverage prefixes back/adventure-face names; remove only that prefix.
            prefixes = tuple(f.name + ": " for f in (card.back, card.adventure) if f)
            for line in ignored:
                for prefix in prefixes:
                    if line.startswith(prefix):
                        line = line[len(prefix):]
                        break
                all_lines[line].add(name)
                if len(ignored) == 1:
                    single_lines[line].add(name)

        def ranked(groups):
            return [{"line": line, "cards": len(cards), "examples": sorted(cards)[:3]}
                    for line, cards in sorted(groups.items(), key=lambda row: (-len(row[1]), row[0]))[:20]]

        data = {
            "python": platform.python_version(),
            "inputs_sha256": {
                "carddb": digest(ALL_CARDS), "builtin": digest(BUILTIN), "cache": digest(CACHE),
                "snapshot": {str(p.relative_to(SAVED)): digest(p)
                             for p in sorted(SAVED.rglob("*.txt"))},
            },
            "format": fmt, "total": rep.total, "status": dict(rep.status),
            "one_line": rep.one_line, "sentences": rep.sentences,
            "handled_sentences": rep.sentences - rep.ignored_sentences,
            "all_unmatched": ranked(all_lines), "single_line_misses": ranked(single_lines),
        }
        output = Path(__file__).resolve().parent
        (output / f"{output_stem}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        text = format_report(rep, top=20) + "\n"
        for title, key in (("All unmatched lines", "all_unmatched"),
                           ("Cards missing exactly one line", "single_line_misses")):
            text += f"\n{title} (top 20; count distinct cards, ties alphabetical):\n"
            for row in data[key][:20]:
                text += f"{row['cards']:4}  {row['line']}\n"
        (output / f"{output_stem}.txt").write_text(text, encoding="utf-8")
        print(text, end="")
    finally:
        db._all.close()


if __name__ == "__main__":
    main()
