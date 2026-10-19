# AI before/after

## Artifact Control vs Dimir Midrange after the card thread's additions, 2026-10-19

Built-in engine on `main` at `a76c7d4` (300 games, seed 1, `results/cross_check/rerun_flagged_10.json`) after
Kaito, Tishana's Tidebinder and Wan Shi Tong, Librarian landed (PRs 11 and 15). The Wondrous Wasp is still
ignored. Forge is the 36% over 100 games from the section below.

| Matchup | Last round | Now | Forge | Gap now | z |
|---|---|---|---|---|---|
| Azorius Artifact Control vs Dimir Midrange | 55% | 42% | 36% (100 games) | +6 | +1.1 |

- **No longer flagged**: the three added cards moved our side down 13 points, which confirms the gap was
  mostly the missing cards. Re-check once the Wasp is added.

## Forge cross-check, Dimir Midrange and Izzet at 100+ Forge games, 2026-10-19

Built-in engine on `main` at `cf77c02` (300 games per matchup, seed 1, `results/cross_check/rerun_flagged_9.json`).
Forge was played 100 games of Azorius Artifact Control vs Dimir Midrange (seed 11, `forge_100_dimid.json`)
and a second 100 vs Izzet (seed 21, `forge_100_izzet2.json`), which combine with the earlier 100 (78/100) into
160/200.

| Matchup | Last round | Now | Forge | Gap now | z |
|---|---|---|---|---|---|
| Azorius Artifact Control vs Dimir Midrange | 58% | 55% | 36% (100 games) | +19 | +3.3 |
| Azorius Artifact Control vs Izzet | 55% | 68% | 80% (200 games) | -12 | -2.9 |

