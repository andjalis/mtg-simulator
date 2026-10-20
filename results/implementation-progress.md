# Implementation progress

The project's working memory. Agents read **Status**, **Next up** and the latest **Log** entries
at the start of a session and update them at the end (see `.claude/skills/mtg-dev/SKILL.md`).
Newest log entry first; fold old entries into **History** when the log passes ~10 entries.

## Status

- Branch: `docs/standard-coverage-remeasure` · Synced commit: `63aa2df` + uncommitted
  round-16 work, manifest/attach, delayed end-step scheduling, Aura targets and Equipment costs;
  pre-existing AGENTS.md / skill edits, AI measurements and coverage artifacts preserved
- Tests: full suite 614 OK in 193.122 s (2026-10-20, Python 3.14.8, card DB present).
  Final focused mechanics/coverage: 126 OK in 8.374 s, including three regressions
  added after full-suite discovery; 617 tests now discoverable, 25 new Equipment cases.
  Earlier mechanics/Aura pass: 138 OK; 52 regressions.
  Previous AI/combo measurement pass: 32 OK in 1.354 s.
- Coverage (2026-10-20, `python3 -m scripts.coverage_summary`): Standard 1,834/4,902 fully supported
  (37.4%, 60% of rules sentences); all cards 7,602/34,084 (22.3%, 41%); 1 card crashes the
  parser (Dovin, Grand Arbiter: `int('ten')` in `cards._num`).
- Engine: built-in engine plus templates for auras/equipment, X spells, copy effects, library
  search, counting, modal choices and ~40 newer keyword mechanics (rounds 1-15). Standard
  saved-snapshot coverage is 1,834 / 4,902 fully template-matched (37.4%),
  7,702 / 12,933 rules sentences handled (~60%); round-16, three-followup and
  Equipment before/after reports saved separately.
- AI: `HeuristicAI` default; precombat kill setup and per-game reset were already in
  `363d3ce`. Now verified with end-to-end lifecycle regressions and 33,000 measured
  games: combo setup improves tested matchups, aggro/control difference inconclusive
  (`AI_RESULTS.md`). Earlier lethal-attack tie-break has no measurable win-rate effect.
- Web: sequential fullscreen deck trials, league track, saved-run replay, in-browser engine,
  opponent-pool arena; QA passes on validation, recovery and mobile (`QA_RESULTS.md`).
- In flight: nothing; top Equipment follow-up completed and verified locally.
  Earlier three engine follow-ups were independently reviewed.

## Next up

Ranked; each is ready to launch from the repo root.

1. **Additional delayed token actions** (medium) - reuse the scheduler for explicit
   next-end-step exile/destroy continuations, while keeping conditions and unbound pronouns visible.
   `ask "mtg-dev: extend the shared delayed end-step scheduler to general exile/destroy-that-token continuations such as Stormsplitter and Old Hob; test object identity, indestructible, stolen tokens, both turns and one-time execution, run full suite and distinct coverage reports"`
2. **Graveyard spell-target fidelity** (large) - granted flashback still chooses a
   graveyard spell on resolution; bring its targeting closer to the Aura spell path.
   `ask --pair "mtg-dev: choose and store legal graveyard targets for matched flashback-grant spells and abilities at cast/activation time, recheck after responses without retargeting, preserve cost and cleanup semantics, test same-name cards changing zones, run full suite and offline coverage"`
3. **Multiple and mixed Equipment costs** (medium) - one stored equip cost still
   loses alternatives; mixed mana/sacrifice and restricted sacrifice costs stay unsupported.
   `ask "mtg-dev: represent multiple Equip abilities independently and add general mixed mana/sacrifice costs; preserve unsupported restrictions, test cost choice, failed payments, discounts and priority responses, run full suite and distinct offline coverage reports"`

## Known gaps

- Combo fixture remains weak in tested built-in matchups (16–22% vs platinum
  aggro/midrange); list, pilot and engine limits are not separated by these measurements.
- Granted flashback chooses the highest-mana-value eligible graveyard spell on
  resolution. Aura entry directly onto the battlefield outside the matched Role
  effects has no non-target host-selection policy; unattached Auras go to the graveyard.
- Manifest dread uses a simplified 2/2 that cannot turn face up. Dissection Tools
  now manifests/attaches, grants its bonus and pays its sacrifice equip cost.
  Conditional/pronoun prepared variants remain.
- Equipment stores one recognized equip cost (the last recognized line); multiple
  alternatives are not preserved. Mixed mana/sacrifice and restricted sacrifice
  costs remain unsupported. The sacrifice equip policy picks the least valuable
  other creature without evaluating whether its loss is worth the Equipment bonus.
- Delayed scheduling is bounded to matched single-target exile/return pairs and
  token/copy-creation sacrifice continuations. Conditional, plural, return-to-hand,
  exile/destroy-token and unbound pronoun variants remain visible in coverage.
- Custom AI instances are shallow-copied; mutable per-game containers should be
  rebound in their optional `reset()` hook (documented; built-in state resets correctly).
- Forge observed play/draw sampling balances starters when possible; the worker
  cap can leave skew in lopsided matchups (the earlier cannot-balance note was stale).
- Still unsupported per README: casualty (never paid), day/night, Old-Growth Troll's return.
- No real Forge games or Python 3.10/3.13 runs in the latest QA passes (CI covers 3.10/3.13).

## Log

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

### 2026-10-20 - Complete four Next up tasks (Codex lead / Claude Opus partner)

- Added general prepared rearming (`prepare` effect on a live source), explicit
  mana-cost flashback continuation bound to its grant, and Raid entry-counter wording
  in `mtgsim/cards.py` / `engine.py`; 10 new mechanics regressions in `tests/test_round16.py`.
