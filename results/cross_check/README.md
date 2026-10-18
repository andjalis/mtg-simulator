# Built-in engine vs Forge: first cross-check (2026-10-15/16)

60 matchups: UB Snow Control against each deck of the old five tiers, plus a round robin inside each
tier. Every deck still exists unchanged in the rank pools, so the results are labelled by rank.
Forge played 40 games per matchup (seed 1, 4 Java processes); the built-in engine played 300 games
per matchup on current `main` (seed 1). Win rates are for the first deck, draws count half.
A matchup is flagged when the engines differ by at least 15 points and |z| ≥ 3.

`first_run.json` holds every count: `forge`, `python_now` (current engine) and `python_tier_era`
(the engine before the card-coverage work merged, 500 games), plus the number and names of
each deck's cards whose text the built-in engine ignores. It predates the provenance checks in
`mtgsim.crosscheck`, so that script won't resume from it; a new run writes its own `results.json`.

## Findings

**16 of 60 matchups are flagged. Median gap 12 points.** The causes, biggest first:

1. **Azorius Artifact Control can't win in the built-in engine (6 flagged, gaps 28–80 points).**
   It loses every built-in game (0–3%) but wins 28–80% in Forge. 18 of its 26 distinct cards have
   ignored text, including all its threats and token makers (Simulacrum Synthesizer, Pinnacle
   Starcage, Repurposing Bay, Cryogen Relic, United Battlefront, Perilous Snare, Castle Doom), and
   it plays no creatures, so it has no way to deal damage. Card coverage.
2. **UB Snow is overrated against Grandmaster decks with ignored cards (4 flagged, 31–46 points).**
   Mono-Green Landfall (9 of 15 cards ignored), Jund Sacrifice and Dimir Midrange (11 each) lose
   much more often in the built-in engine. The same decks' mirror matchups disagree too:
   Izzet Spellementals vs Landfall (−51), Boros Dragons vs Izzet (+36), Dimir Control vs Jund (+39).
   Card coverage; the lists are in `first_run.json`.
3. **UB Snow is overrated by about 25 points even against fully simulated decks (3 flagged).**
   Land Glut, UW Flyers and Green Stompy have no ignored cards, yet UB Snow wins 69–84% built-in
   against 45–60% in Forge. A sampled Forge game shows its AI casting Massacre Wurm into open
   Essence Scatter mana and racing with Hall of Storm Giants instead of stabilising, so this looks
   like Forge's AI piloting a control deck worse than ours rather than a rules bug. Inferred from
   a few logs, not proven.
4. **The card-coverage work already closed the Platinum control gaps.** Before it, Azorius Control
   scored 6–19% built-in against Platinum aggro decks (Forge 30–48%) and 39% against UB Snow
   (Forge 70%). On current `main` all four agree with Forge within 12 points.

