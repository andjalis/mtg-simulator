"""Measure every card in the offline database and rank remaining coverage gaps.

    python3 -m mtgsim.database_coverage
    python3 -m mtgsim.database_coverage --save results/database_coverage --progress
    python3 -m mtgsim.database_coverage --json --top 10

Uses MTGSIM_CARDDB when configured. Counts distinct database entries, including
basic lands, using the same lookup and classification as deck coverage. No network
requests or games are needed. Parse failures are reported and cause exit status 1.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .carddb import CardDB
from .coverage import FULL, PARTIAL, SIMPLIFIED, CardCoverage, _faces, card_coverage
from .standard_coverage import families

PARSE_ERROR = "parse_error"
LABELS = [(FULL, "Fully template-matched"), (SIMPLIFIED, "Matched with recorded simplifications"),
          (PARTIAL, "Partly supported"), (PARSE_ERROR, "Could not parse")]


@dataclass
class Gap:
    label: str
    affected: set[str] = field(default_factory=set)
    candidates: set[str] = field(default_factory=set)
    weight: float = 0.0              # summed play weight of the candidates (0 without --weights)

    def as_dict(self):
        extra = {"weighted_potential": round(self.weight, 3)} if self.weight else {}
        return {"gap": self.label, "affected_cards": len(self.affected), **extra,
                "potential_full_matches": len(self.candidates),
                "examples": sorted(self.candidates or self.affected)[:3]}


def ranked(gaps, weighted=False):
    """By potential full matches, or (weighted) by the play weight those matches carry."""
    lead = (lambda g: -g.weight) if weighted else (lambda g: 0)
    return sorted(gaps.values(), key=lambda g: (lead(g), -len(g.candidates), -len(g.affected), g.label))


@dataclass
class DatabaseReport:
    measured_on: str = field(default_factory=lambda: datetime.now(timezone.utc).date().isoformat())
    rows: list[CardCoverage] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    families: dict[str, Gap] = field(default_factory=dict)
    wording: dict[str, Gap] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)    # play weights by card name (empty = unweighted)

    @property
    def counts(self):
        return Counter(row.status for row in self.rows)

    def as_dict(self, top=15):
        counts = self.counts
        return {"measured_on": self.measured_on, "total": len(self.rows),
                "counts": {status: counts[status] for status, _ in LABELS}, "parse_errors": self.errors,
                "ranking_method": "Potential full matches have every ignored line in the gap and no recorded simplifications. "
                                  "Counts are upper bounds, overlap, and must not be summed.",
                "unclassified": self.families.get("unclassified", Gap("unclassified")).as_dict(),
                "families": [g.as_dict() for g in ranked(self.families, bool(self.weights)) if g.label != "unclassified"][:top],
                "exact_wording": [g.as_dict() for g in ranked(self.wording, bool(self.weights))[:top]]}


def card_weight(report, name):
    w = report.weights
    return w.get(name, w.get(name.split(" // ")[0], 0.0)) if w else 0.0


def record_gaps(report, row, ignored):
    """Count each card once per gap; all its missing lines must fit to qualify."""
    lines = {re.sub(r"\s+", " ", line).strip().lower() for line in ignored if line.strip()}
    if not lines:
        return
    line_families = [set(families(line)) or {"unclassified"} for line in lines]
    for name in set.union(*line_families):
        gap = report.families.setdefault(name, Gap(name))
        gap.affected.add(row.name)
        if not row.simplified and all(name in group for group in line_families):
            gap.candidates.add(row.name)
            gap.weight += card_weight(report, row.name)
    for line in lines:
        gap = report.wording.setdefault(line, Gap(line))
        gap.affected.add(row.name)
        if len(lines) == 1 and not row.simplified:
            gap.candidates.add(row.name)
            gap.weight += card_weight(report, row.name)


def measure(db, progress=None, weights=None):
    if db._all is None:
        raise ValueError("no card database; run python3 -m mtgsim.build_carddb first")
    names = [r[0] for r in db._all.execute("SELECT name FROM cards ORDER BY key")]
    report = DatabaseReport(weights=weights or {})
    for i, name in enumerate(names, 1):
        try:
            card = db.get(name)
            row = card_coverage(card)
            # Front faces are not unique: distinct database entries can share one.
            row.name = name
        except Exception as exc:
            # An incomplete parser must not hide failed entries or stop the census.
            error = f"{type(exc).__name__}: {exc}"
            report.errors.append({"name": name, "error": error})
            row = CardCoverage(name, 1, PARSE_ERROR, [error])
        else:
            if row.status == PARTIAL:
                # Raw ignored text avoids a different group for every back-face name.
                record_gaps(report, row, [line for face in _faces(card) for line in face.unsupported])
        report.rows.append(row)
        if progress and (i % 5000 == 0 or i == len(names)):
            progress(i, len(names))
    return report


def _share(n, total):
    pct = 100 * n / total if total else 0
    return "<0.01%" if 0 < pct < .01 else f"{pct:.2f}%"


def _cell(text):
    return text.replace("|", "\\|").replace("\n", " ")


def format_report(report, top=15):
    counts, total = report.counts, len(report.rows)
    lines = ["# Entire local card database coverage", "", f"Measured {report.measured_on} against the current working tree.", "",
             "| Status | Cards | Share |", "| --- | ---: | ---: |"]
    for status, label in LABELS:
        lines.append(f"| {label} | {counts[status]:,} | {_share(counts[status], total)} |")
    lines += [f"| Total | {total:,} | {'100%' if total else '0%'} |", "",
              "Counts include every distinct database entry, including basic lands and cards outside Standard. "
              "Printings and face-name aliases are not counted separately. CardDB lookup and card_coverage classification "
              "match the deck coverage reports.", "",
              "Fully template-matched means no rules text is reported as ignored or simplified. This measures template "
              "coverage; complete Magic rules correctness is not verified.", "",
              "## Missing effects ranked by potential full matches", "",
              "A potential full match has every ignored line in the listed gap and no recorded simplifications. "
              "These are upper bounds: an entire family may need many implementations. Families overlap, so counts "
              "must not be summed. Exact wording groups ignore case and whitespace, preserve numbers, and do not "
              "merge differently worded effects."]
    other = report.families.get("unclassified")
    if other:
        lines += ["", f"Unclassified wording affects {len(other.affected):,} cards; {len(other.candidates):,} have all "
                  "their remaining gaps unclassified. This bucket is separate from the effect-family ranking."]
    if report.weights:
        lines += ["", "Gaps are ranked by the play weight of the cards they would unlock "
                  f"({sum(1 for r in report.rows if card_weight(report, r.name)):,} cards carry a weight), then by potential full matches."]
    for title, gaps in (("Effect families", report.families), ("Exact ignored wording", report.wording)):
        if not top:
            continue
        wt = bool(report.weights)
        lines += ["", f"### {title}", "", "| Gap | Potential full matches | " + ("Play weight | " if wt else "") + "Cards affected | Examples |",
                  "| --- | ---: | " + ("---: | " if wt else "") + "---: | --- |"]
        ordered = [g for g in ranked(gaps, bool(report.weights)) if title != "Effect families" or g.label != "unclassified"]
        for gap in ordered[:top]:
            g = gap.as_dict()
            lines.append(f"| {_cell(gap.label)} | {g['potential_full_matches']:,} | "
                         + (f"{gap.weight:.2f} | " if wt else "") + f"{g['affected_cards']:,} | "
                         f"{_cell('; '.join(g['examples']))} |")
    if report.errors:
        lines += ["", "## Parser errors", ""]
        lines += [f"- {_cell(e['name'])}: {_cell(e['error'])}" for e in report.errors]
    return "\n".join(lines) + "\n"


def save_report(report, dest, top=15):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    links = "\n[Every card](cards.csv) · [All ranked gaps](gaps.csv) · [Machine-readable summary](summary.json)\n"
    (dest / "README.md").write_text(format_report(report, top) + links, encoding="utf-8")
    (dest / "summary.json").write_text(json.dumps(report.as_dict(top), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (dest / "cards.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["name", "status", "ignored_text", "simplifications"])
        for row in report.rows:
            writer.writerow([row.name, row.status, "\n".join(row.ignored), "\n".join(row.simplified)])
    with (dest / "gaps.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["kind", "gap", "potential_full_matches", "affected_cards", "examples"])
        for kind, gaps in (("family", report.families), ("exact_wording", report.wording)):
            for gap in ranked(gaps, bool(report.weights)):
                g = gap.as_dict()
                writer.writerow([kind, gap.label, g["potential_full_matches"], g["affected_cards"], "; ".join(g["examples"])])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--save", type=Path, metavar="DIR", help="save Markdown, JSON, per-card CSV and ranked-gap CSV")
    ap.add_argument("--json", action="store_true", help="print the summary and top rankings as JSON")
    ap.add_argument("--top", type=int, default=15, help="number of rows in each ranking (default 15)")
    ap.add_argument("--weights", type=Path, nargs="+", metavar="FILE",
                    help="play-weight JSON files (see mtgsim.play_weights); gaps are then ranked by the weight they unlock")
    ap.add_argument("--progress", action="store_true", help="report progress on stderr")
    args = ap.parse_args(argv)
    if args.top < 0:
        ap.error("--top must be nonnegative")
    db = CardDB(offline=True)
    if db._all is None:
        print("error: no card database; run python3 -m mtgsim.build_carddb first", file=sys.stderr)
        return 2
    progress = (lambda i, total: print(f"Measured {i:,} / {total:,} cards", file=sys.stderr, flush=True)) if args.progress else None
    try:
        weights = None
        if args.weights:
            from .play_weights import load
            weights = load(args.weights)
        report = measure(db, progress, weights)
        if args.save:
            save_report(report, args.save, args.top)
        print(json.dumps(report.as_dict(args.top), indent=2, ensure_ascii=False) if args.json else format_report(report, args.top), end="\n")
        return 1 if report.errors else 0
    finally:
        db._all.close()


if __name__ == "__main__":
    sys.exit(main())
