"""Command line entry point.

    python -m mtgsim DECK_A DECK_B [-n GAMES] [--seed S]      head-to-head
    python -m mtgsim DECK --gauntlet OPP1 OPP2 ... [-n GAMES]  one deck vs a field
    python -m mtgsim --round-robin DECK1 DECK2 DECK3 ...        everyone vs everyone
    python -m mtgsim DECK --ladder                             climb the ranks, Bronze to Grandmaster
    python -m mtgsim DECK --rank master [diamond ... | all]    one deck vs whole rank pools (--list-ranks)
    python -m mtgsim DECK ... --coverage                       which cards the built-in engine can't fully play

Add --engine forge --forge-dir PATH to play the games in Forge instead.
"""
from __future__ import annotations

import argparse
import itertools
import sys

from . import history
from .carddb import CardDB
from .coverage import deck_coverage, format_coverage
from .decklist import load_deck
from .forge import ForgeError, run_forge_match
from .ladder_report import HtmlReport, TerminalView, text_summary
from .rating import LadderTracker
from .runner import build_deck, run_match, unsupported_report, wilson
from .ranks import PASS_RATE, RANKS, list_ranks, resolve_ranks


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mtgsim", description="Simulate Magic games between decklists.")
    ap.add_argument("decks", nargs="*", help="decklist text files")
    ap.add_argument("-n", "--games", type=int, default=500, help="games per pairing (default 500)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--gauntlet", nargs="+", metavar="OPP", help="play the first deck against each of these")
    ap.add_argument("--round-robin", action="store_true", help="play every deck against every other deck")
    ap.add_argument("--ladder", action="store_true",
                    help="climb the ranks (Bronze, Silver, Gold, Platinum, Diamond, Master, Grandmaster) "
                         "until a rank is failed")
    ap.add_argument("--full-ladder", action="store_true", help="with --ladder: keep playing after a failed rank")
    ap.add_argument("--pass-rate", type=float, default=PASS_RATE,
                    help=f"with --ladder: win rate needed to clear a rank (default {PASS_RATE})")
    ap.add_argument("--rank", "--tier", dest="rank", nargs="+", metavar="R",
                    help="play the deck against every deck in these ranks (names, numbers 1-7, or all)")
    ap.add_argument("--list-ranks", "--list-tiers", dest="list_ranks", action="store_true",
                    help="show the ranks and their decks")
    ap.add_argument("--coverage", action="store_true",
                    help="report which cards the built-in engine plays fully, simplified or partly, then exit")
    ap.add_argument("--report", metavar="HTML",
                    help="with --ladder/--rank: where to write the live ranked-ladder report "
                         "(default results/ladder/DECK.html)")
    ap.add_argument("--no-report", action="store_true", help="with --ladder/--rank: don't write the HTML report")
    ap.add_argument("--no-history", action="store_true",
                    help="with --ladder/--rank: don't save the run to the deck's history (python3 -m mtgsim.history)")
    ap.add_argument("--show-ignored", action="store_true",
                    help="list every card's ignored rules text, even when there is a lot of it")
    ap.add_argument("--offline", action="store_true", help="don't fetch unknown cards from Scryfall")
    ap.add_argument("--log", action="store_true", help="print the play-by-play of the first game")
    ap.add_argument("--engine", choices=["python", "forge"], default="python",
                    help="python: built-in simplified engine (fast); forge: Forge's full rules engine")
    ap.add_argument("--forge-dir", help="Forge install folder (or set FORGE_HOME)")
    ap.add_argument("--java", default="java", help="java executable for --engine forge")
    ap.add_argument("--jobs", type=int, default=1, help="Forge: run games in this many Java processes at once")
    ap.add_argument("--clock", type=int, default=120, help="Forge: seconds before a game is called a draw")
    args = ap.parse_args(argv)
    if args.list_ranks:
        print(list_ranks())
        return
    if not args.decks and not (args.coverage and args.rank):
        ap.error("give at least one decklist")
    if args.coverage:
        db = CardDB(offline=args.offline)
        paths = list(args.decks) + (args.gauntlet or [])
        reports = [load_deck(p) for p in paths]
        try:
            reports += [(f"{t.key}/{p.stem}", load_deck(p)[1]) for t in resolve_ranks(args.rank or []) for p in t.decks()]
        except ValueError as e:
            ap.error(str(e))
        print("\n\n".join(format_coverage(name, deck_coverage(db, counts)) for name, counts in reports))
        return

    paths = list(args.decks) + (args.gauntlet or [])
    tiers = []
    if args.ladder or args.rank:
        if len(args.decks) != 1 or args.gauntlet or args.round_robin:
            ap.error("--ladder and --rank play one deck against the ranks; give exactly one deck")
        try:
            tiers = RANKS if args.ladder and not args.rank else resolve_ranks(args.rank)
        except ValueError as e:
            ap.error(str(e))
    counts, decks = {}, {}
    for path in paths:
        name, counts[name] = load_deck(path)
    tier_opps = {}  # rank key -> opponent names; ranks can share deck names, so names carry the rank
    for t in tiers:
        tier_opps[t.key] = []
        for p in t.decks():
            name = f"{t.key}/{p.stem}"
            counts[name] = load_deck(p)[1]
            tier_opps[t.key].append(name)
    if args.engine == "python":
        db = CardDB(offline=args.offline)
        for name in counts:
            try:
                decks[name] = build_deck(db, counts[name])
            except KeyError as e:
                sys.exit(f"{name}: {e}")

    names = list(counts)
    if args.round_robin:
        pairings = list(itertools.combinations(names, 2))
    elif args.gauntlet or tiers:
        pairings = [(names[0], opp) for opp in names[1:]]
    elif len(names) == 2:
        pairings = [(names[0], names[1])]
    else:
        ap.error("give two decks, or use --gauntlet / --round-robin / --rank / --ladder")

    warnings = [line for n in decks for line in unsupported_report(n, decks[n])]
    if warnings and (len(warnings) <= 25 or args.show_ignored):
        print("Partially simulated cards (their extra text is ignored):")
        print("\n".join(warnings))
        print()
    elif warnings:
        print("Partially simulated cards (distinct cards whose extra text is ignored; --show-ignored lists it):")
        for n in decks:
            distinct = {c.name: c for c in decks[n]}
            part = sum(1 for c in distinct.values() if c.unsupported)
            if part:
                print(f"  {n}: {part} of {len(distinct)}")
        print("  Results for decks with many partial cards say little; --engine forge plays every card,")
        print("  and --coverage shows what each card is missing.")
        print()

    tracker = view = None
    if tiers:
        tracker = LadderTracker(names[0], [(t.key, t.label, tier_opps[t.key]) for t in tiers],
                                pass_rate=args.pass_rate, ladder=args.ladder)
        view = TerminalView()
        tracker.listeners.append(view)
        if not args.no_report:
            report = args.report or f"results/ladder/{names[0]}.html"
            tracker.listeners.append(HtmlReport(report))
            print(f"Live ranked-ladder report: {report}\n")

    def play(a, b):
        if tracker:
            before = tracker.mmr
            tracker.start_match(b, args.games)
        on_game = (lambda r: tracker.update_match(b, r.wins_a, r.draws, r.games)) if tracker else None
        if args.engine == "forge":
            def progress(done, total):
                if view and view.live:
                    return  # the live rank line already shows progress
                print(f"\r  {a} vs {b}: {done}/{total} games", end="", file=sys.stderr, flush=True)
            try:
                res = run_forge_match(a, counts[a], b, counts[b], games=args.games, seed=args.seed,
                                      forge_dir=args.forge_dir, java=args.java, clock=args.clock, jobs=args.jobs,
                                      progress=progress)
            except ForgeError as e:
                sys.exit(f"Forge: {e}")
            print(file=sys.stderr)
        else:
            res, log = run_match(a, decks[a], b, decks[b], games=args.games, seed=args.seed,
                                 log_first=args.log, on_game=on_game)
            if args.log:
                print("\n".join(log), "\n")
        if tracker:
            tracker.update_match(b, res.wins_a, res.draws, res.games)
            view.clear()
            print(res.summary())
            print(f"  MMR {tracker.mmr:.0f} ({tracker.rank.name}, {tracker.mmr - before:+.0f})\n")
        else:
            print(res.summary(), "\n")
        return res

    if tiers:
        run_tiers(names[0], tiers, tier_opps, play, ladder=args.ladder, full=args.full_ladder,
                  pass_rate=args.pass_rate, tracker=tracker)
        if not args.no_history and history.try_record(history.record_ladder, tracker.to_dict(), counts[names[0]],
                                                      engine=args.engine, source="cli"):
            print(f"Saved to run history: python3 -m mtgsim.history show {names[0]}")
        return

    totals = {n: [0.0, 0] for n in names}
    for a, b in pairings:
        res = play(a, b)
        totals[a][0] += res.wins_a + 0.5 * res.draws
        totals[b][0] += res.wins_b + 0.5 * res.draws
        totals[a][1] += res.games
        totals[b][1] += res.games

    if len(pairings) > 1:
        print("Overall win rate")
        for n, (w, g) in sorted(totals.items(), key=lambda kv: -kv[1][0] / max(kv[1][1], 1)):
            if g:
                lo, hi = wilson(w, g)
                print(f"  {n:<24} {w / g:6.1%}  (95% CI {lo:.1%} to {hi:.1%}, {g} games)")


