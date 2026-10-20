---
name: mtg-dev
description: Development loop for the MTG simulator repo (mtgsim). Use for any development task in this repo - adding engine mechanics or card templates, AI changes, web/UI work, bug fixes, benchmarks, QA - and whenever a session is started with `ask` here, or the user says "continue", "what's next" or "pick up where we left off". Reads the progress log to see where the project stands, does the work, records it, and ends by suggesting next steps as ready-to-run `ask` commands.
---

# MTG simulator development loop

The project's memory is `results/implementation-progress.md` (the progress log). Every session
starts by reading it and ends by updating it, so the next agent (Claude or Codex, usually launched
through `ask`) can continue without re-discovering the state. `AGENTS.md` holds the working rules
(commands, layout, stdlib only, verify before reporting, branch not `main`); follow it throughout.

## 1. Orient (before touching code)

1. Read the top of the progress log: **Status**, **Next up**, and the latest **Log** entries.
   Skip **History** unless the task touches that area.
2. Check what happened since the log was last synced:
   ```
   git status --short && git branch --show-current
   git log --oneline <Synced commit from Status>..HEAD
   ```
   If there are unrecorded commits, read their messages (and diffs where unclear) and add a short
   catch-up entry to the log first. The log must never be silently behind `git log`.
3. Check the card DB exists (`ls mtgsim/data/cards.sqlite3`); build it if not, otherwise
   card-DB tests are skipped and a green run means little.
4. Restate the task in one or two lines. If the ask is open-ended ("continue", "next", "improve
   something"), take the top item from **Next up** and say so. If it conflicts with the log
   (already done, known blocker), say that before starting.

## 2. Work

- Branch off `main` before editing unless already on a feature branch or told otherwise
  (`feature/<topic>` or `fix/<topic>`). Commit or push only when the user asks.
- Prefer general oracle-text templates over card-specific hacks; leave unsupported text visible
  in `--coverage`.
- For coverage work, choose the next mechanic from `python3 -m scripts.coverage_gaps` (or
  `--standard`), using its normalized blockers, keyword groups and greedy unlock plan; re-run it
  after the change to measure what moved.
- Large or separable work: delegate bounded pieces with `ask -p -t <tier> "..."` (include the
  file paths, acceptance criteria and test command in the prompt) and review the result yourself.

## 3. Verify

Run what the change calls for and keep the exact commands and outcomes for the log:

| Change | Minimum check |
| --- | --- |
| Engine, cards, parser | `python3 -W ignore::ResourceWarning -m unittest discover -s tests -t .` (full suite; note the count) |
| New mechanic / template | Tests above + a focused test file + `--coverage` on an affected deck |
| Anything touching cards, templates or the engine | `python3 -m scripts.coverage_summary` (~2 min, offline): the coverage line for the report |
| AI heuristics | Tests + measured win rate vs `BaselineAI` or `--gauntlet`/`--ladder`, with CI; record in `AI_RESULTS.md` |
| Web / browser engine | Tests + `python3 -m web` smoke; `scripts/ui_qa.cjs` / `browser_bench.cjs` when UI flow changed |
| Forge | Fake-Forge tests; real Forge runs only when asked (slow, ~1.5 GB install) |

Report failures as failures. Never write "passed" for something not run; say "not run" instead.

## 4. Record (update the progress log)

Edit `results/implementation-progress.md`:

- **Status**: current branch, `Synced commit` (HEAD after your work, or the base plus "uncommitted"),
  test count and result, the **Coverage** line (below), and a few lines on what works / what's in flight.
- **Log**: prepend a dated entry (`### YYYY-MM-DD - <title> (<agent/model>)`) with what changed
  and why, files touched, checks run with results, measured numbers, and anything left open.
  Keep it terse - a handful of bullets.
- **Known gaps**: add new ones, remove fixed ones.
- **Next up**: rewrite it with the suggestions from step 5.
- Keep the file readable: when the Log has more than ~10 entries, fold the oldest into
  **History** as one or two lines each.

In an `ask` team, only the lead edits the progress log (`ask --team ID --as NAME claim
results/implementation-progress.md`); the partner posts findings to the board instead.

## 5. Finish: suggest what's next

End every session with a short summary (what changed, checks and results, branch, anything
uncommitted), the coverage line, and **3-5 ranked next steps**.

The coverage line is always there, as before -> after (before = the **Coverage** line in Status
when you started; re-run `python3 -m scripts.coverage_summary` if your work changed cards or the
engine, otherwise say "unchanged"):

```
Coverage: Standard 1,834/4,902 -> 1,840/4,902 fully supported; all cards 7,602/34,084 -> 7,610/34,084
```

If the summary lists cards that crash the parser, report them too; they are bugs. Base them on the log's known gaps,
`--coverage` misses, `AI_RESULTS.md` weak spots, failing or flaky checks, and what you noticed
while working. For each one give:

- one line on what and why (the impact on simulation fidelity, AI strength, or usability),
- a size: small / medium / large,
- a ready-to-paste command, run from the repo root:
  ```
  ask "mtg-dev: <self-contained task, with acceptance criteria>"
  ```
  Add `-t <tier>` only when you are confident of the difficulty (`codex-fast`/`haiku` for
  mechanical edits, `sonnet`/`codex` for normal features, `opus`/`codex-strong` for engine
  rules or AI design). Add `--pair` for large or risky work that benefits from a reviewer.
  Otherwise leave the tier out so Jev scores it.

Write the same list into **Next up**. Where the list goes depends on how the session started:

- **Launched through `ask`** (the task ends with an `ask --report-back` instruction): the user reads
  results in the orchestrator, not in this pane. Put the summary and the ranked suggestions only in
  the report, and keep your reply in this pane to a line or two:
  ```
  ask --report-back <id> - <<'EOF'
  <summary>

  Next up:
  1. ...
  EOF
  ```
  Then stop; don't ask which to do here.
- **Interactive session**: give the summary and suggestions in your reply, then ask the user which
  to do.

Either way, do not start any of them without a go-ahead.

## Handoff when stopping early

If the session ends unfinished (quota, blocker, user stops it): update the log as in step 4 with
the remaining steps marked clearly in **Status**, then record the handoff for `ask`:

```
ask --progress --completed "..." --files "..." --checks "..." --remaining "..."
```

After the user has reviewed a finished result, suggest `ask --feedback accepted|correction|failed
--note "..." --check-result passed|failed|unknown` so routing learns from it.
