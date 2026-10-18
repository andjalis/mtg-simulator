# QA pass — 2026-10-18

Tested the built-in simulator through separate CLI processes, HTTP requests,
and a saved-run/new-app session. Changes are uncommitted on
`feature/simulation-validation`.

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