- Saved after reports separately (`results/standard_coverage/round16.*`, deck fixture
  and before/after CLI output). Same input hashes: full 1,810 → 1,818; partial 3,050 →
  3,042; simplified 42 unchanged; one-line misses 1,933 → 1,927; handled sentences
  7,661 → 7,671 / 12,933. Eight-card coverage fixture 0/8 → 8/8 full. Baseline untouched;
  `remeasure.py` now accepts an output stem so the after wrapper shares its method.
- Updated README supported mechanics and approximations against code/tests: Auras,
  copies (including Reflection), X spells, prepared, flashback, disguise/manifest,
  earthbend and remaining gaps. Documented the existing AI lifecycle protocol.
- Reconciled stale tasks 3/4 with `363d3ce`; no duplicate AI/runner implementation.
  Added 2 end-to-end reused-instance/custom-AI tests in `tests/test_ai.py`; partner's
  identity-copy mutation check made the reused-instance regression fail as intended.
- Measured precombat setup on/off, default and Baseline opponents: seeds 21–23,
  1,000 games per seed/arm, 33,000 total. Combo vs default aggro 14.3 → 21.9%
  (+7.6 points, 95% CI ±1.9); vs Baseline aggro 12.4 → 17.3% (+5.0 ±1.8).
  Aggro/control +2.1 ±2.4 is inconclusive. Raw rows and reproducible scripts in
  `results/precombat-setup/`; tables and limitations in `AI_RESULTS.md`.
- Verification (all exit 0): `python3 -W ignore::ResourceWarning -m unittest discover
  -s tests -t .` — 540 OK, 190.152 s; focused `tests.test_round16 tests.test_prepared_convoke
  tests.test_round12` — 28 OK; focused `tests.test_standard_coverage tests.test_coverage
  tests.test_round16 tests.test_auras tests.test_copies tests.test_search_x tests.test_x_tokens`
  — 61 OK, 8.096 s; `tests.test_ai tests.test_combo` — 32 OK, 1.354 s.
  `python3 -m results.standard_coverage.round16` and `python3 -m mtgsim
  decks/coverage/round16.txt --offline --coverage` exited 0; `git diff --check` clean.
- Independent partner review: card diff and README approved; 73 focused template tests
  OK. Lead reviewed lifecycle tests and all 33 measurement rows/summaries. Existing
  guide/skill edits preserved; no commit or push; no real Forge or Python 3.10/3.13 runs.

### 2026-10-20 - Reconcile AI tasks before implementation (Codex / Claude team)

- Verified current HEAD already contains commit `363d3ce` (2026-10-16): general
  `HeuristicAI.lethal_setup`, the exact Kiln Fiend / Battle Rage / Bolt regression,
  and `runner.fresh_ai` with a per-game copy and optional `reset()` hook. The previous
  catch-up entry missed these; Next up / Known gaps 3–4 above are stale pending verification.
- Completing the missing AI measurements and lifecycle compatibility checks alongside
  a bounded card-template round and README corrections. No newer commits since synced HEAD.

### 2026-10-20 - Standard coverage re-measure (Codex)

- Measured unchanged engine at `63aa2df` on saved 4,902-card WOE–FRA snapshot, offline:
  1,810 full (36.9%), 42 simplified, 3,050 partial, zero unknown; 1,933 one-line misses;
  7,661 / 12,933 rules sentences handled (~59%). Matches round-15 full count.
- Added re-measure section to `results/standard_coverage/README.md`, top 20 ignored lines
  overall and on one-line-miss cards, examples, limitations and reproduction commands.
  Added `remeasure.py`, `remeasure.txt`, `remeasure.json` (rankings + input hashes).
- Checks: `python3 -m mtgsim.standard_coverage --top 20` and
  `python3 -m results.standard_coverage.remeasure` exited 0 with identical summaries;
  `python3 -W ignore::ResourceWarning -m unittest tests.test_standard_coverage tests.test_coverage`
  passed all 22 tests in 7.524 s. Full suite not rerun (no engine/card/parser changes).
- No newer commits since synced HEAD. Preserved existing guide/skill/progress edits;
  corrected stale Status coverage figures and advanced Next up. No commit or push.

### 2026-10-20 - Dev loop skill and catch-up (Claude Opus 5.5)

- Added `.claude/skills/mtg-dev/SKILL.md` (Codex sees it via `.agents/skills/mtg-dev` symlink);
  pointer added to `AGENTS.md`. Restructured this file into Status / Next up / Known gaps / Log.
- Checks: 528 tests OK in ~170 s (Python 3.14, card DB present, 2026-10-20)

### 2026-10-16 to 2026-10-18 - Catch-up of unrecorded work (158 commits since `e067d48`)

- Engine rounds 1-15 (PRs #44-#79): auras and self-attaching equipment (`auras.py`), library
  search and X spells (`search.py`, `xspells.py`), counting templates (`counting.py`), copy
  templates (`copies.py`), modal/choose-both (`modal.py`), many triggers and keyword mechanics
  (convoke, mobilize, disguise, discover, empower, bargain, gift, exhaust, renew, flashback grants,
  graveyard statics, firebending, ...). Standard coverage re-measured four times (latest 64e8f6f).
- Web: deck trial page with league track, saved ladder replay, sequential fullscreen trials,
  results stage, opponent-pool arena, browser trial recovery after reload, early-stop deadlock fix.
- QA (2026-10-18): request validation, history store path, decklist comments, parallel
  nine-agent and six-agent interface reviews; suite reached 523 tests. Details in `QA_RESULTS.md`.

## History

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
