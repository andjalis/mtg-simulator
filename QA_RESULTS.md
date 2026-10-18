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

## Six-agent interface review

Six additional agents used Playwright and Chromium to review desktop forms,
mobile layouts, the trial lifecycle, network recovery, keyboard accessibility,
and leaderboard/saved results. Tested widths were 320, 390, 768, and 1440px.

Fixed confirmed UX bugs:

- Mobile users had no leaderboard link, and completed results also hid it.
  Navigation now stays available; the saved-results header wraps at narrow widths.
- Small mobile controls now have at least 44px-high touch targets.
- Overlapping league names at 320px now wrap into three columns.
- Zero-count lists enabled starting an empty trial; huge quantities enabled
  potentially enormous card expansion. Zero quantities are ignored, and web
  validation/run creation enforces 1–1000 cards before expansion.
- Correcting rank selections left an old error visible. Loadout edits now clear
  stale form errors.
- A failed rank-list request silently left the page unconfigured. The page now
  explains the failure, offers retry, and blocks starting until ranks load.
- Refreshing an active or completed trial lost its run ID. The browser tab now
  retains it in session storage and restores the same run. Interrupted polling
  exposes a reconnect action; an expired run clears the saved ID and explains
  how to start again. This does not preserve in-memory runs across server restarts.
- Failed trials incorrectly used the completed-trial navigation hint. The hint
  now distinguishes incomplete trials.
- Saved replay independently rounded wins and draws, sometimes showing 150%
  score and negative losses. Replay prefixes now use a consistent sequence of
  outcomes. Regression checks cover every valid W/D/L combination for 1–12 games
  at two replay subdivisions.
- Repeated leaderboard action links lacked deck-specific accessible names;
  those links now identify each deck. The actions column and internal-rating
  wording are explicit.

`scripts/ui_qa.cjs` is the repeatable integrated Playwright regression pass.
It passed against an isolated real server, including a 10-game trial, saved-results
refresh without resubmission, invalid forms, retry, mobile layout/navigation and
touch targets. Mocked transport tests separately passed active-trial refresh,
polling interruption, and reconnect. No unhandled browser errors occurred.
Expired-session recovery and blocked browser-engine download/server fallback
also passed. Final full Python suite: **523 tests passed** in 166 seconds
(`/tmp/mtgsim-ux-final-suite.log`); `git diff --check` passed.
Log: `/tmp/mtgsim-ux/final-playwright.log`; screenshots:
`/tmp/mtgsim-ui-artifacts/`. Agent-specific scripts/screenshots are under
`/tmp/mtgsim-ux/`.

Keyboard start, result-heading focus, Space/Enter table expansion, configuration
focus, and explicit reduced-motion checks passed. An initial reduced-motion
finding was withdrawn after isolated reproduction showed the existing rule works.
Tests used Chromium on Linux, including emulated mobile viewports, not physical
phones or other browser engines.

## Live trial stalled at 270 games

Inspected trial `6b7e42957ea9`: status running, 270/3770 games, Bronze pool,
device execution, no server game workers. All five Bronze matchups had reached
their full or early-stop limits (20, 100, 20, 30, 100 games).

Root cause: `DevicePool` creates plain futures. Cancelling them at an early-stop
decision leaves them in the cancelled state without the executor acknowledgment
that `as_completed` requires. The completion loop then waits indefinitely.
A cancellation callback now sends that acknowledgment. A focused regression
failed before the fix and passes afterward; an integration test drives browser
chunks through early stops and verifies that the entire run finishes.

The saved snapshot also explained the rating/map confusion: Silver at 1067 MMR
is the estimated rating; Bronze is the opponent pool under test. A further user
trial reaching Gold confirmed that two simultaneous named ranks remained confusing.
Live play now shows only a numeric MMR estimate with a neutral symbol, withholds the
named MMR rank and rank-threshold progress until completion, keeps the arrow above
the active opponent pool, and leaves the final
arrow at the last tested pool rather than moving it to an MMR rank. Matchup totals
include early-stop limits so completed 20-game matchups read 20/20 rather than 20/100.

The original trial snapshot was preserved at
`~/.local/state/mtgsim/diagnostics/6b7e42957ea9.json` before restarting the server.
An isolated Playwright check using that snapshot verified Silver/1067 alongside
the Bronze arrow, shortened matchup totals, and consistent finished-pool placement
(`/tmp/mtgsim-stall-map.log`). Focused checks: 14 rating/replay/cancellation tests,
10 cancellation/device/early-stop tests, and 9 HTTP/cancellation tests passed.
Full suite: **525 tests passed** in 179 seconds
(`/tmp/mtgsim-stall-final-suite.log`). The subsequently added live-rating regression
passed separately with rating/replay/cancellation checks (14 tests), and Playwright
verified numeric live MMR followed by the named badge only upon completion.

## Opponent-pool close-up prototype

Replaced the live MMR panel with the active opponent pool's badge, pool score,
clear target, completed-matchup count, game count, interactive opponent cards,
and the selected matchup's W/L/D record. Map nodes are keyboard-accessible
buttons; selecting another pool pins the close-up until Follow live pool is used.
The map arrow continues to identify the actual live pool. Batch updates preserve
opponent selection and keyboard focus; overall counters are labeled Trial.
MMR remains on the final results screen.

Validation: **14 focused interface/replay/HTTP regressions passed**
(`/tmp/mtgsim-pool-focus-tests.log`). Playwright's deterministic transport fixtures
passed pool selection, return to live, opponent inspection with Space, focus
preservation across batches, automatic pool advance, completed-result navigation,
and overflow/touch checks at 320/390/768px, plus 1440px desktop inspection
(`/tmp/mtgsim-pool-focus-playwright.log`). Screenshots:
`/tmp/mtgsim-ui-artifacts/pool-closeup-*.png`.

## Reload during browser-run grading

The user's visible trial was in Deck analysis at 1160/1230 games while the
close-up incorrectly showed the next unplayed Gold pool. Reproduced a second
stall mechanism: after old workers claim tasks and a page reload destroys them,
the new page's heartbeats keep those tasks pending forever. Explicit pool release
completes the same futures on the server. Reconnection now performs that handoff
for running device trials, preserving completed results without restarting the
server. Browser titles include the trial ID for diagnosis.

Grading now displays a dedicated analysis panel with the remaining matchup-game
count or hand/speed-analysis stage. The pool map rests at the last tested pool;
past pools can still be inspected, with a Back to analysis action.

Added a claimed-work/reconnect regression and Playwright coverage for the handoff,
grading stages and review navigation (`/tmp/mtgsim-reconnect-analysis-playwright.log`).
Also added read-only `/api/runs` summaries for diagnosis after the next normal
server restart; the running user's server was not restarted just to add that API.
