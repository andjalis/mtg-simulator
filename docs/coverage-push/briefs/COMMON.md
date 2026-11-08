# Coverage push: shared rules for every developer agent

You are one of four developer agents working in parallel on andjalis/mtg-simulator, a pure-Python Magic: The
Gathering rules engine. The goal is to fully support as many cards as possible from the whole card database
(35,277 cards; 17,612 full on 2026-11-06). A lead agent (pane name `sim-lead`) plans, reviews your PRs, merges them and
re-runs the census. You build. Your worktree is already checked out on your first branch with the card database
(`mtgsim/data/cards.sqlite3`) and a Python 3.13 venv in `.venv`.

## Private project boundary (absolute)
This is the user's PRIVATE project. Only ever touch the GitHub repo `andjalis/mtg-simulator` and the files under
~/mtg-worktrees and ~/mtg-simulator. Never run gh or git against any other repository or organisation, never pass `-R`/`--repo`
with another repo, never change GitHub settings, tokens, scopes or workflows' secrets, and never read or use
anything outside this project (other repos on disk, password managers, other accounts or tools). If a task seems to need any of
that, stop and ask the lead.

## GitHub issues (to-do list for bugs and follow-ups)
Bugs, follow-ups and parked items live as GitHub issues in andjalis/mtg-simulator (only there). Labels:
`counted-full-but-wrong` (a card counts full but plays wrong: fix these BEFORE new coverage), `follow-up`,
`parked`, and `lane:<your lane>` (grammar, static, tokens, abil, trig, mech, simplify, counters, gzones, gplayers, gcond).
- Before each new round: `gh issue list -R andjalis/mtg-simulator --label lane:<yours> --state open`; take
  `counted-full-but-wrong` ones first.
- A PR that fixes one says "Fixes #<n>" in its body (it closes on merge).
- Found a problem outside your lane? File it instead of fixing it: `gh issue create -R andjalis/mtg-simulator
  --title "..." --label "<priority>,lane:<owner>" --body "<what, which cards, evidence, probable cause>"`.
- Coverage work lists stay in the CSV lists, not in issues.

## Read first
`AGENTS.md`, `CONTRIBUTING.md`, and the "Coverage push from 2026-11-06" section at the end of `AGENTS_LANES.md`.
Your worklist is `results/blocking_units_2026-11-06/units.csv` filtered to your lane (column `lane`).
`sole` = cards completed if that unit alone is fixed; `affected_cards` = cards containing it. See
`mtgsim/blocking_units.py` for how units are cut (numbers -> N, mana -> {M}, colours -> COLOR).

## Priority (the user's standing rule)
Rank work by cards fully supported per amount of code. Prefer one general rule that completes many units over
one template per wording: almost every unit is rare (22k distinct units, only 96 reach 10 cards), so general rules
are the only way to big numbers. Deck relevance is only a tiebreaker.

## Correctness rules (non-negotiable)
- Never fake behaviour to win count. A line may only stop being "ignored" if the engine really does what the text
  says when the card is played (resolve it in a test game). If you approximate, record it as a simplification the
  way the existing code does, so the card counts as "simplified", not "full".
- Don't change the parse of cards that are already full unless it's a real fix; `scripts/parse_diff.py` shows it.
- No card-name special cases when a general rule fits. Standard library only. Code must also run on Python 3.10
  (no backslashes inside f-string expressions, no 3.11+ only syntax or modules).
- Stay in your lane's files (see AGENTS_LANES.md). Shared files: only one-line hooks (`cards/parse.py`) and
  appended lines (`cards/__init__.py` join). Do not edit BACKLOG.md (the lead owns it).

