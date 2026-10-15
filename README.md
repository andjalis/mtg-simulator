# MTG Simulator

A Magic: The Gathering game simulator. `mtgsim` simulates Magic games to measure deck strength.

Plays thousands of AI-vs-AI games between decklists and reports win rates with
95% confidence intervals, split by play/draw.

```
python3 -m mtgsim.build_carddb                  # once after cloning: builds the card database
python3 -m mtgsim decks/mono_red_aggro.txt decks/green_stompy.txt -n 1000
python3 -m mtgsim decks/orzhov_midrange.txt --gauntlet decks/mono_red_aggro.txt decks/green_stompy.txt
python3 -m mtgsim --round-robin decks/*.txt -n 1000 --seed 7
python3 -m mtgsim A.txt B.txt -n 1 --log        # watch one game play out
python3 -m mtgsim decks/ub_snow_control.txt --coverage   # which cards the engine can't fully play
python3 -m mtgsim decks/ub_snow_control.txt --ladder --engine forge --forge-dir ~/forge   # climb the ranks
python3 -m unittest discover -s tests -t .       # tests
```

Needs only Python 3.10+, no packages.

GitHub Actions runs the tests on Python 3.10 and 3.13 for every push and pull request
(`.github/workflows/tests.yml`); the card database is rebuilt there once a week and cached.

## Decklists

Plain text as exported by Arena, MTGO or Moxfield: `4 Lightning Bolt`,
`4x Lightning Bolt`, `4 Lightning Bolt (M10) 146`. Pasted tables with section
headings and tab-separated columns also work, and double-faced cards are read
by their front face. A `Sideboard` header (or a
blank line after 60+ cards) ends the main deck; the sideboard is ignored.

## Ranks and the ladder

Opponents are grouped into seven ranks under `decks/ranks/`, from Bronze (badly built piles) through
Silver, Gold, Platinum, Diamond and Master to Grandmaster (the most-played, best-performing current
Standard tournament decks). `--ladder` plays a deck against each rank's pool from the bottom up and
stops at the first rank it fails; a rank is cleared with a win rate of at least 50% against all its
decks together (`--pass-rate` changes that, `--full-ladder` keeps going). `--rank master diamond`
plays chosen ranks, and `--list-ranks` shows every deck. Use `--engine forge` from Diamond up: the
built-in engine ignores much of those cards' text. `decks/ranks/README.md` says where each list came
from and how the ranks were checked.

## Ranks and MMR

A ladder or tier run also rates the deck like a ranked queue: Bronze, Silver, Gold, Platinum,
Diamond, Master and Grandmaster, each a 200-point MMR band (Silver starts at 1000, Grandmaster at
2000). Each rank's opponent pool is anchored at the middle of that rank's band (a custom pool not named
after a rank is spread over the bands in order), and the deck's MMR is its
Elo performance rating against everything it has played, so it moves after every game. While the
run goes, the terminal shows the current rank and match progress on one live line, each match ends
with the MMR change, and the run ends with the rank ladder as text. `results/ladder/DECK.html` is
rewritten as the run goes (it reloads itself in a browser until the run finishes) with a rank
badge, the MMR climb over the rank bands and win rates by opponent; `DECK.json` beside it holds
the same data. `--report PATH` writes it elsewhere and `--no-report` skips it.

## Web page

```
python3 -m web            # then open http://127.0.0.1:8000
```

Paste a decklist, pick the full climb or chosen ranks and the number of games per opponent,
and the page shows how far the deck climbs and each rank's win rate with its 95% confidence
interval; click a rank for every opponent's record, play/draw split and game length. It checks the list
as you type and flags unknown cards and cards the engine only partly simulates. Above the results it shows the deck's rank, MMR and MMR chart
(see Ranks and MMR) as games finish. Games run in
the built-in engine on every CPU core (`--jobs N` to limit, `--port`, `--host`, `--offline`).
Standard library only, like the rest of the simulator.

## Deck assessment