One AI misplay seen in built-in logs: it casts removal into a ward cost it can't pay, then casts a
second removal spell into the same ward in the same turn (Hero's Downfall, then Power Word Kill,
into Hall of Storm Giants' ward 3). `ai.py` never checks ward.

## Rerun

    python3 -m mtgsim.crosscheck --forge-dir ~/forge --forge-games 40 --python-games 300 --jobs 4

The full Forge run took about 4 hours on 4 cores.

## All matchups, biggest gap first

| Matchup | Built-in now | Built-in before card fixes | Forge | Gap | z | Ignored cards (A / B) | Flag |
|---|---|---|---|---|---|---|---|
| master/azorius_artifact_control vs grandmaster/izzet_spellementals | 0% | 0% | 80% | -80% | -16.3 | 18 / 7 | yes |
| master/azorius_artifact_control vs master/dimir_control | 0% | 0% | 72% | -72% | -15.4 | 18 / 11 | yes |
| ub_snow_control vs master/azorius_artifact_control | 100% | 100% | 40% | +60% | +13.9 | 0 / 18 | yes |
| grandmaster/izzet_spellementals vs grandmaster/mono_green_landfall | 22% | 22% | 72% | -51% | -6.8 | 7 / 9 | yes |
| master/azorius_artifact_control vs grandmaster/jund_sacrifice | 3% | 0% | 50% | -47% | -9.8 | 18 / 11 | yes |
| ub_snow_control vs grandmaster/mono_green_landfall | 71% | 94% | 25% | +46% | +5.7 | 0 / 9 | yes |
| master/azorius_artifact_control vs grandmaster/mono_green_landfall | 0% | 0% | 40% | -40% | -11.2 | 18 / 9 | yes |
| master/dimir_control vs grandmaster/jund_sacrifice | 59% | 60% | 20% | +39% | +4.7 | 11 / 11 | yes |
| ub_snow_control vs grandmaster/jund_sacrifice | 82% | 84% | 45% | +37% | +5.2 | 0 / 11 | yes |
| grandmaster/boros_dragons vs grandmaster/izzet_spellementals | 94% | 98% | 57% | +36% | +7.1 | 11 / 7 | yes |
| master/azorius_artifact_control vs grandmaster/boros_dragons | 0% | 0% | 35% | -35% | -10.5 | 18 / 11 | yes |
| ub_snow_control vs grandmaster/dimir_midrange | 71% | 90% | 40% | +31% | +4.0 | 0 / 11 | yes |
| master/azorius_artifact_control vs grandmaster/dimir_midrange | 0% | 0% | 28% | -28% | -9.2 | 18 / 11 | yes |
| ub_snow_control vs bronze/land_glut | 80% | 80% | 55% | +25% | +3.5 | 0 / 0 | yes |
| ub_snow_control vs silver/uw_flyers | 84% | 89% | 60% | +24% | +3.7 | 0 / 0 | yes |
| ub_snow_control vs silver/green_stompy | 69% | 70% | 45% | +24% | +3.1 | 0 / 0 | yes |
| master/dimir_control vs grandmaster/mono_green_landfall | 36% | 34% | 12% | +23% | +2.9 | 11 / 9 |  |
| bronze/land_glut vs bronze/vanilla_pile | 62% | 61% | 40% | +22% | +2.6 | 0 / 0 |  |
| ub_snow_control vs grandmaster/boros_dragons | 55% | 59% | 35% | +20% | +2.4 | 0 / 11 |  |
| grandmaster/dimir_midrange vs grandmaster/izzet_spellementals | 77% | 77% | 57% | +20% | +2.7 | 11 / 7 |  |
| grandmaster/izzet_spellementals vs grandmaster/jund_sacrifice | 44% | 43% | 62% | -19% | -2.2 | 7 / 11 |  |
| grandmaster/dimir_midrange vs grandmaster/jund_sacrifice | 86% | 87% | 68% | +18% | +3.0 | 11 / 11 |  |
| grandmaster/jund_sacrifice vs grandmaster/mono_green_landfall | 21% | 20% | 38% | -17% | -2.4 | 11 / 9 |  |
| platinum/mono_green_stompy vs platinum/mono_red_aggro | 79% | 79% | 62% | +17% | +2.3 | 1 / 0 |  |
| master/dimir_control vs grandmaster/izzet_spellementals | 61% | 62% | 45% | +16% | +1.9 | 11 / 7 |  |
| silver/green_stompy vs silver/uw_flyers | 68% | 68% | 52% | +16% | +1.9 | 0 / 0 |  |
| ub_snow_control vs gold/dimir_control | 76% | 76% | 90% | -14% | -2.0 | 0 / 0 |  |
| ub_snow_control vs grandmaster/izzet_spellementals | 96% | 100% | 82% | +14% | +3.7 | 0 / 7 |  |
| master/dimir_control vs grandmaster/dimir_midrange | 26% | 26% | 12% | +14% | +1.9 | 11 / 11 |  |
| platinum/azorius_control vs platinum/rakdos_midrange | 45% | 6% | 32% | +12% | +1.5 | 0 / 0 |  |
| gold/boros_burn vs gold/dimir_control | 66% | 71% | 55% | +11% | +1.4 | 0 / 0 |  |
| ub_snow_control vs gold/orzhov_midrange | 61% | 66% | 50% | +11% | +1.4 | 0 / 0 |  |
| grandmaster/boros_dragons vs grandmaster/mono_green_landfall | 76% | 78% | 65% | +11% | +1.5 | 11 / 9 |  |
| silver/red_goblins vs silver/uw_flyers | 61% | 64% | 50% | +11% | +1.3 | 0 / 0 |  |
| ub_snow_control vs master/dimir_control | 86% | 99% | 75% | +11% | +1.7 | 0 / 11 |  |
| ub_snow_control vs platinum/mono_green_stompy | 30% | 27% | 40% | -10% | -1.3 | 0 / 1 |  |
| ub_snow_control vs platinum/azorius_control | 20% | 61% | 30% | -10% | -1.5 | 0 / 0 |  |
| gold/dimir_control vs gold/orzhov_midrange | 35% | 39% | 45% | -10% | -1.2 | 0 / 0 |  |
| bronze/five_color_mess vs bronze/land_glut | 18% | 17% | 28% | -9% | -1.4 | 0 / 0 |  |
| gold/gruul_midrange vs gold/orzhov_midrange | 26% | 29% | 18% | +9% | +1.2 | 0 / 0 |  |
| grandmaster/boros_dragons vs grandmaster/jund_sacrifice | 96% | 96% | 88% | +8% | +2.3 | 11 / 11 |  |
| ub_snow_control vs bronze/vanilla_pile | 86% | 84% | 78% | +8% | +1.4 | 0 / 0 |  |
| ub_snow_control vs silver/red_goblins | 45% | 42% | 38% | +8% | +0.9 | 0 / 0 |  |
| silver/green_stompy vs silver/red_goblins | 75% | 71% | 68% | +8% | +1.1 | 0 / 0 |  |
| grandmaster/boros_dragons vs grandmaster/dimir_midrange | 83% | 91% | 75% | +8% | +1.2 | 11 / 11 |  |
| gold/boros_burn vs gold/gruul_midrange | 38% | 43% | 45% | -7% | -0.9 | 0 / 0 |  |
| platinum/mono_green_stompy vs platinum/rakdos_midrange | 63% | 64% | 70% | -7% | -0.9 | 1 / 0 |  |
| platinum/mono_red_aggro vs platinum/rakdos_midrange | 40% | 43% | 32% | +7% | +0.9 | 0 / 0 |  |
| ub_snow_control vs gold/gruul_midrange | 75% | 73% | 80% | -5% | -0.7 | 0 / 0 |  |
| grandmaster/dimir_midrange vs grandmaster/mono_green_landfall | 52% | 54% | 57% | -5% | -0.6 | 11 / 9 |  |
| ub_snow_control vs bronze/five_color_mess | 97% | 97% | 92% | +5% | +1.6 | 0 / 0 |  |
| grandmaster/boros_dragons vs master/dimir_control | 96% | 95% | 92% | +3% | +1.0 | 11 / 11 |  |
| ub_snow_control vs gold/boros_burn | 33% | 26% | 30% | +3% | +0.4 | 0 / 0 |  |
| gold/boros_burn vs gold/orzhov_midrange | 23% | 36% | 25% | -2% | -0.2 | 0 / 0 |  |
| ub_snow_control vs platinum/mono_red_aggro | 24% | 25% | 25% | -1% | -0.2 | 0 / 0 |  |
| bronze/five_color_mess vs bronze/vanilla_pile | 36% | 32% | 35% | +1% | +0.1 | 0 / 0 |  |
| gold/dimir_control vs gold/gruul_midrange | 82% | 79% | 82% | -1% | -0.1 | 0 / 0 |  |
| platinum/azorius_control vs platinum/mono_green_stompy | 48% | 19% | 48% | +1% | +0.1 | 0 / 1 |  |
| ub_snow_control vs platinum/rakdos_midrange | 35% | 34% | 35% | -0% | -0.0 | 0 / 0 |  |
| platinum/azorius_control vs platinum/mono_red_aggro | 30% | 12% | 30% | +0% | +0.0 | 0 / 0 |  |

## Forge pilot notes

Forge's AI does not play every card it is given, so decks that rely on them read low in this
comparison. Seen so far (Forge logs of 112 games of Dimir Control vs Jund Sacrifice, 2026-10-18):

- **Seasoned Cryomancer** (4 copies in Dimir Control): cast 0 times. Forge's AI only discards or mills
  it. The built-in AI casts it about once per game.
- **Uldaros Theorix** (2 copies): cast 0 times in Forge, 0.27 per game in the built-in engine.

Making Cryomancer and Theorix uncastable in the built-in engine moves Dimir Control vs Jund from 52%
to 37 to 43%, which is 10 to 15 of the 30+ point gap to Forge. When a matchup disagrees, check
`compare_dimir_jund_logs.py` (cards cast per game in Forge logs vs built-in games) before assuming
a rules or card bug. See `RERUN_5_2026-10-18.md`.
