# Test tiers

```
python3 -m mtgsim MY_DECK.txt --ladder --engine forge --forge-dir ~/forge -n 50 --jobs 4
python3 -m mtgsim MY_DECK.txt --ladder -n 200                      # built-in engine, fast
python3 -m mtgsim MY_DECK.txt --tier pro --engine forge --forge-dir ~/forge
python3 -m mtgsim --list-tiers
```

The ladder plays a deck against each tier from the bottom up. A tier is cleared with a win rate of
at least 50% against all of its decks together; the deck's level is the highest tier cleared before
the first failure. To add an opponent, drop a decklist into the tier's folder.

| Tier | Folder | Decks |
| --- | --- | --- |
| 1 Trash | `1-trash/` | Overcosted vanilla creatures; five colours on basics; 32 lands |
| 2 Beginner | `2-beginner/` | Starter-style mono-green, red goblins, white-blue flyers |
| 3 Advanced | `3-advanced/` | Focused budget decks: Boros burn, Dimir control, Gruul and Orzhov midrange |
| 4 Semi-pro | `4-semipro/` | Top Standard decks of 2022: mono-red, mono-green, Rakdos midrange, Azorius control |
| 5 Pro | `5-pro/` | The best current Standard tournament decks (below) |

Tiers 1 to 3 were built for this project from cards the built-in engine fully supports. Checked
with the built-in engine (30 games per pairing), each tier beats the one below it on average:
beginner 71% against trash, advanced 65% against beginner, semi-pro 64% against advanced.

## Pro tier sources

Each list is a real top finisher from 2026-10-12, picked from the most-played archetypes in both
[AetherHub's tournament metagame](https://aetherhub.com/Metagame/Standard-Events/) and
[MTGGoldfish's Standard metagame](https://www.mtggoldfish.com/metagame/standard) (last 30 days,
read 2026-10-15). Each file's comment header has the player, event and link.

| Deck | Meta share (AetherHub / MTGGoldfish) | List from |
| --- | --- | --- |
| Izzet Spellementals | 14.1% / 12.3% | Mortaa, MTGO Standard Challenge 32, 12th |
| Jund Sacrifice | 11.5% / 6.3% | harrowhark, MTGO Standard Challenge 32, 2nd |
| Dimir Midrange | 11.0% / 9.6% | Ale_Mtg, MTGO Standard Challenge 32, top 8 |
| Azorius Artifact Control | 10.3% / – | shadow438, MTGO Standard Challenge 32, top 8 |
| Mono-Green Landfall | 9.4% / 8.6% | MagicRaiz, MTGO Standard Challenge 32, top 4 |
| Boros Dragons | 8.2% / 8.4% | Hanta, Izzet Explosive Experiment event (66 players), top 8 |
| Dimir Control | 4.5% / – | gazmon48, MTGO Standard Challenge 32, top 4 |

Not included: MTGGoldfish's counterspell Azorius Control (6%) and 4c Control (5%), whose exact lists
weren't readable from here. The Standard metagame moves quickly, so refresh this tier every few
weeks and after each new set. Every pro-tier card is in the offline card database and in Forge.
Sideboards are in the files but neither engine plays them yet.