```
python3 -m mtgsim.assess MY_DECK.txt                     # rank plus four graded criteria
python3 -m mtgsim.assess MY_DECK.txt -n 50 --engine forge --forge-dir ~/forge --json out.json
python3 -m mtgsim.assess MY_DECK.txt --skip-meta --key "Sheoldred, the Apocalypse"
```

Rates a deck on the criteria competitive players use, each scored 0 to 100 with a grade (S, A, B,
C, D, F):

- **Meta**: win rate against the top Standard decks, each weighted by its tournament meta share
  (`mtgsim/data/metagame.json`, with sources and the date it was read). This sets the MMR and rank:
  the meta field is the Grandmaster pool, reweighted by share before the Elo performance rating.
- **Mana**: Frank Karsten's method. For each coloured spell, the chance of having enough sources of
  its colours to cast it on curve, against his 90% target.
- **Speed**: the average turn the deck kills a goldfish (an opponent who only plays lands).
- **Consistency**: sampled hands with the AI's mulligan rule: mulligans, screw, flood, castable
  plays on turns 1 to 4 and key cards by turn N.

`mtgsim.assess.assess()` returns the same thing as plain JSON for the web page and reports.
Refresh `metagame.json` when the metagame moves.

## Card data

Every Magic card (about 34,000) is in `mtgsim/data/cards.sqlite3`, an offline
database with name, mana cost, mana value, type line, Oracle text,
power/toughness, loyalty, colors, color identity, keywords, layout and card
faces. Names match regardless of case or accents, and a face name such as
`Stomp` finds `Bonecrusher Giant // Stomp`. Lookup order: the sample cards in
`mtgsim/data/builtin_cards.json`, a local cache at `~/.cache/mtgsim/cards.json`
(`MTGSIM_CACHE`), the database (`MTGSIM_CARDDB` points at another copy), then
the Scryfall API. `--offline` skips Scryfall.

The database (about 27 MB) is not checked in to git. Build it once after cloning,
and again to refresh it (about 20 seconds, needs git); the tests need it:

```
python3 -m mtgsim.build_carddb                          # Scryfall bulk data if reachable, else Forge
python3 -m mtgsim.build_carddb --scryfall oracle-cards.json   # a Scryfall bulk file you downloaded
python3 -m mtgsim.build_carddb --forge ~/forge          # a Forge checkout or release
```

