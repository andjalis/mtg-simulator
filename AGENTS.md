# MTG Simulator: agent guide

Shared instructions for any coding agent working in this repo (Claude, Codex, or a delegated
model run through `ask`). Read `README.md` for the user-facing docs; this file covers how to
work in the code.

## What it is

See [README.md](README.md) for what the simulator does and how to run it: AI-vs-AI games between
decklists with win rates and 95% CIs split by play/draw, a rank ladder (Bronze to Grandmaster, MMR),
deck assessment, and an optional Forge engine (`--engine forge`).

## Setup and commands

See the README's quick start for the `python3 -m mtgsim ...` commands; the agent-specific ones:

```
python3 -m mtgsim.build_carddb                 # once per clone; builds mtgsim/data/cards.sqlite3 (~13 s)
python3 scripts/fast_check.py                  # what a PR must pass: lint, sampled card parse, games, fast tests (~2 min on 4 cores)
python3 -m unittest discover -s tests -t .     # full suite (900+ tests, about five minutes; runs nightly in CI)
```

Python 3.10+ only, standard library only. Do not add dependencies. CI and the checks every PR must
pass are described in [CONTRIBUTING.md](CONTRIBUTING.md): `scripts/fast_check.py` on every push and pull
request, the full suite on Python 3.10, 3.13 and 3.14 nightly (`nightly.yml`) and on demand, pyflakes
via `scripts/lint.py`, and `scripts/parse_diff.py` on pull requests (run `python3 scripts/parse_diff.py local --show 5`
before pushing a parser change to see the same list for your working tree). Card-database tests are
skipped when `cards.sqlite3` is missing, so build it before trusting a green run. The Forge tests use
a fake Forge directory and don't need a real install; a real Forge run needs Java 17+, Maven and
`scripts/install_forge.sh` (about 1.5 GB).

See [CONTRIBUTING.md](CONTRIBUTING.md) for how pull requests are opened and merged.

## Layout

The file-by-file layout table is in [README.md](README.md#layout). Additions for agents:

| Path | Role |
| --- | --- |
| `mtgsim/engine/` | Rules engine package (`Game` = the mixins in this package; one handler per effect kind in `kinds/`) |
| `mtgsim/behavior_coverage.py`, `rules/` | Behavior evidence: capability catalog, scenario map, evidence ledgers |
| `mtgsim/data/` | `builtin_cards.json`, `metagame.json`, the wordings JSON, and the generated `cards.sqlite3` (gitignored) |
| `tests/` | `unittest` files, one per area |

## Working rules

- **Verify before reporting.** Run the test suite after engine, AI, card or parser changes.
  Ignore the `ResourceWarning` lines in test output; they are not failures. Check the exit status
  and the `OK` / failure count instead.
- **Card data is generated.** Do not commit `mtgsim/data/cards.sqlite3`. Rebuild it with
  `build_carddb` when needed. Card text the engine doesn't match is ignored on purpose, so
  coverage gaps show up in `--coverage` and in run output; do not hide them.
- **Where new code goes.** A card that fails only on an unrecognised wording of an existing effect needs a data entry,
  not code: see `mtgsim/data/wordings/README.md`. A new mechanic family gets its own template module (like `removal.py`) exporting
  `EFFECT_PATTERNS`/`SUBS`, joined at the end of `cards/__init__.py`, with any engine helper it needs in that
  module. Small general templates go in `cards/patterns.py` (trigger templates and substitutions in `cards/clauses.py`); new effect kinds as an `@kind(...)` handler in the
  matching `engine/kinds/` family module (damage, cards, graveyard, permanents, stats, other); rules
  systems (zones, events, layers, SBA) in `engine/` or the rules-foundation modules. `mtgsim.engine` and
  `mtgsim.cards` re-export every name, so `from mtgsim.engine import Game` keeps working.
- **The engine is incomplete by design.** Support varies by mechanic; check the README's
  implemented subsets and remaining gaps. Don't add a
  card-specific hack when a general template is the right fix. Template recognition is separate
  from behavior evidence (`python3 -m mtgsim.behavior_coverage`, `rules/`).
- **Results are measurements.** Changes to AI heuristics should be checked against `BaselineAI`
  or the rank ladder (`--ladder`, `--gauntlet`), not only against tests. Record notable numbers in
  `AI_RESULTS.md` rather than in code comments.
- **Keep the backlog current.** [BACKLOG.md](BACKLOG.md) is the active capability roadmap.
  Before choosing work, re-parse candidate cards against the current offline database.
  Historical reports and archived backlog snapshots are not open work.
  List only residual ignored clauses on partial cards; never add fully template-matched
  cards or already matched effects as parser todos. Treat supported mechanics as existing
  foundations. After a capability batch, refresh coverage in a new results directory,
  retire resolved clauses/tasks, and update the backlog and its machine-readable records.
  Track recorded simplifications and verified behavior bugs separately from parser gaps.
- **Pure stdlib.**
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

## Local-model pilot gate

Run `python3 scripts/pilot_gate.py --base origin/main [--worktree PATH] [--fast]`
before accepting a pilot change. Requires the offline card database and pyflakes.
The gate writes `verdict.json`, compact `verdict.md`, and full logs under
`results/pilot_gate/<branch>-<UTC time>/`; keep these local rather than committing them.
It checks lint, tests, parser exceptions, full-match regressions, all-card and saved
Standard-snapshot coverage deltas, ten seeded newly-full parse samples, an exercise step
that resolves every effect of each newly-full card once on a stock board (any exception
fails; it checks for crashes, not behavior), and 50 seeded AI smoke games (20 seconds per game). Suspicious sample fields fail for human review;
`target='none'` is listed but does not fail, since untargeted effects use it. `--fast` selects tests by changed/related filenames,
falling back to the full suite for broad or unmapped Python changes. Base coverage is
cached by commit plus code/data fingerprints. A PASS is a review aid, not evidence
of complete rules correctness; read the sampled Oracle/parse pairs.
