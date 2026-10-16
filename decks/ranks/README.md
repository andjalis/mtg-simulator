# Ranks

```
python3 -m mtgsim MY_DECK.txt --ladder --engine forge --forge-dir ~/forge -n 50 --jobs 4
python3 -m mtgsim MY_DECK.txt --ladder -n 200                      # built-in engine, fast
python3 -m mtgsim MY_DECK.txt --rank grandmaster --engine forge --forge-dir ~/forge
python3 -m mtgsim --list-ranks
```

The ladder plays a deck against each rank's pool from the bottom up. A rank is cleared with a win
rate of at least 50% against all of its decks together; the deck's rank is the highest one cleared
before the first failure. To add an opponent, drop a decklist into the rank's folder. Each file's
comment header says what the deck is and, for tournament lists, the player, event, placing and link.

| Rank | Folder | Decks | What they are |
| --- | --- | --- | --- |
| Bronze | `1-bronze/` | 5 | Badly built piles: overcosted vanillas, five colours on basics, 32 lands, all card draw and no threats |
| Silver | `2-silver/` | 5 | Starter-style mono-colour decks with filler cards |
| Gold | `3-gold/` | 6 | Focused budget decks: Boros burn, Dimir control, Gruul, Golgari, Orzhov and Selesnya creatures |
| Platinum | `4-platinum/` | 7 | Top Standard decks of 2022 (older, weaker card pool) |
| Diamond | `5-diamond/` | 5 | Current Standard tournament decks from the edge of the metagame |
| Master | `6-master/` | 6 | Strong current Standard decks just outside the top archetypes |
| Grandmaster | `7-grandmaster/` | 6 | The most-played, best-performing current Standard decks |

Bronze to Gold were built for this project from cards the built-in engine supports (a few cards
have a line of text it ignores; `--coverage --rank bronze silver gold` lists them). From Platinum
up the lists are real tournament decks; use `--engine forge` there, because the built-in engine
ignores much of their text.

## Where the tournament lists come from

Diamond, Master and Grandmaster are picked from every MTGO Standard Challenge between 2026-09-10 and
2026-10-11 (38 events, 1,147 decklists, from the
[MTGODecklistCache](https://github.com/Jiliac/MTGODecklistCache) mirror of mtgo.com results, read
2026-10-15). The decks were grouped into archetypes by shared cards. An archetype's rank follows its
share of the field and how often it reached the top 8; each list is a recent top-8 finish of it.
Five Grandmaster and two Master lists (the ones whose headers cite AetherHub) were picked earlier
the same day from AetherHub and MTGGoldfish's metagame pages, from 2026-10-12 events.

| Rank | Deck | Share of Challenge decks | Top 8s | List |
| --- | --- | --- | --- | --- |
| Grandmaster | Jund Sacrifice (Golgari/Jund) | 13.2% | 50 | harrowhark, Challenge 32, 2nd, 2026-10-12 |
| Grandmaster | Izzet Spellementals | 12.8% | 30 | Mortaa, Challenge 32, 12th, 2026-10-12 |
| Grandmaster | Mono-Green Landfall | 9.3% | 36 | MagicRaiz, Challenge 32, top 4, 2026-10-12 |
| Grandmaster | Dimir Midrange | 8.8% | 32 | Ale_Mtg, Challenge 32, top 8, 2026-10-12 |
| Grandmaster | Boros Dragons | 7.0% | 19 | Hanta, 66-player event, top 8, 2026-10-12 |
| Grandmaster | Azorius Control | 5.7% | 20 | _Atraxa_, Challenge 32 Special, 3rd, 2026-10-09 |
| Master | Dimir Control | 4.2% | 14 | gazmon48, Challenge 32, top 4, 2026-10-12 |
| Master | Orzhov Lifegain | 3.9% | 17 | CardGameAddict, Challenge 32 Special, 1st, 2026-10-09 |
| Master | Izzet Prowess | 3.7% | 7 | _IlNano_, Challenge 32, 1st, 2026-10-02 |
| Master | Azorius Artifact Control | 2.8% | 15 | shadow438, Challenge 32, top 8, 2026-10-12 |
| Master | Jeskai Control | 2.4% | 9 | Venom01, Challenge 16 Special, 1st, 2026-10-09 |
| Master | Sultai Reanimator | 2.1% | 12 | Martin_Dominguez, Challenge 32 Special, 3rd, 2026-10-05 |
| Diamond | Boros Dwarves | 2.6% | 4 | Kritik, Challenge 32, 3rd, 2026-09-19 |
| Diamond | Rakdos Aggro | 2.4% | 3 | PedraStone, Challenge 32, 6th, 2026-10-02 |
| Diamond | Azorius Flyers | 1.7% | 6 | JonDaBill, Challenge 16 Special, 3rd, 2026-10-07 |
| Diamond | Mono-Black Aggro | 1.0% | 3 | Bertram, Challenge 32, 3rd, 2026-09-15 |
| Diamond | Mardu Aggro | 0.9% | 4 | Bugsy69, Challenge 32, 1st, 2026-09-14 |

Platinum's three new lists (Grixis, Esper and Mono-White Midrange) are the three most-played
archetypes of MTGO Standard Challenges from October to December 2022 (1,480 decklists, same
source); the other four are the earlier 2022 semi-pro decks.

Not included: Izzet Gandalf Aggro (1.4%), whose lists play Fire-Brained Scheme, a card neither
Forge nor the card database knows yet. The Standard metagame moves quickly, so refresh Diamond to
Grandmaster every few weeks and after each new set. Sideboards are in the files but neither engine
plays them yet.

## Checking the order

Every deck in a rank played every deck in each rank below it, same AI on both sides. The number is
the higher rank's win rate against the lower one, over all its decks.

Built-in engine, 100 games per pairing (2026-10-15):

| | vs Bronze | vs Silver | vs Gold |
| --- | --- | --- | --- |
| Silver | 81% | | |
| Gold | 87% | 67% | |
| Platinum | 84% | 65% | 58% |

Forge, each deck against every deck in the rank directly below, 4 games per pairing (120 to 144
games per row, so about ±8 points):

| | Win rate | Games |
| --- | --- | --- |
| Diamond vs Platinum | 65% | 140 |
| Master vs Diamond | 22% | 120 |
| Grandmaster vs Master | 50% | 144 |

Bronze to Diamond climb as intended. Above Diamond the order follows tournament results, not how
well the AI pilots the decks: Forge's AI plays fast aggro decks well and control, combo and
reanimator decks badly, so Diamond's aggro decks beat most of Master, and Grandmaster's control
decks (Azorius Control, Izzet Spellementals) lose to Master. Per deck, Boros Dwarves, Rakdos Aggro
and Boros Dragons did best and Azorius Control, Dimir Control and Izzet Spellementals worst. Treat
a deck's Master or Grandmaster result as "how it does against the real top decks as the AI plays
them", not as a strict ladder step.

The Gold deck Mono-Blue Tempo was dropped before this run for winning only 26% against Silver.

## Fitted ratings

Every pool deck has its own rating in `ratings.json`, fitted from simulated results by
`python3 -m mtgsim.calibrate` (Bradley-Terry on the Elo scale, Bronze's mean anchored at 900, the
centre of its band). The ladder rates each opponent at its fitted rating when it computes a deck's
MMR, and uses the band centre for any deck the file doesn't list. The rule for clearing a rank (50%
against its pool) is unchanged. `python3 -m mtgsim --list-ranks` shows the ratings.

