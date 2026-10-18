# QA pass — 2026-10-18

Tested the built-in simulator through separate CLI processes, HTTP requests,
and a saved-run/new-app session. The initial fixes were committed on
`feature/simulation-validation` and merged into the updated local `main`.
The first verification below describes that initial pass; the parallel follow-up
tested the newer main branch and additional fixes.

## Bugs reproduced and fixed

- **Malformed API requests:** JSON arrays/scalars, null deck/name values and
  non-string rank entries could terminate the HTTP connection with an exception.
  Fractional game counts were silently truncated, and string boolean values
  such as `"false"` enabled options. Requests now receive HTTP 400 with a useful
  error before starting a run. Integer strings remain accepted.
- **History destination ignored:** `App(history_path=...)` read its leaderboard
  from that store but wrote completed runs to the default store. Both ladder
  and assessment writes now use the configured path. A regression test completes
  a run using the process pool, creates another app with the same store, and
  verifies the saved deck appears on its leaderboard.
- **Comments changed deck composition:** after 60 main-deck cards, a `#` or `//`
  comment was treated as a blank sideboard separator. Later main-deck cards
  silently became sideboard cards. Comment lines are now skipped before checking
  for a blank separator; actual blank lines retain the MTGO behavior.

Added regression coverage for these cases. Web tests now use temporary history
stores so future test runs do not populate the user's leaderboard.

## Verification

- Full suite: **153 tests passed**, card database present, Python 3.14.
  Command: `python3 -W ignore::ResourceWarning -m unittest discover -s tests -t .`.
  Local HTTP tests required execution outside the socket-restricted sandbox.
  Log: `/tmp/mtgsim-qa-unsandboxed.log`.
- Focused parser/web regression run: **13 tests passed**.
  Log: `/tmp/mtgsim-qa-regression-after.log`.
- Separate CLI sessions: mono-red vs green stompy, 10 games each with seeds 7
  and 29; UB snow control vs mono-red, 4 best-of-three matches with seed 13;
  combo deck coverage report. All exited successfully.
- Built-in benchmark: four archetype pairings, four games each, seed 23.
  A second process repeated the command and reused all four checkpoints.
  Both commands exited successfully.
- `git diff --check` passed.

CLI commands, logs and benchmark report are in
`/tmp/mtgsim-qa-sessions-fvmuntu4/`. These temporary artifacts may be removed
by system cleanup.

This pass does not establish comprehensive Magic rules correctness or accurate
human matchup predictions. No real Forge games or interactive browser rendering
were tested; Forge wrapper tests are included in the full suite. Python 3.10/3.13
were not available as part of this run's checks.

## Parallel follow-up after merging current main

Nine agents reviewed separate areas in batches (three workers at a time),
covering engine state, CLI/history, browser sessions, statistics, parsing,
Forge, checkpoint provenance, reports, and assessment.

Additional reproduced defects fixed:

- Creature planeswalkers failed to lose loyalty when damaged and survived
  at zero loyalty. Damage now applies to both relevant types; zero loyalty
  kills them even with indestructible.
- Concurrent history writers allocated duplicate deck version numbers.
  Version lookup/allocation now runs in an immediate SQLite transaction.
- Deck files with equal filename stems silently overwrote one another in CLI
  matchups and gauntlets. Display labels now disambiguate the lists.
- Malformed device results removed the pending future before validating it,
  permanently hanging runs; impossible statistics were also accepted.
  Validation now preserves pending work for retries/server fallback, and bad
  device API inputs return HTTP 400.
- A subsequent browser trial retained the first trial's card data. Each trial
  now refreshes workers before assigning games.
- Arena Companion-before-Deck exports lost their main deck; empty table cells
  lost sideboard notes or imported colors as cards. Section resets and table
  column positions are now preserved.
- Nonfinite saved ratings crashed rather than using the documented fallback.
- Forge's compressed card-script archive was unreachable behind a directory
  check, disabling validation for archive-only installs.
- Malformed checkpoint/result/artifact structures crashed resume. Invalid
  entries now replay; invalid checkpoint containers produce a clear error.
  Artifact references must resolve inside their output directory.
- Malformed saved report containers/criteria and missing podium ranks crashed
  leaderboard rendering. Invalid files are skipped, missing ranks get a fallback,
  and saved assessment scores/MMR are HTML escaped.
- Unanimous tiny samples reported zero assessment uncertainty. Weighted bounds
  now use approximate Bonferroni-adjusted Wilson intervals with an explicit
  method label. Tiny-deck mana calculations now use the available card count;
  invalid consistency sample counts receive a useful error.

Follow-up checks:

- First merged full suite: **484 tests passed** in 170 seconds, before the
  additional regressions were all present (`/tmp/mtgsim-merged-qa.log`).
- Engine stress harness: **120 seeded games**, six pairings and alternating
  starting seats, with **30,796 state checks passed**. The checks covered
  battlefield identity/controller, surviving toughness/loyalty, lethal damage,
  deathtouch, and loss flags (`/tmp/mtgsim-engine-fuzz.py`).
- Focused integrated regressions: **31 passed**
  (`/tmp/mtgsim-parallel-focused.log`); device/browser/HTTP suite:
  **16 passed** (`/tmp/mtgsim-parallel-web-qa.log`).
- Individual reviews also ran existing Forge, assessment, rating, sideboard,
  benchmark, and report tests; the final full suite supersedes these counts.
- Final expanded full suite: **520 tests passed** in 165 seconds
  (`/tmp/mtgsim-parallel-final-suite.log`). `git diff --check` passed.
- Browser JavaScript regression runs the actual extracted session function
  under Node. It checks worker card refresh between trials; it is not a full
  interactive browser rendering test.

No real Forge games or Python 3.10/3.13 runtime checks were added in this follow-up.