def run_tiers(me, tiers, tier_opps, play, ladder=False, full=False, pass_rate=PASS_RATE, tracker=None):
    """Play `me` against each rank's pool in order. On the ladder, stop at the first rank it fails
    (win rate below pass_rate against the pool as a whole) unless full is set.
    A rating.LadderTracker, if given, is told when each rank's pool ends and gets the verdict."""
    rows, reached, failed = [], None, None
    for t in tiers:
        points = games = 0.0
        for opp in tier_opps[t.key]:
            res = play(me, opp)
            points += res.wins_a + 0.5 * res.draws
            games += res.games
        rate = points / games if games else 0.0
        cleared = rate >= pass_rate
        lo, hi = wilson(points, int(games))
        rows.append(f"  {t.label:<11} {rate:6.1%}  (95% CI {lo:.1%} to {hi:.1%}, {int(games)} games)"
                    + (("  cleared" if cleared else "  failed") if ladder else ""))
        if tracker:
            tracker.end_pool(t.key, cleared if ladder else None)
        if ladder:
            if cleared and failed is None:
                reached = t
            elif not cleared and failed is None:
                failed = t
                if not full:
                    break
    print(f"{me} by rank" + (f" (clearing a rank needs {pass_rate:.0%})" if ladder else ""))
    print("\n".join(rows))
    verdict = ""
    if ladder:
        if failed is None:
            verdict = f"Ladder: {me} cleared every rank, up to and including {reached.label}."
        elif reached is None:
            verdict = f"Ladder: {me} did not clear the first rank ({failed.label})."
        else:
            verdict = f"Ladder: {me} reached {reached.label} and stopped at {failed.label}."
        print(verdict)
    if tracker:
        tracker.finish(verdict)
        print()
        print(text_summary(tracker.to_dict()))


if __name__ == "__main__":
    main()