The current copy was built from [Forge](https://github.com/Card-Forge/forge)'s
card scripts, because Scryfall and MTGJSON are blocked where it was built.
Forge's data has no sets or format legality.

Each card's rules text is matched against templates the engine understands.
Text that doesn't match is ignored, and the run prints exactly which cards are
only partially simulated, so you know how far to trust a result.

`--coverage` reports this per deck without playing: each card is fully
supported, simplified (played in a looser way, such as a fetch land cracked as
soon as it enters or an optional extra cost never paid), partly supported (the
ignored text is listed) or unknown. It works on decklists and on whole tiers
(`--coverage --tier all`). The trash, beginner and advanced tiers and the
semi-pro mono red and Azorius lists are fully playable; the pro tier is about
30 to 65% playable, so use `--engine forge` there.

## What the engine covers

- Lands and mana: dual, tapped and conditionally tapped lands, shock lands
  (pay 2 life or enter tapped), fast lands, fetch lands and basic-land
  search, mana creatures, Sol Ring, Treasure
- The stack with priority passing: both players can respond to every spell and
  trigger, and get priority with an empty stack in the declare attackers,
  declare blockers and end steps. Counterspells (including "unless its
  controller pays {N}", creature/noncreature filters, "can't be countered"),
  instant-speed removal, flash creatures and flash planeswalkers
- Triggered abilities: enters, attacks, dies, combat damage to a player,
  "whenever you cast" (prowess, Eidolon, Hullbreaker Horror's modes),
  "whenever you draw" / "an opponent draws" (Sheoldred), landfall, upkeep, end
  step, "another creature enters or dies", "becomes the target of a spell",
  ward (mana or discard)
- Sagas (lore counters, chapters, transforming), planeswalkers (loyalty
  abilities, The Wandering Emperor at instant speed, attacking and burning
  them), creature and artifact tokens (Treasure, Clue, Blood), +1/+1 counters,
  transforming cards (Wedding Announcement), anthems
- Modal spells ("choose one / two"), adventures, flashback, foretell,
  spectacle, blitz (also from the graveyard), channel lands, alternative costs
  (Baleful Mastery), cost reductions (Tolarian Terror, Ghalta), snow mana for
  Blood on the Snow's return
- Manlands (Hall of Storm Giants, Den of the Bugbear, Crawling Barrens) and
  vehicles with crew
- Kicker (Burst Lightning), additional life costs (Bitter Triumph), devotion
  drain (Gray Merchant), stun counters and tapping, mill, -1/-1 counters
  (Soul-Scar Mage), "enters with +1/+1 counters" and doubling them,
  Duress, Spell Snare, Goblin Guide's drawback
- Burn, removal with restrictions (mana value, tapped, attacking, nonartifact;
  creature-type restrictions like "non-Dragon" are ignored), bounce, discard
  (Thoughtseize), card draw, scry, surveil, "look at the top N", rummaging,
  life gain/loss/drain, pump tricks, -N/-N effects, board wipes
- Creatures with flying, reach, haste, vigilance, defender, menace, trample,
  first strike, double strike, deathtouch, lifelink, hexproof, indestructible,
  "can't be blocked by power 2 or less"
- London mulligan, drawing from an empty library, hand size, 60-turn cap

Not yet: auras and equipment, X spells, copy effects (Reflection of
Kiki-Jiki), casualty (never paid), day/night, Old-Growth Troll's return, Map
tokens, spree, warp. Modal double-faced cards keep their land face in
`CardDef.land_face`, played with `Game.play_land(p, card, back=True)`.
Every run lists the text it ignores.

### How AIs plug in

The AI class makes the main decisions (mulligans, main phase, attacks, blocks,
`respond` when it has priority). Everything else goes through optional hooks;
an AI that doesn't define one gets the default policy of the same name in
`engine.py`:

| Hook | Default |
| --- | --- |
| `respond(game, me)` | Counter spells worth about 3 mana, save creatures with hexproof tricks, kill attackers, use mana at the opponent's end step. Returns `(card, targets)`, `("loyalty", pw, index)`, `("activate", perm, what)` or `None` |
| `respond_extras(game, me)` | Runs when the AI's own `respond` passes: The Wandering Emperor, Clues, flashback/adventure/modal instants at the opponent's end step |
| `use_abilities(game, me)` | After each main phase: loyalty abilities, Bloodtithe Harvester, Blood tokens, foretell, spells from other zones and modal sorceries the AI skipped |
| `before_attacks(game, me)` | Crew vehicles, animate manlands with spare mana |
| `choose_attack_targets(game, me, attackers)` | Send attackers at planeswalkers unless the player is dead on board |
| `choose_target(game, me, effect)` | Best legal target (respects hexproof and restrictions) |
| `choose_modes(game, me, modes, n, up_to)` | The n most valuable modes |
| `scry`, `choose_dig`, `choose_rummage`, `choose_discard_from`, `choose_crew`, `pay_unless`, `pay_optional`, `pay_shock` | Simple heuristics |

Useful state and helpers: `game.stack` (top is `stack[-1]`; items have
`controller`, `card`, `effects`, `targets`, `kind`), `game.step`,
`game.active`, `game.attackers`, `game.spell_options(p)` (hand cards plus
adventures, flashback, foretold cards, blitz, channel; cast them with
`game.cast`), `game.can_cast_now(p, card)`, `game.cost_of(p, card)`,
`game.legal_targets(p, effect)`, `game.targetable(obj, p)`,
`engine.default_choose_target(game, p, effect)`.

## Layout

| File | Role |
| --- | --- |
| `mtgsim/cards.py` | Scryfall JSON to `CardDef`; oracle-text templates |
| `mtgsim/carddb.py` | Card lookup and Scryfall fetch/cache |
| `mtgsim/build_carddb.py` | Builds `data/cards.sqlite3` from Scryfall bulk data or Forge |
| `mtgsim/decklist.py` | Decklist parsing |
| `mtgsim/engine.py` | Game state, turns, the stack and priority, triggers, combat, default response policy |
| `mtgsim/ai.py` | `HeuristicAI` (default) and `BaselineAI` (the first, simpler player, kept for comparison) |
| `mtgsim/runner.py` | Match loop, statistics |
| `mtgsim/ranks.py` | Ranks and the ladder (`decks/ranks/`); `tiers.py` is its old name |
| `mtgsim/rating.py` | MMR, ranks and `LadderTracker` (live state of a ladder run, as JSON) |
| `mtgsim/ladder_report.py` | Live terminal line, text summary and HTML report of a ladder run |
| `mtgsim/forge.py` | Forge mode: .dck export, running Forge's `sim`, parsing results |
| `web/` | The web page: `server.py` (HTTP API), `sim.py` (runs ranks in a process pool), `static/index.html` |
| `decks/` | Sample decklists and the rank pools |
| `results/` | Saved test runs, such as `results/ub_snow_control/` |
| `AI_RESULTS.md` | Measurements of the AI against the baseline player |

The AI is a separate class, so a stronger player (lookahead or Monte Carlo
search) can be dropped in and compared against the heuristic one.

## Results reflect the AI as well as the deck

Win rates measure "this deck piloted by this AI". Simple AIs favour
straightforward decks (big creatures) over decks that need careful play.

`HeuristicAI` scores decisions with one evaluation: life on a concave scale
(the last points matter most; burn in hand counts towards the opponent's) plus
the value of creatures in play. It picks attacks by simulating each attack set
against the blocks the defender would make and checking the crack-back, finds
blocks (including double blocks and chumps) by local search over the same
combat model, spends mana on the combination of spells that uses it best, holds
instants for the opponent's turn (removal on attackers, counters on real
threats, burn and card draw at their end step, pump spells to save a creature
or win a block) and keeps counter mana up. `AI_RESULTS.md` has before/after
numbers against `BaselineAI`.

## Forge mode: full card coverage

`--engine forge` plays the games in [Forge](https://github.com/Card-Forge/forge),
an open-source (GPL-3) Java rules engine that implements nearly every card and
has its own AI. Use it for real decks; use the built-in engine for fast
what-if runs on simple cards.

Setup (needs git, Java 17+ and Maven; a few minutes, about 1.5 GB):

```
scripts/install_forge.sh ~/forge
```

or unpack a release from the Forge GitHub page. Then:

```
python3 -m mtgsim decks/ub_snow_control.txt decks/forge/rakdos_midrange.txt \
    --engine forge --forge-dir ~/forge -n 100 --jobs 4
python3 -m mtgsim decks/ub_snow_control.txt --gauntlet decks/forge/*.txt --engine forge --forge-dir ~/forge
```

Setting `FORGE_HOME` replaces `--forge-dir`. Gauntlet and round-robin work as
with the built-in engine.

- Every card name is checked against Forge's card list first, so typos fail
  loudly instead of Forge quietly playing a short deck.
- Forge doesn't report who played first or game length, so those lines are
  left out of the summary.
- About 3 to 4 seconds per game on a 4-core machine. `--jobs` runs several
  Java processes, which helps most on machines with more cores.
- `--clock` (default 120 s) calls a stuck game a draw.
- Win rates reflect Forge's AI piloting both decks. It plays control and
  combo decks less well than a strong human.

`decks/forge/` has three opponents that use real, modern cards
(mono-red aggro, mono-green stompy, Rakdos midrange).
