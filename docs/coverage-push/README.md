# Card-coverage push (started 2026-11-06)

Goal: fully support as many cards of the whole database as possible, building on the existing coverage. A card is
"full" when no rules text is ignored and nothing is recorded as simplified. Full must also mean it plays right:
honest numbers only, never fake behaviour.

The open work is in [TODO.md](TODO.md). This page explains how the push works, so anyone (a person or a new lead
session) can pick it up.

## Where we are

| When (UTC) | main | Full | Share | Simplified | Partial | vs baseline |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2026-11-06 morning (baseline) | f1c4ed1 | 17,612 | 49.92% | 393 | 17,272 | |
| 2026-11-06 20:25 | d4e28c5 | 18,128 | 51.39% | 371 | 16,778 | +516 |

About 55 PRs were open at 22:10 UTC, many approved and waiting for the gate or their base PR
(see [TODO.md](TODO.md#open-prs)). PR claims summed to well over +1,500 more full cards.

## Why general rules

`python3 -m mtgsim.blocking_units <census cards.csv>` splits every ignored line into the part the parser rejects
(activated cost or effect, trigger head, plain sentence, named mechanic) and ranks the parts by cards completed.
On the baseline there were 22,405 distinct blocking parts; only 96 reached 10 cards, and fixing the top 1,000 would
complete about 2,100 cards. Even with types, keywords, players and durations masked, 15,776 sentence shapes remain.
The building blocks (destroy, P/T change, sacrifice, damage ...) are shared; the *combinations* are unique. The
old parser matches whole sentences, one template per wording, so each template unlocks a handful of cards.

The fix is a compositional grammar (`mtgsim/cx_grammar*.py`, documented in `mtgsim/GRAMMAR.md` once #207 merges):
subject + verb chain + duration + riders, with verb families as plug-in modules. Its first round (#189) completed
280 cards in about 255 lines; cost modifiers as one grammar (#186) completed 103.

## Team and lanes

One lead (Claude Opus) plans, reviews last, merges and measures; it never implements card families. Developers are
Claude agents (Opus for grammar-heavy lanes, Sonnet otherwise), each in its own git worktree under
`~/mtg-worktrees/<lane>` and its own herdr pane. No Codex. Briefs are in [briefs/](briefs/): every agent reads
`COMMON.md` and its own brief; grammar-extension agents also read `gram-common.md`.

| Agent | Lane (brief) | Model |
| --- | --- | --- |
| sim-grammar | compositional effect grammar, verb registry, animation, tap/untap, control, prohibitions ([grammar](briefs/grammar.md)) | Opus |
| sim-gzones | grammar verbs: destroy/exile/return/sacrifice/tuck/blink ([gzones](briefs/gzones.md)) | Opus |
| sim-gplayers | grammar verbs: damage/life/draw/discard/mill ([gplayers](briefs/gplayers.md)) | Opus |
| sim-gcond | grammar riders: quantities, if, unless, instead ([gcond](briefs/gcond.md)) | Opus |
| sim-static | cost modifiers, replacement/prevention, conditional statics, entering rules, priced prohibitions ([static](briefs/static.md)) | Opus |
| sim-tokens | token descriptions and create/populate ([tokens](briefs/tokens.md)) | Opus |
| sim-counters | counters of any kind ([counters](briefs/counters.md)) | Sonnet |
| sim-abil | activated-ability costs and effects ([abil](briefs/abil.md)) | Sonnet |
| sim-trig | trigger heads and events ([trig](briefs/trig.md)) | Sonnet |
| sim-mech | named mechanics ([mech](briefs/mech.md)) | Sonnet |
| sim-simplify | simplified cards to full, wrong existing behaviour ([simplify](briefs/simplify.md)) | Sonnet |
| sim-review | first review for the non-grammar lanes ([review](briefs/review.md)) | Opus |
| sim-review2 | first review for the grammar team ([review2](briefs/review2.md)) | Opus |
| sim-audit | behaviour audit: plays ~20 newly full cards per batch against Oracle text ([audit](briefs/audit.md)) | Opus |

The grammar agents' surveys and plans are in [plans/](plans/). Lane ownership of files is in `AGENTS_LANES.md`.

## Flow of one change

1. A developer works round after round, one coherent rule per PR (aim for 30+ newly full cards; bundle small
   units). Rounds that build on an open PR are stacked on its branch; agents never wait for merges, gates or reviews.
2. Required tests: real DB cards parsed AND resolved in a game, and for every new effect kind / target type /
   player subject a test that `HeuristicAI` actually casts it and aims it at the right side.
3. Locally only lint and the agent's own tests. GitHub CI runs fast check and parse-diff. The pilot gate runs on
   the lead's Mac (see Tools) and posts a PR comment `<!-- pilot-gate --> Local gate ... for head <sha>`.
4. The reviewer checks rules correctness, faking (conditions dropped, forms skipped), parse-diff, the gate comment
   for the current head, the AI test and hygiene (no `.venv`, `results/pilot_gate/` or generated files committed).
5. The lead does a final check and adds the `lead-approved` label. `merge_batch.sh` squash-merges labelled PRs with
   green checks every 20-25 minutes, oldest first, then runs a census.
6. After each batch the auditor samples newly full cards and plays them. Findings become GitHub issues.

## To-do system

Bugs, follow-ups and parked items are GitHub issues with labels `counted-full-but-wrong` (always first), `follow-up`,
`parked` and `lane:<name>`. Reviewers and the auditor file them; a fixing PR says "Fixes #n". Coverage work lists
stay in CSVs (`python3 -m mtgsim.blocking_units`), not issues.

## Tools (copies in [tools/](tools/); live copies in `~/mtg-worktrees/bin/`)

- `heavy` / `heavy_lock.py`: machine-wide queue for CPU-heavy checks (4 slots, nice 10, fast_check capped at 4
  workers). Each agent venv has a `sitecustomize.py` that auto-queues `fast_check.py`, `pilot_gate.py`,
  `parse_diff.py` and `mtgsim.database_coverage`, even when run without the wrapper.
- `local_gate.py gate1|gate2`: local pilot-gate workers (worktrees `~/mtg-worktrees/gate1/2`, log
  `~/mtg-worktrees/gate.log`); they gate GitHub's merge ref of each open PR and skip PRs that track `.venv`. Restart
  after a reboot: `cd ~/mtg-worktrees && nohup python3 bin/local_gate.py gate1 > gate1.out 2>&1 &` (and gate2).
- `merge_batch.sh [wait-seconds]`: merges `lead-approved` PRs with green checks, then runs `census.sh`.
- `census.sh`: census of main through the queue into `~/mtg-worktrees/census/<UTC>`, refreshes the work list.
- The pilot-gate cache is shared: every worktree's `results/pilot_gate/cache` links to `~/mtg-worktrees/.pilot_cache`.
  `results/pilot_gate/` and `.venv` are in `.git/info/exclude`.

## Lessons (rules that came from real bugs)

- Review and audit find real "counted full but wrong" cards: {Q} usable while summoning-sick, no-mana-cost cards
  castable for {0}, "target player draws" played as "you draw", AI never casting group/player spells, Spacecraft never
  becoming creatures, colour anthems read as subtypes, removal wordings swallowing "nonblack"/"attacking", exile played
  as destroy, tucks firing dies triggers, mana abilities producing nothing. Keep both.
- Run the pilot gate on the PR merged into current main, or cards merged since the branch point look like regressions.
- Never commit `.venv`: checking out such a branch deletes everyone's ignored `.venv` folder.
- Never `git clean -x` in a worktree. Never force-push; stacked branches take `git merge origin/main`.
- Fast check and parse-diff on every push saturate GitHub's 20 free runners: push only when a PR is ready.
  Pending (needs a workflow edit by the owner): Tests on push only for `main`, plus a concurrency group.
- Private project: only `andjalis/mtg-simulator`; never another repo or organisation (see `briefs/COMMON.md`).