- **Forge's 28% on Dimir Midrange was a small-sample low**: at 100 games it is 36%. Our side is still 19
  points above, so the matchup stays flagged. Dimir Midrange still has four ignored cards (Kaito, Bane of
  Nightmares; The Wondrous Wasp; Tishana's Tidebinder; Wan Shi Tong, Librarian); re-check once the card
  thread adds them.
- **Izzet is no longer flagged**: 55% to 68% after the control AI fixes, against Forge's 80% (gap 23 to 12).

## Forge cross-check after the control and combo AI fixes, 2026-10-19

Built-in engine on `main` at `29851a4` (300 games per matchup, seed 1) against Forge's results (first
player's win rate, draws half). The AI changes since the last round are the Jund and control-deck fixes
(PRs 88 and 2). Forge numbers are unchanged from `results/cross_check/`; Azorius Artifact Control vs Boros
Dragons was re-run at 100 games (seed 11, `forge_100_boros.json`) because 40 games left the gap unreadable.
Counts are in `results/cross_check/rerun_flagged_8.json`.

| Matchup | Last round | Now | Forge | Gap now | z |
|---|---|---|---|---|---|
| Izzet vs Mono-Green Landfall | 42% | 50% | 65% (100 games) | -15 | -2.5 |
| Azorius Artifact Control vs Boros Dragons | 16% | 25% | 34% (100 games) | -9 | -1.7 |
| Azorius Artifact Control vs Dimir Midrange | 47% | 58% | 28% (40 games) | +31 | +3.7 |
| Azorius Artifact Control vs Izzet | 55% | 55% | 78% (100 games) | -23 | -4.0 |
| Azorius Artifact Control vs Jund | 55% | 61% | 50% (40 games) | +11 | +1.3 |
| Azorius Artifact Control vs Mono-Green Landfall | 41% | 43% | 40% (40 games) | +3 | +0.4 |
| Azorius Artifact Control vs Dimir Control | 38% | 50% | 62% (100 games) | -12 | -2.0 |

- **Closer to Forge:** Izzet vs Landfall (gap 23 to 15, no longer flagged), Artifact Control vs Dimir
  Control (24 to 12, no longer flagged) and Artifact Control vs Boros Dragons (19 to 9; Forge's 40-game
  35% held up at 34% over 100).
- **Further from Forge:** Artifact Control vs Dimir Midrange went from +19 to +31 and is now flagged.
  The Dimir Midrange deck still has four ignored cards (Kaito, The Wondrous Wasp, Tishana's Tidebinder,
  Wan Shi Tong), which Forge plays and the built-in engine does not.
- **Unchanged:** Artifact Control vs Izzet is still flagged (55% vs Forge's 78%).

## Card-effects integration check, 2026-10-18 (rounds 46–48)

Two synthetic 60-card mirrors exercise regeneration and learn with HeuristicAI
against BaselineAI on the same rules engine. Each ran 40 games, seed 20261018,
alternating play/draw (20 each); draws count as half a win. The learn mirror gives
each player the same eight-card Lesson sideboard, reset for every game.

| Fixture | Heuristic wins | Baseline wins | Draws | Heuristic score, approximate 95% CI |
| --- | ---: | ---: | ---: | --- |
| Regeneration | 18 | 21 | 1 | 46.2% (31.8%–61.3%) |
| Learn | 21 | 19 | 0 | 52.5% (37.5%–67.1%) |

The games resolved 688 regenerations and 612 learn choices. Both intervals include
50%, so these small fixtures do not establish a pilot-performance difference.
They are integration checks, not before/after measurements or tournament-deck
performance claims. Pure regeneration actions are held for threats, and both
pilots value learn's available Lesson or discard-and-draw option.
Exact deck definitions, sideboards, outcomes and event counts are in
[`results/card_effect_batches/rounds46-48-ai.json`](results/card_effect_batches/rounds46-48-ai.json).

## Card-effects integration check, 2026-10-18 (rounds 38–45)

Two synthetic 60-card mirrors exercise the added mechanics with HeuristicAI
against BaselineAI on the same rules engine. Each ran 40 games, seed 20261018,
alternating play/draw (20 each); draws count as half a win.

| Fixture | Heuristic wins | Baseline wins | Draws | Heuristic score, approximate 95% CI |
| --- | ---: | ---: | ---: | --- |
| Wither and persist | 25 | 13 | 2 | 65.0% (49.5%–77.9%) |
| Storm, cascade and rebound | 16 | 24 | 0 | 40.0% (26.3%–55.4%) |

Both intervals include 50%; these samples do not establish a pilot-performance
difference. They are fixture-specific integration checks, not before/after
measurements or tournament-deck performance claims. The later fixes for multiple
native storm/cascade instances and wither on damage spells do not alter these
fixtures, which use single instances and wither creatures.
Exact deck definitions and outcomes are in
[`results/card_effect_batches/rounds38-45-ai.json`](results/card_effect_batches/rounds38-45-ai.json).

## Card-effects integration check, 2026-10-18 (rounds 35–37)

Two synthetic 60-card mirrors exercise payment assistance and undying with
HeuristicAI against BaselineAI on the same rules engine. Each ran 40 games,
seed 20261018, alternating play/draw (20 each). Draws count as half a win.

| Fixture | Heuristic wins | Baseline wins | Draws | Heuristic score, approximate 95% CI |
| --- | ---: | ---: | ---: | --- |
| Improvise | 18 | 21 | 1 | 46.2% (31.8%–61.3%) |
| Delve and undying | 22 | 15 | 3 | 58.8% (43.4%–72.6%) |

Both confidence intervals include 50%; these small fixtures do not establish a
pilot-performance difference. These are integration checks, not before/after
measurements of the rules changes or tournament-deck performance claims. The
payment policies use available artifacts and graveyard cards before mana for
generic costs; the heuristic and baseline pilots share those rules and policies.
Exact deck definitions and results are in
[`results/card_effect_batches/rounds35-37-ai.json`](results/card_effect_batches/rounds35-37-ai.json).

## Card-effects integration check, 2026-10-18 (rounds 26–28)

Two 60-card synthetic mirrors exercise infect and exalted with HeuristicAI against
BaselineAI on the same rules engine. Each ran 40 games, seed 20261018, alternating
play/draw (20 each). Draws count as half a win.

| Fixture | Heuristic wins | Baseline wins | Draws | Heuristic score, approximate 95% CI |
| --- | ---: | ---: | ---: | --- |
| Infect | 35 | 4 | 1 | 88.8% (75.4%–95.3%) |
| Exalted | 36 | 1 | 3 | 93.8% (81.8%–98.0%) |

These are small fixture-specific pilot comparisons, not a before/after measurement
of the AI changes or evidence of performance on tournament decks. They confirm
that games using the new mechanics complete and that the current heuristic pilot
outperforms the baseline in these fixtures. Devoid's color and cost semantics are
covered by regression tests rather than a separate mirror.
Exact deck definitions and counts are in
[`results/card_effect_batches/rounds26-28-ai.json`](results/card_effect_batches/rounds26-28-ai.json).

## Card-effects integration check, 2026-10-18 (rounds 23–25)

Two 60-card synthetic mirrors check that the new land targets and proliferate policy work in played games.
Each uses HeuristicAI against BaselineAI for 40 games, seed 20261018, alternating play/draw (20 each).
Both pilots use the same current rules engine. These small samples compare pilots, not engine versions.

| Fixture | Heuristic wins | Baseline wins | Draws | Heuristic score, approximate 95% CI |
| --- | ---: | ---: | ---: | --- |
| Land denial | 15 | 25 | 0 | 37.5% (24.2%–53.0%) |
| Counter growth | 17 | 23 | 0 | 42.5% (28.5%–57.8%) |

The land-denial mirror resolved 210 land destructions; counter growth resolved 325 proliferations.
Both intervals include 50%, so these measurements do not establish a pilot-performance difference.
Exact fixture definitions and outcome counts are in
[`results/card_effect_batches/rounds23-25-ai.json`](results/card_effect_batches/rounds23-25-ai.json).

`BaselineAI` is the first AI (with the engine's default policies for instants,
abilities and alternative casts). `HeuristicAI` is the rewritten one, now the
default. All numbers are on the current engine (stack, triggers, adventures,
vehicles, manlands and the other mechanics from the second engine update),
1,600 games per pairing, 95% margin about ±2.4 points. Draws (the 60-turn cap)
count as half a win.

## Is the new AI a better player?

Each deck piloted by the new AI against the same deck piloted by the old one:

| Mirror | New AI wins |
| --- | --- |
| Mono-red aggro (sample) | 53% |
| Green stompy (sample) | 64% |
| Orzhov midrange (sample) | 56% |
| UB snow control (sample) | 72% |
| Mono-red aggro (gauntlet) | 57% |
| Rakdos midrange (gauntlet) | 63% |
| Mono-green stompy (gauntlet) | 47% |

The gauntlet green mirror is the one place it isn't ahead. Swapping either
half of its combat code (attacks or blocks) back to the old version gives 50%,
so neither half is clearly at fault. The likely cause is what the combat model
leaves out: Pelt Collector growing as creatures die, and Esika's Chariot making
Cats when it attacks.

## Overall win rates, everyone vs everyone

Sample decks:

| Deck | Old AI | New AI |
| --- | --- | --- |
| UB snow control | 48% | 59% |
| Orzhov midrange | 58% | 55% |
| Green stompy | 49% | 50% |
| Mono-red aggro | 46% | 37% |

Gauntlet decks:

| Deck | Old AI | New AI |
| --- | --- | --- |
| Mono-green stompy | 71% | 68% |
| Rakdos midrange | 46% | 49% |
| Mono-red aggro | 34% | 33% |

Head to head (row deck's win rate, old → new):

| | vs green | vs Orzhov | vs UB control |
| --- | --- | --- | --- |
| Mono-red | 36% → 27% | 30% → 27% | 71% → 57% |
| Green | | 33% → 39% | 49% → 36% |
| Orzhov | | | 37% → 30% |

| | vs mono-green | vs Rakdos |
| --- | --- | --- |
| Gauntlet mono-red | 28% → 25% | 40% → 41% |
| Gauntlet mono-green | | 69% → 61% |

## Test tiers: does the better deck win more?

The ladder only works if a stronger deck beats a weaker one, so this is the
main check of the AI. Every deck in tiers 1 to 4 (trash to semi-pro) played
every deck in the other tiers, 400 games per pairing, same AI on both sides.
The pro tier is left out because the built-in engine ignores much of its text.

| Higher tier's win rate | Old AI | New AI | New AI, tuned (current) |
| --- | --- | --- | --- |
| Beginner vs trash | 76% | 75% | 75% |
| Advanced vs beginner | 60% | 62% | 63% |
| Semi-pro vs advanced | 61% | 66% | 65% |
| Semi-pro vs beginner | 65% | 70% | 71% |
| All tier pairs | 68.9% | 71.8% | 72.2% |

The new AI widens the gaps between the better tiers, mostly because it plays
the semi-pro control and midrange decks properly: Azorius control goes from 33%
to 44% overall, Rakdos midrange from 77% to 82%. "Tuned" is the latest change,
which values life less steeply (`LIFE_SCALE` 8 → 5), so the AI races and trades
a little more readily. Against the previous version, settings of 4.5 and 6 won 51.2–51.3% of games on
average across 7 mirrors and 4 cross matchups.

A look-ahead attacker that plays each candidate attack out to the end of the
game was also tried. It won 53% (±5) of a red mirror against the current AI but
ran about 50 times slower, so it was not added.

## Round 2: control and land drops

Each change was measured against the previous AI on every pairing of the old
trash to semi-pro decks, both seats, with only the new AI using the change:

| Change | Deck it affects | Win rate vs previous AI |
| --- | --- | --- |
| Sweepers wait until they take out several cards (unless the AI is under pressure) | Azorius control | 40% → 45% (±2) |
| Modal double-faced cards are played as lands when no other land is in hand | Mono-green stompy (Kazandu Mammoth) | 84.3% → 85.1% (±1) |
| Cantrips that surveil (Consider) are cast at the opponent's end step | Control decks | too small to measure |

Tried and dropped: holding flash permanents such as The Wandering Emperor for
the opponent's turn (Azorius 44% → 41%), and stricter two-land keeps (no
change, and worse when two two-drops were required).

## Tie-break among already-lethal attacks (October 2026)

Lethal and burn-reach attack scores saturate, so the old attacker picked the
fewest attackers among tied plans. The current one breaks those ties by least
exposure (attackers that die in combat plus crack-back if the kill fails), then
more damage, then fewer attackers. It never looks at the opponent's hand.

Fixed positions (tests in `tests/test_ai.py`), old → new choice:

| Position | Old | New |
| --- | --- | --- |
| 3 bears, any 2 lethal, opponent has open mana | 2 attack | 3 attack |
| Same, but a failed kill leaves us dead to crack-back | 2 | 2 |
| Bolt in hand is lethal, 1 bear, no blockers | 0 | 1 |
| Bolt in hand is lethal, bear would meet a bigger blocker | 0 | 0 |

Games (platinum ranked lists plus the combo fixture; script and raw rows in
`results/pilot-tiebreak/`). Draws count half. Each seed restarts one RNG
stream for 400 games, but the streams desync after the first different
decision, so seeds are not paired games.

| New pilot vs old pilot, same deck | Seeds 11–13 | Pooled (1,200 games, 95% CI) |
| --- | --- | --- |
| Mono-red aggro | 50.0, 49.0, 49.5% | 49.5% (46.7–52.3) |
| Rakdos midrange | 45.5, 48.7, 50.5% | 48.2% (45.4–51.1) |
| Azorius control | 49.2, 48.2, 50.5% | 49.3% (46.5–52.2) |
| Mono-green stompy | 51.2, 49.2, 51.0% | 50.5% (47.7–53.3) |
| Kiln Fiend combo fixture | 50.7, 47.7, 45.5% | 48.0% (45.2–50.8) |

Cross matchups, both sides old vs both sides new, 1,200 games each: aggro vs
midrange 45.1 → 45.2%, midrange vs control 74.3 → 76.0%, stompy vs aggro
75.1 → 74.8%, stompy vs midrange 61.8 → 61.9%, combo vs midrange 11.8 →
12.0%, combo vs aggro 14.7 → 14.7%.

Aggro vs control first showed 74.2 → 70.6%. Splitting the sides showed the
aggro pilot was the one that changed (control's change made no difference),
but 24 more seeds (12,000 games per arm, aggro new or old vs control old) gave
72.1% old and 72.3% new, standard error 0.4 points: the first gap was noise.
In 400 aggro-vs-control games the two pilots chose differently 119 times,
117 of them by adding attackers to an already lethal attack on an empty board.

These runs used the AI before the Round 2 changes above were merged. Rerun on the
merged AI (tie-break on vs off, otherwise identical): mirrors 49.5, 48.2, 49.1,
51.0 and 48.0% for aggro, midrange, control, stompy and combo (1,200 games each,
±2.8), and aggro vs control 68.5 → 69.4% (2,400 games per arm, ±1.9).

Result: the change fixes the fixture positions and has no detectable effect on
win rates at these sample sizes. It costs about 1.5% more CPU time per game
(240 s → 244 s for the cross-matchup runs). The suspected Tenacious Underdog
misplay from the review log was not reproduced: that log had no life totals.

## What changed and why

- **Control was the deck the old AI couldn't play.** It cast counters and
  removal on anything, tapped out on its own turn, and blocked badly. Holding
  counters for real threats, killing attackers rather than every creature,
  and casting card draw at the opponent's end step makes it the best sample
  deck.
- **Mono-red's low numbers are the deck, not its pilot.** The new AI plays red
  at least as well as the old one (it wins both red mirrors, and does better
  against old-AI opponents), and other red strategies tested worse: always
  burning face won 21% vs Orzhov and 17% vs green, always burning creatures
  28% and 33%. Red's results drop because its opponents now block and race
  correctly. The sample list (24 lands, 1/1s and 2/2s that two-mana 3/3s wall
  off) runs out of gas; its games average about 17 turns, so it gains nothing
  from being on the play. The gauntlet red list does get the expected edge on
  the play (31–46% on the play vs 19–36% on the draw).
- **UB mirrors still often reach the turn cap**: neither side can win
  through the other's removal.

## Reproducing

```python
from mtgsim.ai import BaselineAI, HeuristicAI
from mtgsim.carddb import CardDB
from mtgsim.decklist import load_deck
from mtgsim.runner import build_deck, run_match

db = CardDB(offline=True)
red = build_deck(db, load_deck("decks/mono_red_aggro.txt")[1])
res, _ = run_match("new red", red, "old red", red, games=1000, seed=1,
                   ai_a=HeuristicAI(), ai_b=BaselineAI())
print(res.summary())
```
