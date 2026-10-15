# Implementation progress

Owner: Claude (took over from Codex 2026-10-15). No commits or pushes.

## Milestone 1: observability, parser, AI tie-break, combo fixture (done)

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

## Milestone 2: pilot measurements (done)

Recorded in AI_RESULTS.md ("Tie-break among already-lethal attacks"); script and raw rows in
`results/pilot-tiebreak/`. New vs old pilot mirrors (5 decks, seeds 11-13, 1,200 games each):
48.0-50.5%, every 95% CI includes 50%. Aggro vs control first looked like -3.6 pts; 12,000 games
per arm gave 72.1% old vs 72.3% new (noise). CPU cost about +1.5%. No measurable win-rate effect.
Seeds are not paired games (RNG desyncs after the first different decision).

## Milestone 3: bounded real Forge benchmark (done)

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

## Remaining gaps

- Combo fixture is weak under both pilots (13% builtin, 0% Forge vs Rakdos); whether that is the
  list or the pilots is not established. Builtin pilot misses precombat spell sequencing for
  Kiln Fiend (holds Bolt instead of casting it for +3 power).
- Reflection of Kiki-Jiki copy effects remain unsupported (no general copy template).
- `run_match(ai_a=instance)` reuses one AI object across games, so `HeuristicAI._idle_turns`
  carries between games; the pilot script resets it, the runner does not.
- Forge cannot be made to balance starting players through this wrapper.
- 30 games per pairing: intervals are 30+ points wide; diagnostic only.
