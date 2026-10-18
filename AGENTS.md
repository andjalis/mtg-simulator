# MTG Simulator: agent guide

Shared instructions for any coding agent working in this repo (Claude, Codex, or a delegated
model run through `ask`). Read `README.md` for the user-facing docs; this file covers how to
work in the code.

## What it is

A Magic: The Gathering simulator in pure Python. `mtgsim` plays AI-vs-AI games between decklists
and reports win rates with 95% CIs, split by play/draw. It also runs a rank ladder (Bronze to
Grandmaster, MMR), deck assessment, and a web page (`web/`). The built-in engine is the default;
`--engine forge` drives the external Forge rules engine for real tournament decks.

## Setup and commands

```
python3 -m mtgsim.build_carddb                 # once per clone; builds mtgsim/data/cards.sqlite3 (~13 s)
python3 -m unittest discover -s tests -t .     # full suite (900+ tests, about five minutes)
python3 -m mtgsim A.txt B.txt -n 1000          # matchup
python3 -m mtgsim A.txt --gauntlet B.txt C.txt # one deck vs several
python3 -m mtgsim A.txt B.txt -n 1 --log       # play-by-play of one game
python3 -m mtgsim A.txt --coverage             # which cards the engine can't fully play
python3 -m mtgsim.database_coverage --save results/database_coverage  # all cards and ranked gaps
python3 -m mtgsim A.txt --ladder -n 200        # rank ladder, built-in engine
python3 -m mtgsim.assess DECK.txt              # four graded criteria
python3 -m web                                 # http://127.0.0.1:8000
```

Python 3.10+ only, standard library only. Do not add dependencies. CI (`.github/workflows/tests.yml`)
runs the tests on Python 3.10, 3.13 and 3.14; keep code compatible with all three. Card-database tests are
skipped when `cards.sqlite3` is missing, so build it before trusting a green run. The Forge tests use
a fake Forge directory and don't need a real install; a real Forge run needs Java 17+, Maven and
`scripts/install_forge.sh` (about 1.5 GB).

## Layout

| Path | Role |
| --- | --- |
| `mtgsim/engine.py` | Game state, turns, stack and priority, triggers, combat, default response policy |
| `mtgsim/ai.py` | `HeuristicAI` (default) and `BaselineAI` (old player, kept for comparison) |
| `mtgsim/cards.py`, `carddb.py` | Card data; oracle-text templates; lookup order and Scryfall fallback |
| `mtgsim/identity.py`, `rules_events.py`, `continuous.py`, `actions.py` | Rules foundation: physical card identities and zones, shared rules events, scoped continuous effects, transactional actions |
| `mtgsim/removal.py`, `copies.py`, `auras.py`, `search.py`, ... | Template modules: one mechanic family each (patterns plus engine helpers) |
| `mtgsim/behavior_coverage.py`, `rules/` | Behavior evidence: capability catalog, scenario map, evidence ledgers |
| `mtgsim/build_carddb.py` | Builds the card DB from Scryfall bulk data or Forge scripts |
| `mtgsim/decklist.py` | Decklist parsing |
| `mtgsim/runner.py` | Match loop and statistics |
| `mtgsim/ranks.py`, `tiers.py` | Rank ladder over `decks/ranks/`; `tiers.py` is the old name |
| `mtgsim/rating.py`, `ladder_report.py` | MMR, `LadderTracker`, live terminal line and HTML report |
| `mtgsim/assess.py` | Deck assessment (meta, mana, speed, consistency) |
| `mtgsim/coverage.py` | `--coverage` reporting |
| `mtgsim/forge.py`, `crosscheck.py` | Forge mode; engine vs Forge cross-check |
| `mtgsim/data/` | `builtin_cards.json`, `metagame.json`, and the generated `cards.sqlite3` (gitignored) |
| `web/` | `server.py` (HTTP API), `sim.py` (process pool), `static/index.html` |
| `decks/` | Sample lists; `decks/ranks/` has the rank pools (see `decks/ranks/README.md`) |
| `results/` | Saved runs; `results/ladder/` is gitignored (live ladder output) |
| `tests/` | `unittest` files, one per area |
| `AI_RESULTS.md` | Measured AI-vs-baseline results |

## Working rules

- **Verify before reporting.** Run the test suite after engine, AI, card or parser changes.
  Ignore the `ResourceWarning` lines in test output; they are not failures. Check the exit status
  and the `OK` / failure count instead.
- **Card data is generated.** Do not commit `mtgsim/data/cards.sqlite3`. Rebuild it with
  `build_carddb` when needed. Card text the engine doesn't match is ignored on purpose, so
  coverage gaps show up in `--coverage` and in run output; do not hide them.
- **The engine is incomplete by design.** Support varies by mechanic; check the README's
  implemented subsets and remaining gaps. Don't add a
  card-specific hack when a general template is the right fix. Template recognition is separate
  from behavior evidence (`python3 -m mtgsim.behavior_coverage`, `rules/`).
- **Results are measurements.** Changes to AI heuristics should be checked against `BaselineAI`
  or the rank ladder (`--ladder`, `--gauntlet`), not only against tests. Record notable numbers in
  `AI_RESULTS.md` rather than in code comments.
- **Pure stdlib.** The web page and server use only the standard library too.
- **Git.** Commit or push only when asked. Work on a branch, not `main`, unless told otherwise.

## Follow-up suggestions

For this project only, finish completed tasks with 1–5 relevant follow-up tasks,
numbered starting at 1. The user can reply with a number, several numbers, or
"all" to request the corresponding tasks from the latest list. Execute selected
tasks in manageable batches. Do not carry this preference into other projects.

## Delegated work (`ask`)

If you are a delegated model (launched with `ask`), you may not have file or command access.
Work from the text supplied in the prompt, state what you could not verify, and do not claim a
test passed unless you ran it. Local llama.cpp models cannot read files at all.
