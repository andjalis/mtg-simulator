# AI before/after

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
