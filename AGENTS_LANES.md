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
| Card wordings as data: loader, data files, core templates | `mtgsim/wordings.py`, `mtgsim/data/wordings/` (the loader and format; adding entries to a wordings file is open to every card lane), `mtgsim/cards/patterns.py`, `mtgsim/cards/parse.py`, `tests/test_wordings.py` | Claude |
| Card wording entries (data only, batch by batch) | `mtgsim/data/wordings/*.json` entries, `tests/test_wordings.py` | Claude |
| Backlog and docs | `BACKLOG.md`, `README.md`, `results/residual_batch/` | Claude |
| Cards: shared condition library and linked results ("If <condition>,", "if you do", "this way") | `mtgsim/cx_condlib.py`, `mtgsim/cx_links.py`, `tests/test_cx_condlib.py`, `tests/test_cx_links.py` | Claude |
| Cards: conditional statics and anthems, "for as long as" durations, alternative costs, ability cost parts and effects | `mtgsim/cx_statics.py`, `mtgsim/cx_altcost.py`, `mtgsim/cx_costs.py`, `mtgsim/cx_ability_effects.py`, `mtgsim/engine/kinds/cx_statics.py`, `tests/test_cx_statics.py`, `tests/test_cx_costs.py` | Claude |
| Cards: blocking requirements (lures), colour and type changes, damage prevention and redirection, suspect riders, delayed end-step actions | `mtgsim/cx_lures.py`, `mtgsim/cx_recolor.py`, `mtgsim/cx_shields.py`, `mtgsim/engine/kinds/cx_lures.py`, `mtgsim/engine/kinds/cx_recolor.py`, `mtgsim/engine/kinds/cx_shields.py`, `tests/test_cx_lures.py`, `tests/test_cx_recolor.py`, `tests/test_cx_shields.py`, `mtgsim/cx_mixed.py`, `mtgsim/cx_landtypes.py`, `tests/test_cx_mixed.py`, `mtgsim/cx_suspect.py`, `mtgsim/cx_delayed.py`, `mtgsim/engine/kinds/cx_suspect.py`, `mtgsim/engine/kinds/cx_delayed.py`, `tests/test_cx_delayed.py` | Claude |

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

Claude (nightly cloud session, from 31 Oct): new modules `cx_night_*.py` and tests `test_cx_night_*.py` only.

Claude (until-next-turn thread, from 31 Oct): `mtgsim/cx_next_turn.py`, `mtgsim/engine/kinds/cx_next_turn.py` and
`tests/test_cx_next_turn.py` ("until your next turn" durations, player flags, "player or planeswalker" damage), with
one-line hooks in `cards/parse.py`, `engine/resolve.py` and the engine checks that read the flags.

Claude (trigger-event thread, from 31 Oct): `mtgsim/cx_events.py` and `tests/test_cx_events.py` (the "When(ever)
<subject> <event>" grammar and its engine observer), with one-line hooks in `cards/parse.py` (trigger loop),
`engine/stack.py` (`fire`), `engine/play.py` (land played, cast zone) and `engine/effects.py` (sacrificed).
Round 2 adds `mtgsim/cx_replace.py` and `tests/test_cx_replace.py` (conditional entry counters, "would die, exile it
instead", draw replacements, two-player "choose an opponent"), with one-line hooks in `cards/face_lines.py`,
`cards/parse.py`, `engine/battlefield.py`, `engine/turns.py`, `rules_events.py` and `copies.py` (spell_copied).
Round 3 adds `mtgsim/cx_effects.py`, `mtgsim/engine/kinds/cx_effects.py` and `tests/test_cx_effects.py` (disjunctive
targets, opponent draws, graveyard-to-top, random graveyard returns, exile-this-turn, opponent hand counts), with
one-line hooks in `engine/targets.py`, `engine/costs.py`, `cards/clauses.py` and `cx_night_quantity.py`.
Round 4 adds win/lose the game, rest-of-game hand size and "put ~ on top" to `cx_effects.py`, a `forever`
flag in `cx_next_turn._live`, and Alchemy "A-" self-names in `cards/parse.py`.
Round 5 adds target-land animations ("It's still a land", lasting or until end of turn) to `cx_effects.py`, an
`animate_land` target choice in `engine/policy.py`, and "look at the top card any time" in `cx_replace.py`.
Round 6 adds Awaken to `alt_casts.py` (an alternative cost whose extra effects reuse the round 5 land animation).
Round 7 adds `mtgsim/cx_top.py` (play lands / cast spells from the top of your library; hooks in `engine/costs.py`, `engine/play.py`, `ai.py`), `mtgsim/cx_abilitycopy.py` ("whenever you activate an ability ... copy that ability", hooked in `engine/abilities.py`), copy-ability source filters in `copies.py`, and snow-land animation targets in `cx_effects.py`.

## Coverage push from 2026-11-06 (lead: Claude/Opus integrator)

Census baseline: [results/database_coverage_2026-11-06](results/database_coverage_2026-11-06/README.md), 17,612 of
35,277 full. Work lists come from `python3 -m mtgsim.blocking_units` ([results/blocking_units_2026-11-06](results/blocking_units_2026-11-06/README.md)),
which splits each ignored line into the part the parser rejects and ranks those parts by cards completed. Most parts
are rare (22k distinct, top 1,000 complete about 2,100 cards), so each lane prefers one general rule over many wordings.

| Lane | Owns | Owner |
| --- | --- | --- |
| Effect grammar: compositional subject / verb / object / duration parsing for sentences no template matches | `mtgsim/cx_grammar*.py`, `mtgsim/engine/kinds/cx_grammar.py`, `tests/test_cx_grammar*.py`; one-line fallback hook in `cards/parse.py` `_parse_effects` | Claude Opus (`claude/grammar-*`) |
| Activated-ability effects and cost parts | `mtgsim/cx_abil*.py`, `mtgsim/engine/kinds/cx_abil.py`, `tests/test_cx_abil*.py`; one-line hook in `cards/parse.py` `_parse_ability_cost` | Claude Sonnet (`claude/abil-*`) |
| Trigger heads | `mtgsim/cx_trig*.py`, `mtgsim/engine/kinds/cx_trig.py`, `tests/test_cx_trig*.py`; additions to `cx_events.py` | Claude Sonnet (`claude/trig-*`) |
| Named mechanics (Contraptions, Attractions, Sieges, Rooms, splice, spellbooks, prepared, banding, ...) | `mtgsim/cx_mech*.py`, `mtgsim/engine/kinds/cx_mech.py`, `tests/test_cx_mech*.py` | Claude Sonnet (`claude/mech-*`) |
| Statics, cost modifiers, replacement and prevention, conditional self-statics, entering rules | `mtgsim/cx_static*.py`, `mtgsim/engine/kinds/cx_static.py`, `tests/test_cx_static*.py` | Claude Opus (`claude/static-*`) |
| Simplified cards to full (madness, unearth, day/night, mutate, ...): real rules for recorded simplifications | existing modules where each simplification is recorded, tight diffs | Claude Sonnet (`claude/simplify-*`) |
| Coverage tooling, census, BACKLOG.md, merges | `mtgsim/blocking_units.py`, `results/database_coverage_*`, `results/blocking_units_*`, `BACKLOG.md` | Claude Opus lead |

One PR per coherent rule or mechanic. Each PR body states the units it targets and the census or `parse_diff` delta.
The lead reviews, merges (squash) and re-runs the census; developers do not merge or push to `main`.