## Commands (use the venv; the system python3 is 3.9 and can't import the package)
Eight agents share one 10-core Mac. CPU-heavy checks MUST go through the shared queue `~/mtg-worktrees/bin/heavy`
(max 3 heavy checks machine-wide, low priority, fast_check capped at 4 workers). If it says it is waiting, that is
normal: keep working on code meanwhile if you can.

    # cheap, run freely while developing
    .venv/bin/python -m unittest tests.test_<yours>              # only your own / related test modules
    .venv/bin/python -m mtgsim.blocking_units results/database_coverage_2026-11-06/cards.csv
    .venv/bin/python scripts/lint.py                             # pyflakes, cheap
    # The PILOT GATE NOW RUNS IN GITHUB CI on every push to a PR (job "Pilot gate", ~10 min) and keeps one PR
    # comment starting with <!-- pilot-gate --> with verdict.md (full-card delta, regressions, exercise, smoke).
    # Do NOT run pilot_gate locally any more. Read it with: gh pr view <n> --comments

Do NOT run fast_check or parse_diff locally: GitHub CI runs both on every push (parse-diff posts the list of
changed cards as a PR comment: read it with `gh pr view <n> --comments` and check it before telling the lead).
If CI fails, the lead sends the PR back to you.

Any script of your own that parses the whole card database (comparisons, before/after scans, your own census)
is heavy too: run it as `~/mtg-worktrees/bin/heavy .venv/bin/python <script>`. Never run the full `unittest discover` suite or the full census locally (CI and the lead do that), and don't
rerun the heavy checks after every small edit: GitHub CI runs fast check and parse-diff on every push anyway.

## Each round = one PR
1. One coherent rule or mechanic per PR (big enough to matter, small enough to review: aim for a few hundred lines).
   Aim for at least ~30 newly full cards per PR. If your units are small (5-10 cards each), bundle several related
   ones into one PR (same module, same engine area) rather than one PR each. Prefer a more general rule that covers
   a whole family of units over many small templates. Never pad: honest numbers only.
2. Tests that parse real cards from the DB AND resolve the new effect in a game. For every new effect kind, target
   type or player subject, also a test that the default AI (HeuristicAI) actually casts/activates it in a game and
   aims it at the right side: the audit found several kinds that counted full but the AI never used.
3. lint clean and your own tests pass, then push and open the PR right away; CI runs fast check, parse-diff and the
   pilot gate. When the pilot-gate comment arrives, put its full-card delta in the PR body (gh pr edit <n> --body ...)
   and fix any FAIL on the same branch; put the full-card delta (before -> after) and the units
   targeted in the PR body. End the PR body with: 🤖 Generated with [Claude Code](https://claude.com/claude-code)
Commit messages end with a Co-Authored-By line for your model.
4. `git push -u origin <branch>` and `gh pr create --base main`. Never push to main, never force-push, never merge.
5. Tell your reviewer: grammar-team lanes (sim-grammar, sim-static, sim-gzones, sim-gplayers, sim-gcond) message
   `sim-review2`; all other lanes message `sim-review`:
   `herdr agent prompt <reviewer> "<lane>: PR #<n> open — <one line: rule, full-card delta>"`.
   sim-review reviews first and sends change requests to you; the lead does the final check and merges in batches
   every ~25 minutes, so don't wait for the merge.
6. Start the next round right away. Assume your open PRs will merge; never wait for a merge:
   - If the next round builds on your previous, still-open PR (same module, same helpers), stack it:
     `git checkout -b <prefix>-<k+1>` from your current branch, and open its PR with `--base main` noting
     "Stacked on #<prev>: review only the commits after <sha>" in the body.
   - If it is independent, branch from the latest main instead: `git fetch origin && git checkout -b <prefix>-<k+1> origin/main`.
   - When a PR below you is merged, bring main into your branch with a normal merge and a normal push
     (`git fetch origin && git merge origin/main`, then `git push`). Never rebase pushed branches, never force-push.
   If a reviewer asks for changes on an open PR, fix them on that PR's branch first, then merge that branch into
   the stacked one (`git merge <prefix>-<k>`).
If you are blocked (a design question, a needed change in another lane's files, an engine gap), message the lead
the same way instead of guessing. Keep going round after round until the lead tells you to stop.