The current fit (2026-10-16) uses the rank-order numbers above, plus 20 built-in games for every
Silver-Bronze, Gold-Silver and Platinum-Gold deck pairing (`--play 20`, 1,940 games), which give
Bronze to Platinum decks their own ratings. Diamond, Master and Grandmaster have only the Forge
rank-against-rank numbers, so every deck in those ranks shares its rank's rating until per-deck Forge
results are added. The scale mixes engines: Diamond is placed against Platinum with Forge games,
Platinum against the lower ranks with built-in games.

| Rank | Mean fitted rating | Band |
| --- | --- | --- |
| Bronze | 900 | below 1000 |
| Silver | 1140 | 1000-1199 |
| Gold | 1251 | 1200-1399 |
| Platinum | 1278 | 1400-1599 |
| Diamond | 1412 | 1600-1799 |
| Master | 1192 | 1800-1999 |
| Grandmaster | 1192 | 2000 and up |

Fitted against observed, rank against rank: Silver vs Bronze 78% (81% observed), Gold vs Silver
65% (67%), Platinum vs Gold 53% (57%), every other row within a point. The built-in rows are not
fully transitive (Platinum beats Bronze less often than Gold does), so no single rating per deck
matches all of them; the gaps are about two standard errors.

Decks whose fitted rating falls outside their rank's band are listed under `out_of_band` in
`ratings.json` and printed by the calibrate command. In this fit: Land Glut (Bronze, rates as
Silver); Boros Burn and Gruul Midrange (Gold, rate as Silver); Esper, Grixis and Mono-White Midrange
(Platinum, rate as Silver) and Mono-Red Aggro (Platinum, rates as Gold); every Diamond deck (rates as
Platinum); and every Master and Grandmaster deck (rate as Silver, because Forge's AI pilots them
worse than Diamond's aggro decks). The deck files have not been moved.

To refit: `python3 -m mtgsim.calibrate` refits from the results stored in `ratings.json`;
`--play N` replays the built-in adjacent-rank pairings first.

Ranks and MMR are internal pool labels and fitted pool ratings, not Arena equivalents or
validated human strength predictions. Pool descriptions and source dates are snapshots,
not claims about today's metagame. Ladder games are main-deck only (no sideboarding or Bo3).
Forge and builtin outcomes both depend on rules implementations and AI pilot limitations.
