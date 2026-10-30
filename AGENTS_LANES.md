# Agent lanes

Several agents (Claude threads, Codex) work in this repo at once. Each lane below has an owner and
the files it may edit. Stay in your lane; this file replaces a pile of issues. Owner is `free`,
`Claude`, or `Codex`.

## Claiming a lane

- Claim a free lane by changing its owner in your first PR (or a tiny PR of its own), and release it
  the same way when you are done. A lane with an owner is off limits to everyone else.
- If your work needs a file in another lane, make only a tiny fix there, or ask the owner.
- Shared files are append-only: the join at the end of `mtgsim/cards/__init__.py` (add your module on
  its own lines) and this file. Never rewrite them.

## Lanes (andjalis/mtg-simulator)

| Lane | Owns | Owner |
| --- | --- | --- |
| Cards: graveyard, flashback/escape/unearth, recursion, mill | `mtgsim/graveyard.py`, `returns.py`, `milling.py`, `cx_graveyard*.py` | Codex |
| Cards: exile effects, blink, foretell, suspend, adventure | `mtgsim/alt_casts.py`, `cx_exile*.py` | Codex |
| Cards: tutor/search, scry, surveil, shuffle | `mtgsim/search.py`, `cx_search*.py` | Codex |
| Cards: copy effects, populate, clones | `mtgsim/copies.py`, `cx_copy*.py` | Codex |
| Cards: cost reduction, alt/additional costs, X spells | `mtgsim/discounts.py`, `xspells.py`, `emerge.py`, `costs.py`, `cx_cost*.py` | Codex |
| Cards: planeswalker loyalty | `cx_walker*.py` | Codex |
| Cards: triggers, counters, proliferate, tokens | `mtgsim/combat_triggers.py`, `cast_triggers.py`, `counter_mechanics.py`, `proliferate.py` | Claude |
| Cards: auras, equipment, vehicles, combat keywords, "can't" effects, anthems, sacrifice, activated costs | `mtgsim/auras.py`, `creature_keywords.py`, `protection.py`, `permanent_templates.py`, `removal.py` | Claude |
| Engine core (rules foundation) | `mtgsim/engine/`, `identity.py`, `rules_events.py`, `continuous.py`, `actions.py` | free |
| AI | `mtgsim/ai.py`, `learning.py`, `AI_RESULTS.md` | free |
| Ranks, rating, assessment | `mtgsim/ranks.py`, `rating.py`, `assess.py`, `ladder_report.py`, `decks/ranks/` | free |
| Card DB, coverage and Forge tooling | `mtgsim/build_carddb.py`, `carddb.py`, `database_coverage.py`, `coverage.py`, `forge*.py`, `crosscheck.py`, `scripts/` | free |
| Browser bundle | `mtgsim/browser.py` | free |
| Card wordings as data: loader, data files, core templates | `mtgsim/cards/wordings.py`, `mtgsim/data/wordings/` (the loader and format; adding entries to a wordings file is open to every card lane), `mtgsim/cards/patterns.py`, `mtgsim/cards/parse.py`, `tests/test_wordings.py` | Claude |
| Card wording entries (data only, batch by batch) | `mtgsim/data/wordings/*.json` entries, `tests/test_wordings.py` | Claude |
| Backlog and docs | `BACKLOG.md`, `README.md`, `results/residual_batch/` | Claude |

Other lanes in andjalis/mtg-gauntlet (private, includes this repo as the `engine/` submodule):

| Lane | Owns | Owner |
| --- | --- | --- |
| Web app: page, gauntlet, leaderboard, theme | `web/` (`static/`, `server.py`, `leaderboard.py`, `theme.py`) | free |
| In-browser runner and QA scripts | `web/sim.py`, `scripts/`, `tests/` | free |
| Engine pin bumps | the `engine/` submodule pointer only | whoever merges an engine change that the web app needs |

## Rules

- New card work goes in new modules `mtgsim/cx_<family>.py` and new tests `tests/test_cx_<family>.py`.
  Codex reports go in `results/codex_round_N/`; Claude updates `BACKLOG.md`.
- Branches: `claude/...` for Claude, `codex/...` for Codex. Never push to the other's branches.
- Small PRs, one lane each. Rebase on main right before opening, and merge as soon as CI is green.
- Before pushing run `python3 scripts/lint.py` and, for parser changes,
  `python3 scripts/parse_diff.py local --show 5`.
- gauntlet CI has no Actions minutes until 1 November 2026: run its tests locally and say so in the PR.

Claude (cards thread, 30 Oct): new modules `cx_triggers.py`, `cx_timing.py`, `cx_damage.py` (named mechanics and wording
rounds). The big families (activated abilities, triggers, counters) belong to the other Claude cards thread.
