# Implementation progress

The project's working memory. Agents read **Status**, **Next up** and the latest **Log** entries
at the start of a session and update them at the end (see `.claude/skills/mtg-dev/SKILL.md`).
Newest log entry first; fold old entries into **History** when the log passes ~10 entries.

## Status

- Branch: `docs/round-18-sync` (docs only, off `docs/standard-coverage-remeasure` at `ca5568e`) ·
  Synced commit: `ca5568e` (round 18, merged: PRs #26 attacking-token grants, restricted Equip
  targets (#27), graveyard return/reanimation targets, AI spell-option dedup (#28), combined
  scenario tests (#29); round 17 merged earlier as #21-#24)
- Tests: full suite 833 OK, 1 skipped (373.7 s, `ca5568e` plus this docs sync, 2026-10-20).
- Coverage (2026-10-20, `python3 -m scripts.coverage_summary`): Standard 1,837/4,902 fully supported
  (37.5%, 60% of rules sentences); all cards 7,615/34,084 (22.3%, 41%); no parser crashes.
  Before round 18's merges the Status line read 1,835 / 7,608.
- Engine: built-in engine plus templates for auras/equipment, X spells, copy effects, library
  search, counting, modal choices and ~40 newer keyword mechanics (rounds 1-17). Standard
  saved-snapshot coverage is 1,835 / 4,902 fully template-matched (37.4%),
  7,704 / 12,933 rules sentences handled (~60%) as of the delayed-token-actions measurement;
  per-round before/after reports are saved under `results/standard_coverage/`.
- AI: `HeuristicAI` default; precombat kill setup and per-game reset were already in
  `363d3ce`. Now verified with end-to-end lifecycle regressions and 33,000 measured
  games: combo setup improves tested matchups, aggro/control difference inconclusive
  (`AI_RESULTS.md`). Earlier lethal-attack tie-break has no measurable win-rate effect.
  Round 17 made no AI change; a 10-game-per-pairing benchmark of `7b6b71e` vs merged round 17
  gave identical winners in all 40 games (diagnostic only, no equivalence claim).
- Web: sequential fullscreen deck trials, league track, saved-run replay, in-browser engine,
  opponent-pool arena; QA passes on validation, recovery and mobile (`QA_RESULTS.md`).
- Round 18 results: attacking-token keyword grants (Old Hob, Alleycat Blues) and exact graveyard
  return/reanimation targets are merged, as are restricted Equip targets and the AI spell-option
  dedup (four AI-vs-Baseline cells unchanged within noise; a correctness fix). The Equip sacrifice
  policy is **not merged**: it regresses `hauberk_bodies` by 10.6 points and is being retuned.
- In flight (round 19, seven threads on `ca5568e`; do not duplicate): graveyard hate targets,
  the legend rule, scaling Equipment bonuses, Equip sacrifice retune, cost-aware AI planning and
  delayed-scheduler invariants (see Next up).

## Next up

Round 19 (in flight, do not launch again; the orchestrator merges them):

1. **gy-hate-targets** - bind targeted graveyard hate ("exile target card from an opponent's
   graveyard") to exact `GraveyardTarget` entries, as the return targets do (`mtgsim/graveyards.py`).
2. **legend-rule** - legend rule state-based action using `CardDef.legendary` (`mtgsim/copies.py`,
   `engine.py`), with an owner choice policy and token-copy identity.
3. **equip-bonuses** - scaling equipped-creature bonuses such as Blackblade Reforged's
   lands-controlled +1/+1, so newly legal Equip activations produce the right stats.
4. **equip-sac-retune** - retune `choose_equip_cost`; merge only if `hauberk_bodies` matches or
   beats the previous policy at 400 games (`scripts/equipment_policy_bench.py`).
5. **ai-planning** - cost-aware combo planner that picks the cheaper of same-name alternatives
   (`mtgsim/ai.py`).
6. **delayed-invariants** - prune delayed entries whose bound object has left the battlefield, and
   add a reusable post-game invariant helper for the bounded seeded games.

Backlog, ranked; each is ready to launch from the repo root:

1. **Equipment self-discount math** (medium) - Plate Armor, Warrior's Blades and Dragonfire
   Blade still use the full-cost approximation.
   `ask "mtg-dev: implement general Equipment self-discounts for Plate Armor, Warrior's Blades and Dragonfire Blade as per-ability cost modifiers; preserve unrelated restrictions and minimum colored costs, test board and target changes, run full suite and distinct offline coverage reports"`
2. **Pay-gated token creation continuations** (medium) - bind next-end-step continuations to
   creation that depends on a payment (Akoum Stonewaker) without hiding conditions or pronouns.
   `ask "mtg-dev: bind next-end-step token continuations safely to supported pay-gated creation such as Akoum Stonewaker; schedule only for tokens actually created after successful payment, preserve unknown conditional/unbound wording, test failed payment, multiple created objects, stolen tokens and both turns, run full suite and distinct coverage"`
3. **Sorcery-only and free flashback grants** (medium) - extend the grant template to Recoup and
   explicit/free grant costs such as Archmage's Newt, reusing exact `GraveyardTarget` entries.
   `ask "mtg-dev: extend flashback-grant templates to sorcery-only grants such as Recoup and explicit/free grant costs such as Archmage's Newt; reuse exact target entries, keep conditional unsupported text visible, test independent printed/granted costs and cleanup, run full suite and offline coverage"`
4. **Non-mana Equip payments** (medium) - typed artifact sacrifice, fixed life and discard
   payments, keeping once-per-turn restrictions visible.
   `ask "mtg-dev: extend EquipCost to general artifact sacrifice and fixed life/discard payments where safely matched; preserve unsupported restrictions, validate all components before spending, test failure and response behavior including self-sacrifice, run full suite and offline coverage reports"`
5. **Delayed token AI valuation** (medium) - the copy heuristic discounts only folded sacrifice
   copies, not delayed exile/destroy.
   `ask --pair "mtg-dev: evaluate token-copy AI valuation for shared delayed sacrifice/exile/destroy continuations; preserve controller timing and indestructible differences, add decision regressions, measure against BaselineAI with confidence intervals before claiming improvement, run full suite and report AI_RESULTS proposals"`
6. **Parser-exception regressions** (small) - guard `scripts.coverage_summary` against crashes
   beyond number conversion.
   `ask "mtg-dev: add focused regression tests for parser exceptions found by scripts.coverage_summary, preserving unsupported text without crashing; run focused tests and full suite"`
7. **Worthy Equip eligibility** (medium) - model Mjolnir's worthy restriction (legendary,
   non-Villain, red or white creature) as an explicit filter, keeping the reminder semantics.
   `ask "mtg-dev: model Mjolnir's worthy Equip target restriction with explicit legendary, non-Villain and red-or-white eligibility; preserve reminder semantics instead of discarding them, test changes during responses and copied creatures, run full suite and distinct offline coverage reports"`

## Known gaps

- Combo fixture remains weak in tested built-in matchups (16–22% vs platinum
  aggro/midrange); list, pilot and engine limits are not separated by these measurements.
- Aura entry directly onto the battlefield outside the matched Role effects has no
  non-target host-selection policy; unattached Auras go to the graveyard.
- Targeted graveyard hate ("exile target card from an opponent's graveyard") and "up to two
  target creature cards with different names" still choose on resolution or stay unmatched.
  AI valuation of graveyard effects looks only at the player's own graveyard. Untargeted
  "return a creature card" effects still choose on resolution by design.
- Planners still approximate one spell option per name, so a combo plan cannot pick the cheaper
  of two same-name alternatives (flashback native vs granted). Options themselves are correct.
- The legend rule is not implemented; `CardDef.legendary` is recorded for targeting and copy
  exceptions only.
- Flashback-grant matching is bounded to the instant-or-sorcery mana-cost template;
  sorcery-only grants (Recoup) and explicit/free grant costs (Archmage's Newt) stay visible.
- Graveyard variants are cached per entry, so the per-game cache grows with graveyard stays
  (no observed issue). Graveyard clear/slice deletion now reports departures to `gy_leave`.
- Manifest dread uses a simplified 2/2 that cannot turn face up. Conditional/pronoun
  prepared variants remain.
- Equipment keeps each supported Equip ability and mixed mana/sacrifice-a-creature costs.
  Restrictions other than legendary, token and the listed creature types (commander, worthy,
  unrecognized conditions), frequency restrictions and non-mana payments other than creature
  sacrifice are unsupported. Plate Armor, Warrior's Blades and Dragonfire Blade self-discounts
  use a full-cost approximation. The merged sacrifice policy does not weigh the lost creature
  against the attachment bonus; the retune is in flight.
- Delayed scheduling covers matched single-target exile/return pairs and unconditional
  sacrifice/exile/destroy continuations directly after supported token/copy creation.
  Conditional/gated continuations (Akoum Stonewaker), unbound pronouns, multi-target
  returns and return-to-hand forms remain visible in coverage. Stale delayed entries for
  objects that already left wait for the next end step. Copy AI valuation discounts only
  legacy folded sacrifice copies; delayed exile/destroy has no valuation.
- Custom AI instances are shallow-copied; mutable per-game containers should be
  rebound in their optional `reset()` hook (documented; built-in state resets correctly).
- Forge observed play/draw sampling balances starters when possible; the worker
  cap can leave skew in lopsided matchups (the earlier cannot-balance note was stale).
- Still unsupported per README: casualty (never paid), day/night, Old-Growth Troll's return.
- No real Forge games or Python 3.10/3.13 runs in the latest QA passes (CI covers 3.10/3.13).

## Log

### 2026-10-20 - Round 18 documentation sync (docs-r18, Claude Haiku 5.5)

- Synced Status, Next up, Known gaps, README and AI_RESULTS with round 18 at `ca5568e`
  (docs only; no code changes). Round-18 threads, from their reports:
  - Attacking-token grants (Old Hob, Alleycat Blues; PR #26): general template `target attacking
    creature token [you control] gains <keyword> until end of turn`. Targets are chosen before
    payment, rechecked without retargeting; SBA drops attackers that change control or stop
    being creatures. Standard 1,835 → 1,836.
  - Graveyard return/reanimation targets (commit `8b356fe`, message says #27 by mistake): targeted
    returns bind an exact `GraveyardTarget` at cast/activation/trigger time (`mtgsim/graveyards.py`),
    multi-target tuples, X planned before targets, reflexive "when you do" returns, saga fix,
    CardDef.legendary. Coverage unchanged.
  - Restricted Equip targets (PR #27): legendary, token and listed creature-type filters per Equip
    ability, chosen before payment and rechecked after responses. Standard 1,835 → 1,836; fixture
    `decks/coverage/equip_targets.txt` 0/19 → 6/19.
  - AI spell-option dedup (PR #28): `engine.unique_spell_options` keeps options with distinct costs,
    origins or granted flashback. Four AI-vs-Baseline cells unchanged within noise (AI_RESULTS).
  - Combined delayed-token / mixed-Equip / flashback-grant scenarios (PR #29): 12 tests, no engine
    bugs found, plus a determinism check on bounded seeded games.
  - Equip sacrifice policy (`equip-sac-policy`): **not merged**. Tests pass, but `hauberk_bodies`
    regresses 10.6 points vs the previous policy (AI_RESULTS). Retuned in round 19.
- Known gaps: removed the fixed graveyard-target, AI-dedup and Old Hob items; added the legend
  rule and the planner-alternatives gap.
- Next up: round-19 threads listed as in flight; backlog renumbered, Mjolnir worthy Equip added.

### 2026-10-20 - Round 17 documentation sync (Claude Sonnet 5.5)

- Synced Status, Next up, Known gaps and the README with merged PRs #21-#24 at `70ab159`
  (previously `63aa2df` plus uncommitted work). Docs only; no engine or test changes.
  README: delayed-effects, Equipment and flashback paragraphs and the remaining-gaps list;
  AGENTS.md test count 528 → 709. Folded the five oldest log entries into History.

### 2026-10-20 - Round 17 integration QA (Codex)

- `integration/round-17` at `05a6abb` (PRs #21-#24 merged), base `7b6b71e`. No failing PR; no
  repo files changed. Python 3.14.8, card DB present.
- Full suite `python3 -W ignore::ResourceWarning -m unittest discover -s tests -t .`: 709 OK,
  1 skipped, 205.099 s. Focused delayed/equip-costs/equip-sacrifice/flashback/templates: 172 OK.
- `python3 -m scripts.coverage_summary`: Standard 1,835/4,902, all cards 7,608/34,084, no parser
  crashes (starting counts 1,834 / 7,602).
- Crash smoke: `python3 -m mtgsim --offline --round-robin decks/green_stompy.txt
  decks/mono_red_aggro.txt decks/orzhov_midrange.txt decks/ub_snow_control.txt -n 200`
  at seeds 101 and 202: all six pairs, 2,400 games, no crash.
- `mtgsim.benchmark --manifest benchmarks/small.json --engine builtin -n 10 --seed 101` on base
  (`git archive 7b6b71e`) vs merged: identical results in all four pairings, 0/40 winners
  changed. Ten-game diagnostics establish nothing about equivalence or strength.
- Evidence under `/tmp/round17-*` (not in the repo). No Forge or Python 3.10/3.13 run.

### 2026-10-20 - Flashback-grant graveyard targets (Codex lead / Claude Opus reviewer, PR #24)

- Matched `grant_flashback` effects declare a `graveyard_spell` target, chosen and stored
  before paying (spells, activated and loyalty abilities) or when the trigger is put on the
  stack. `GraveyardTarget` records controller, exact CardDef and a per-entry token that
  survives or is invalidated by graveyard mutations (bulk removal, slice replacement,
  reordering, shared CardDefs). Resolution rechecks the entry and never retargets; losing
  the only target fizzles the item. Permissions bind to exact entries; leaving the zone or
  cleanup invalidates them. A grant spell cannot target its own casting entry.
- Modal grants bind before payment; Teamwork reserves a viable crew. Native and granted
  flashback are priced independently (grants use the original mana cost). Flashback casts exile
  on resolution, counter or bounce. Fixed: `can_cast_now` rejected `bounce_spell` answers.
- Files: `cards.py`, `engine.py`, `modal.py`, `tests/test_round16.py`, new
  `tests/test_flashback_targets.py` (34 tests, fail against base: 31 failures + 3 errors).
- Full suite 651 OK (skipped=1), 194.366 s; coverage unchanged (Standard 1,834, all 7,602);
  `decks/coverage/round16.txt` 8/8 full; 200-game `green_stompy` smoke without crashes.

### 2026-10-20 - Independent and mixed Equip costs (Codex lead / Claude Opus partner, PR #23)

- `cards.py`: `EquipCost(mana, sacrifice)` and ordered `CardDef.equip_costs`; legacy
  `equip_cost`/`equip_sacrifice` expose the first choice. Independent mana Equip abilities and
  mana plus sacrifice-a-creature costs in either order are matched; unknown mana symbols no
  longer become free equip; self-discount approximations keep the full base cost.
- `engine.py`: picks a payable ability (mana-only first, then lower mana), or an explicit
  `Game.equip(..., ability=N)` / `activate(..., "equip:N")` with no fallback. All costs
  validate before payment; a creature sacrificed for mana cannot pay a second sacrifice;
  target discounts reduce generic mana only; `equip_all` respects reserves.
- `tests/test_equipment_costs.py` (35) plus `decks/coverage/equip_costs.txt` (13 cards).
  Parser comparison over 654 Equipment entries: four period-terminated Equip lines newly
  recognized, Lashwrithe Phyrexian's equip now visibly unsupported.
- Full suite 650 OK (skipped=1), 226.016 s; focused 161 OK; coverage unchanged
  (Standard 1,834, all 7,602). No AI measurements.

### 2026-10-20 - General delayed exile/destroy token actions (Codex lead / Claude Opus reviewer, PR #22)

- Extended the shared one-time end-step scheduler (`delayed.py`, `engine.py`, `copies.py`) to
  unconditional sacrifice/exile/destroy continuations bound to exact created tokens/copies,
  including plural forms, multiple continuations and controller-specific next end steps.
  Exile/destroy follow stolen tokens; sacrifice requires control. Destroy respects
  indestructible and fires death triggers; exile does neither. Each action runs once, even
  if destruction fails; source departure cannot redirect it.
- `tests/test_delayed_token_actions.py` (22) and `decks/coverage/delayed_token_actions.txt`.
  Stormsplitter now fully matches; Old Hob's destroy line matches but its attacking-token
  ability stays visible; Akoum Stonewaker and Echo Chamber remain partial.
- Full suite 636 OK (skipped=1), 223.558 s (partner 219.058 s); focused 138 OK.
- Coverage (identical input hashes): Standard 1,834 → 1,835; all cards 7,602 → 7,608;
  handled sentences 7,702 → 7,704 / 12,933; fixture 0/4 → 1/4 full.

### 2026-10-20 - Number-word parser fix (Codex, PR #21)

- `cards._num` now parses number words zero through twenty, keeping `a`/`an` aliases and
  numeric strings; fixes the Dovin, Grand Arbiter `int('ten')` crash. Regression in
  `tests/test_templates.py`.
- Full suite 618 OK (skipped=1), 195.620 s; `scripts.coverage_summary` reports no crashes;
  coverage unchanged at that point (Standard 1,834, all 7,602).

### 2026-10-20 - Equipment sacrifice costs and attachment fidelity (Codex)

- Took the top Next up item; no newer commits since `63aa2df`. Preserved all prior
  uncommitted work on `docs/standard-coverage-remeasure`; no commit or push.
- `mtgsim/cards.py`: general `Equip—Sacrifice a creature` cost and `Equipped creature
  has +N/+N` bonus wording. Dissection Tools and Demonmail Hauberk fully match;
  checked local DB definitions against fixtures. Restricted/mixed sacrifice costs
  and conditional/unknown bonuses remain visible. Multiple equip costs still use
  the last recognized cost; tracked as a follow-up rather than hidden.
- `mtgsim/engine.py`: equip chooses its target before payment, sacrifices through
  the existing sacrifice/death path, then uses the ability stack. Rechecks target
  control/type and exact source/target objects after responses; no retargeting.
  Failed re-equip keeps the original attachment. Cross-controller stats, keywords,
  ward and cleanup now work; illegal host/type changes detach Equipment. Default
  policy sacrifices the least valuable other creature and keeps its only creature.
  No win-rate claim or sacrifice-value optimization; policy limits are in Known gaps.
- `tests/test_equipment_sacrifice.py`: 25 regressions cover payment, indestructible,
  tokens, sacrifice/death triggers above equip, illegal choices/timing, explicit
  target-as-payment, mana equip, source/target zone identity, control/type changes,
  re-equip, previous-host sacrifice, cleanup, manifest bonus and a real priority
  bounce response. Updated README behavior and coverage documentation.
- Verification (all exit 0): full `python3 -W ignore::ResourceWarning -m unittest
  discover -s tests -t .` — 614 OK in 193.122 s; final focused `python3 -W
  ignore::ResourceWarning -m unittest tests.test_equipment_sacrifice
  tests.test_templates.EquipmentTests tests.test_three_followups tests.test_three_auras
  tests.test_auras tests.test_copies tests.test_coverage tests.test_standard_coverage`
  — 126 OK in 8.374 s. Three tests added after full-suite discovery pass in this
  focused run; 617 tests are currently discoverable. `git diff --check` clean.
- Offline before/after `remeasure.main("equipment-sacrifice-before/after")` and
  `python3 -m mtgsim decks/coverage/three_followups.txt --offline --coverage` exit 0.
  Identical input hashes: full 1,833 → 1,834; partial 3,027 → 3,026; simplified 42,
  one-line misses 1,920 unchanged; handled 7,700 → 7,702 / 12,933. Diagnostic fixture
  11/12 → 12/12 full. Six distinct `equipment-sacrifice-*` artifacts preserve all
  previous reports. No Forge games or Python 3.10/3.13 runs.

### 2026-10-20 - Three engine follow-ups (Codex lead / Claude Opus partner)

- General manifest-dread-and-attach binds Equipment to the exact new 2/2, including
  Machete, Windbreaker, Mask and Dissection Tools. Empty/one/two-card libraries,
  stronger existing creatures, source departure and cleanup are covered. The
  simplified manifest cannot turn face up; Tools' other two lines remain ignored.
- Added `mtgsim/delayed.py`: one-time scheduled triggers at the next eligible end
  step (either player or the controller's next). Token/copy creation binds haste
  and sacrifice continuations to its created objects; quoted granted end-step
  abilities remain ordinary triggers. Exact single-target exile/return pairs
  preserve owner, source independence, zone identity and the flying-counter variant.
  An exile leave/re-enter cycle invalidates the return. A stolen token cannot be
  sacrificed by the original ability's controller. Conditional, plural, hand-return
  and exile/destroy-token wording stays visible. Existing blitz/warp/offspring tests pass.
- Aura spells select/store legal targets before paying, expose targets to ward and
  responses, and fail without retargeting. Enchant restrictions are rechecked on
  resolution and on attached Auras; later hexproof doesn't detach. Friendly/hostile
  policy, spell copies, Role tokens and self-attaching Equipment are covered.
  Ownership routing and cross-controller Equipment cleanup support zone changes.
- New regression files: `tests/test_three_followups.py` (27) and
  `tests/test_three_auras.py` (25), including real priority-loop bounce/removal
  responses. Lead reviewed partner's Aura helper/tests; partner independently
  reviewed scheduler, integration, ownership, actual DB cards, coverage and README.
  An optional-blink sweeper regression caught/fixed saving an opposing creature
  and incorrectly fizzling the spell when declining its optional target.
- Coverage: identical input hashes, 1,818 → 1,833 full; 3,042 → 3,027 partial;
  simplified 42 unchanged; one-line misses 1,927 → 1,920; handled sentences
  7,671 → 7,700 / 12,933. New `three-followups-before/after.{json,txt}` and
  `three-followups-deck-before/after.txt`; `decks/coverage/three_followups.txt`
  improves 0/12 → 11/12 full. Prior reports preserved. Before deck CLI used a
  temporary package reconstructed from HEAD plus saved pre-task card/engine edits.
- Verification: `python3 -W ignore::ResourceWarning -m unittest discover -s tests -t .`
  — final 592 OK in 174.608 s (exit 0); initial integration 583 OK in 173.117 s.
  Focused `python3 -W ignore::ResourceWarning -m unittest tests.test_three_followups
  tests.test_three_auras tests.test_auras tests.test_copies tests.test_mechanics
  tests.test_round12 tests.test_round16 tests.test_roles_connive_bite tests.test_coverage
  tests.test_standard_coverage` — 138 OK in 9.166 s. Offline before/after measurement
  and both deck `--coverage` commands exited 0; `git diff --check` clean.
- No new commits since `63aa2df`; all work remains uncommitted on the existing branch.
  No commit/push, real Forge games or Python 3.10/3.13 runs.

## History

### Log entries folded from 2026-10-16 to 2026-10-20 (rounds 1-16)

- 2026-10-16 to 2026-10-18 catch-up: engine rounds 1-15 (PRs #44-#79; auras, search/X spells, counting, copies, modal, ~40 keyword mechanics), web deck-trial/league/replay work, QA pass (523 tests, `QA_RESULTS.md`).
- 2026-10-20 dev loop skill added (`.claude/skills/mtg-dev/SKILL.md`); progress log restructured; 528 tests OK.
- 2026-10-20 Standard coverage re-measure at `63aa2df`: 1,810 full (36.9%), 7,661 / 12,933 sentences; `remeasure.py` added.
- 2026-10-20 AI task reconciliation: precombat `lethal_setup` and `runner.fresh_ai` were already in `363d3ce`.
- 2026-10-20 four Next up tasks (round 16): prepared rearming, flashback continuation, Raid counters, README sync, 33,000-game precombat-setup measurement (combo vs default aggro 14.3 → 21.9%, details in `AI_RESULTS.md`); 540 tests OK; coverage 1,810 → 1,818.


### Milestone 1: observability, parser, AI tie-break, combo fixture (done)

- Builtin audit: `Game.audit` emits `AUDIT {json}` lines (start with first player and
  `turn_unit=player-turn`, mulligan, keep with hand, every life change with cause, loss with cause,
  result with final life and player-turns). Seats in AUDIT are play-order indices.
  `run_match(log_game=...)` streams every game; benchmark `--builtin-logs all` keeps them, default keeps first game.
- Forge parser verified on stored logs: aggro-vs-midrange review log = A on play in both games,
  19 and 11 player-turns; observability smoke = A first once, B first once, 9 and 17. Quiet (`-q`),
  missing turn 1, unknown player labels or turn gaps stay unknown (gap: first player kept, length unknown).
  Observed Forge rule in all stored logs: the previous game's loser starts the next game, so Forge
  starting players are not balanced by construction.
- Attack tie-break (`ai.py choose_attackers`): among saturated lethal/reach plans prefer less
  exposure (lost material + crack-back), then more damage, then fewer attackers.
  Fixtures (tests/test_ai.py) vs prechange `/tmp/mtgsim-ai-before.py`:
  redundancy (3 bears, any 2 lethal, open mana): old 2, new 3; crack-back exposure: both 2;
  costless reach (Bolt lethal, 1 bear, no blockers): old 0, new 1; reach into blocker: both 0.
- Combo fixture `decks/combo/kiln_fiend_strobe.txt` + `tests/test_combo.py` (oracle text written out).
  Rules key line (Strobe + Brute Force on Kiln Fiend = 20) and pilot key line pass.
  Observed pilot miss (scratch probe): Fiend + Temur Battle Rage + Bolt vs 14 life, pilot holds Bolt
  instead of casting it precombat for +3 power (deals 8, not lethal). Not fixed.
- Thirst for Discovery: builtin text corrected to "basic land card" (was "basic snow land");
  general template now discards one basic land instead of two cards when one is in hand.
- Reflection of Kiki-Jiki copying: not implemented (no general copy-effect template); stays a
  documented limitation.

### Milestone 2: pilot measurements (done)

Recorded in AI_RESULTS.md ("Tie-break among already-lethal attacks"); script and raw rows in
`results/pilot-tiebreak/`. New vs old pilot mirrors (5 decks, seeds 11-13, 1,200 games each):
48.0-50.5%, every 95% CI includes 50%. Aggro vs control first looked like -3.6 pts; 12,000 games
per arm gave 72.1% old vs 72.3% new (noise). CPU cost about +1.5%. No measurable win-rate effect.
Seeds are not paired games (RNG desyncs after the first different decision).

### Milestone 3: bounded real Forge benchmark (done)

`benchmarks/small.json` now has 4 pairings (added combo vs midrange). Commands:
`python3 -m mtgsim.benchmark --engine both --forge-dir ~/forge -n 10 --seed {101,202,303} --jobs 2
--clock 20 --builtin-logs all --out results/benchmark-moderate/seed-<s>` (all complete, exit 0).
Observability smoke first: `results/benchmark-observability-2` (-n 2, seed 7, all 4 pairings).
Forge games used: 2 (earlier smoke) + 8 + 120 = 130 of the 150 cap. No Forge exceptions, no draws.
Builtin keeps all 30 game logs per pairing; Forge keeps raw worker logs.

Pooled over the 3 seeds, 30 games per pairing per engine, A's win probability (95% Wilson):

| Pairing | Builtin W-L-D | Builtin | Forge W-L-D | Forge | Forge A on play / draw (games) |
|---|---|---|---|---|---|
| aggro vs midrange | 13-17-0 | 43% (27-61) | 8-22-0 | 27% (14-44) | 18 / 12 |
| aggro vs control | 23-7-0 | 77% (59-88) | 18-12-0 | 60% (42-75) | 12 / 18 |
| midrange vs control | 19-11-0 | 63% (46-78) | 18-12-0 | 60% (42-75) | 12 / 18 |
| combo vs midrange | 4-26-0 | 13% (5-30) | 0-30-0 | 0% (0-11) | 25 / 5 |

Builtin play/draw is exactly 15/15 per pairing (alternation). Forge first player known for all
120 games, game length for all 120. Forge rule observed over 35 worker logs: game 1 starter
varies (A 15, B 20); the loser starts the next game (107/107). So Forge play/draw is unbalanced
and tied to results; splits are reported per observed starting player. Seeds are not paired
across engines. The two "vs control" Forge rows match exactly in total but their game sequences differ.

Full test suite after all changes: 129 tests, OK (Python 3.14; 3.10 not available locally, CI covers it).

### Remaining gaps as of 2026-10-15

- Combo fixture is weak under both pilots (13% builtin, 0% Forge vs Rakdos); whether that is the
  list or the pilots is not established. Builtin pilot misses precombat spell sequencing for
  Kiln Fiend (holds Bolt instead of casting it for +3 power).
- Reflection of Kiki-Jiki copy effects remain unsupported (no general copy template).
- `run_match(ai_a=instance)` reuses one AI object across games, so `HeuristicAI._idle_turns`
  carries between games; the pilot script resets it, the runner does not.
- Forge cannot be made to balance starting players through this wrapper.
- 30 games per pairing: intervals are 30+ points wide; diagnostic only.
