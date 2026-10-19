# MTG Simulator

A Magic: The Gathering game simulator. `mtgsim` measures AI-vs-AI outcomes under each simulator's rules and pilot policies.

Plays thousands of AI-vs-AI games between decklists and reports win rates with
sampling uncertainty, split by play/draw when available. Matchups, the ladder and the benchmark
play main-deck games; `mtgsim.sideboard` and `assess --bo3` play best-of-three matches with
sideboarding. Results do not establish human matchup strength.

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

GitHub Actions runs the tests on Python 3.10, 3.13 and 3.14 for every push and pull request
(`.github/workflows/tests.yml`); the card database is rebuilt there once a week and cached. The same
workflow runs pyflakes (`scripts/lint.py`) and, on pull requests, lists every card whose parse differs
from the base branch (`scripts/parse_diff.py`, shown in the job summary).

## Decklists

Plain text as exported by Arena, MTGO or Moxfield: `4 Lightning Bolt`,
`4x Lightning Bolt`, `4 Lightning Bolt (M10) 146`. Pasted tables with section
headings and tab-separated columns also work, and double-faced cards are read
by their front face. A `Sideboard` header (or a
blank line after 60+ cards) ends the main deck; only best-of-three runs use the sideboard.

## Ranks and the ladder

Opponents are grouped into seven ranks under `decks/ranks/`, from Bronze (badly built piles) through
Silver, Gold, Platinum, Diamond and Master to Grandmaster (a dated, curated opponent pool). `--ladder` plays a deck against each rank's pool from the bottom up and
stops at the first rank it fails; a rank is cleared with a win rate of at least 50% against all its
decks together (`--pass-rate` changes that, `--full-ladder` keeps going). On the built-in engine a matchup ends early once
its result is clear (at least 20 games, then a 99.7% interval wholly above or below 50%), which cuts lopsided
pools to a fraction of the games; `--no-early-stop` plays every game. `--rank master diamond`
plays chosen ranks, and `--list-ranks` shows every deck. Use `--engine forge` from Diamond up: the
built-in engine ignores much of those cards' text. `decks/ranks/README.md` says where each list came
from and how the ranks were checked.

## Ranks and MMR

Ranks and MMR are internal scores against these fixed pools, not Arena ranks/MMR,
player skill ratings or calibrated tournament predictions. Pool anchors are assigned,
not inferred from human results. A ladder or rank run uses these labels: Bronze, Silver, Gold, Platinum,
Diamond, Master and Grandmaster, each a 200-point MMR band (Silver starts at 1000, Grandmaster at
2000). Each rank's opponent pool is anchored at the middle of that rank's band (a custom pool not named
after a rank is spread over the bands in order), and the deck's MMR is its
Elo performance rating against everything it has played, so it moves after every game. While the
run goes, the terminal shows the current rank and match progress on one live line, each match ends
with the MMR change, and the run ends with the rank ladder as text. `results/ladder/DECK.html` is
rewritten as the run goes (it reloads itself in a browser until the run finishes) with a rank
badge, the MMR climb over the rank bands and win rates by opponent; `DECK.json` beside it holds
the same data. `--report PATH` writes it elsewhere and `--no-report` skips it.

## Web front end

The engine has no web front end in this repository. `python3 -m mtgsim.browser` still bundles the
engine and the cards of the decks under `decks/` (written to `build/browser/`, or `--out DIR`) for
a page that runs it in the browser with [Pyodide](https://pyodide.org); the page itself lives elsewhere.

## Deck assessment

```
python3 -m mtgsim.assess MY_DECK.txt                     # rank plus four graded criteria
python3 -m mtgsim.assess MY_DECK.txt -n 50 --engine forge --forge-dir ~/forge --json out.json
python3 -m mtgsim.assess MY_DECK.txt --skip-meta --key "Sheoldred, the Apocalypse"
python3 -m mtgsim.assess MY_DECK.txt --bo3 20             # adds the Sideboard criterion
```

Provides heuristic diagnostics, each scored 0 to 100 with an internal grade (S, A, B,
C, D, F):

- **Meta**: simulated score against a dated Standard opponent snapshot, weighted by its recorded meta share
  (`mtgsim/data/metagame.json`, with sources and the date it was read). This sets the MMR and rank:
  the meta field is the Grandmaster pool, reweighted by share before the Elo performance rating.
- **Mana**: Frank Karsten's method. For each coloured spell, the chance of having enough sources of
  its colours to cast it on curve, against his 90% target.
- **Speed**: the average turn the deck kills a goldfish (an opponent who only plays lands).
- **Consistency**: sampled hands with the AI's mulligan rule: mulligans, screw, flood, castable
  plays on turns 1 to 4 and key cards by turn N.
- **Sideboard** (with `--bo3 N`): N best-of-three matches against each meta deck with both sides
  sideboarding after game 1. Reports the meta-weighted match win rate and how much post-board games
  move against game 1 (play and draw compared separately); no change scores 50.

### Best of three and sideboarding

```
python3 -m mtgsim.sideboard MY_DECK.txt OPPONENT.txt -n 50     # Bo3 matches
python3 -m mtgsim.sideboard MY_DECK.txt OPPONENT.txt --plan    # show both sideboard plans
```

Decklists can carry a sideboard (an Arena `Sideboard` heading, an MTGO blank line, `SB:` lines, or a
pasted table with a fourth "Bring in vs." column). Before game 2 each side labels the opponent
aggro, midrange or control and swaps up to six spells with a rule-based plan read from the cards'
rules text: sweepers and cheap removal against aggro, discard and narrow counters against control.
A "Bring in vs." note adds weight. Lands are never swapped and the loser of a game is on the play
next. Decks without a sideboard (all of Bronze to Gold and some Platinum decks) play their main deck
every game.

`mtgsim.assess.assess()` returns the same thing as plain JSON for front ends and reports.
The `--ladder`/`--rank` HTML report show these grades as cards under the rank
(the report's JSON gains an `assessment` key); they reuse the games already played against the
Grandmaster pool and play the rest of the meta field. Turn them off with `--no-grades` or the
page's "Grade the deck" box. In the built-in engine the meta grade is a rough guide, and the page
says so; `--engine forge` gives a trustworthy one.
Refresh `metagame.json` when the metagame moves.

## Run history: compare versions of a deck

Every ladder, rank and assessment run is saved when it finishes, from the command line and the
front-end runs, in `results/history.sqlite3` (set `MTGSIM_HISTORY` for another file, `--no-history` to
skip). A deck's versions are told apart by a fingerprint of its exact main deck, so editing the
list and re-testing it adds version 2, 3 and so on.

    python3 -m mtgsim.history                            # every deck: current and best rank/MMR
    python3 -m mtgsim.history show my_deck               # its versions and every run
    python3 -m mtgsim.history compare my_deck [1 2]      # cards added/removed, MMR, rank and grade changes

Add `--json` for machine-readable output; `mtgsim/history.py` documents the Python API.

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
and again to refresh it (needs network access; the Forge fallback also needs git); the tests need it:

```
python3 -m mtgsim.build_carddb                          # Scryfall bulk data if reachable, else Forge
python3 -m mtgsim.build_carddb --scryfall oracle-cards.jsonl.gz  # a downloaded bulk file
python3 -m mtgsim.build_carddb --forge ~/forge          # a Forge checkout or release
```

The builder reads Scryfall's current bulk metadata to find the download URL. It supports
gzip-compressed JSON Lines and legacy JSON arrays, including local files passed with
`--scryfall` (either format, with or without gzip). Download or parsing failures automatically
fall back to [Forge](https://github.com/Card-Forge/forge)'s card scripts; use `--source scryfall`
to require Scryfall and report a failure instead. The existing database is replaced only after
a successful, nonempty build. Forge's data has no sets or format legality.

Each card's rules text is matched against templates the engine understands.
Text that does not match is ignored and reported. Template coverage helps identify gaps;
it cannot prove correct rules execution or quantify how trustworthy a win rate is.
The [rules architecture audit and implementation plan](results/rules_architecture/README.md)
documents reproduced gaps, Forge integration limits, and a proposed behavior-evidence report.
The first behavior-evidence slice is available separately from template coverage:

```sh
python3 -m mtgsim.behavior_coverage --run --save results/behavior-coverage
python3 -m mtgsim.behavior_coverage --ledger results/behavior-coverage/ledger.json --save results/behavior-review
```

It maps 97 explicit scenarios for identity, events, joint cost planning, transactional
actions, type/color and P/T continuous effects, phase triggers, supported replacements,
removal, graveyard returns, targeting,
the normal legend rule and normal equip
to a versioned [capability catalog](rules/capabilities.json). Reports retain failures,
missing/stale evidence and separate direct card tests from inferred capability evidence.
Use a fresh directory for a new run. Complete card rules support remains unmeasured;
rules outside that scope are unclassified. A source checkout with tests and the offline
database is required. See [the scenario scope](rules/README.md).

`--coverage` reports this per deck without playing: each card is template-matched, simplified (played in a looser way, such as a fetch land cracked as
soon as it enters or an optional extra cost never paid), partly supported (the
ignored text is listed) or unknown. It works on decklists and on whole rank pools
(`--coverage --rank all`). These labels describe template recognition, not verified rules correctness. Use
`--engine forge` for a broader implementation and review both engines' logs.

Measure the entire offline database, including basic lands and cards outside Standard:

```bash
python3 -m mtgsim.database_coverage
python3 -m mtgsim.database_coverage --save results/database_coverage --progress
python3 -m mtgsim.database_coverage --json --top 10
```

The saved report includes totals, a per-card CSV, and missing effects ranked by potential new full matches.
An eligible card must have every ignored line in the listed gap and no recorded simplifications.
Family rankings are upper bounds that overlap; exact-wording rankings group case and whitespace variants
while preserving amounts. Parser failures are counted separately, and the command finishes the census
and saves its results before returning exit code 1. A missing database returns 2. Use `MTGSIM_CARDDB`
to select another local database.

## What the engine covers

- Lands and mana: dual, tapped and conditionally tapped lands, shock lands
  (pay 2 life or enter tapped), fast lands, fetch lands and basic-land
  search, mana creatures, Sol Ring, Treasure
- Targeted land destruction, including nonbasic and opponent-control restrictions
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
- Milling yourself, a target player/opponent, or each player/opponent; recovering
  milled cards by type or subtype to hand, the battlefield, or the library top,
  including multiple cards, cards with Adventures, and tapped battlefield returns;
  conditional rewards for milling matching cards
- Finality and additional +1/+1 counters on battlefield returns (including X paid);
  counters apply as the permanent enters, and finality replaces dying with exile
- Activated graveyard returns with mana, discard and life costs, sorcery timing,
  and delirium/descend-8 restrictions; shared-type mill rewards and repeated
  mill/check/draw processes; discounts for spells that have Adventures
- Creatures with flying, reach, haste, vigilance, defender, menace, trample,
  first strike, double strike, deathtouch, lifelink, hexproof, indestructible,
  "can't be blocked by power 2 or less"
- Swampwalk, forestwalk, mountainwalk, islandwalk and plainswalk against a defending player with the
  corresponding land subtype, including dual lands; flying-only blocking restrictions
- Shroud prevents either player from targeting a permanent, including equip;
  untargeted effects and already attached Equipment and Auras still work
- Fear restricts blocking to black or artifact creatures; horsemanship requires
  a blocker with horsemanship. These restrictions combine with flying and landwalk
- Delayed draws at the beginning of the next turn's upkeep or your next upkeep;
  each draw triggers once, uses the stack, and survives its source leaving play
- Improvise taps untapped artifacts and delve exiles graveyard cards to pay generic
  costs, including X; colored and {C} requirements still need mana. Costs remain
  paid if the spell is countered
- Undying returns a creature that died without +1/+1 counters under its owner's
  control with a +1/+1 counter, provided its card has stayed in the graveyard
- Persist likewise returns creatures that died without -1/-1 counters, with a
  -1/-1 counter. Wither deals creature damage as -1/-1 counters and player damage normally
- Rebound exiles a spell cast from hand as it resolves and offers one free recast
  during your next upkeep. The recast uses fresh targets and does not rebound again
- Storm copies a spell for each earlier spell cast by either player that turn;
  copies are not cast. Cascade exiles to a cheaper nonland card, offers a free cast,
  and puts the other exiled cards on the library bottom in random order
- Shadow restricts both attacking and blocking creatures to those with shadow;
  intimidate restricts blockers to artifact creatures or creatures sharing a color
- Nonbasic and legendary landwalk use the defending player's land supertypes
- Regeneration shields replace destruction, tap the permanent, clear its damage
  and remove it from combat. They expire at cleanup and cannot prevent sacrifice
  or zero toughness. Regeneration-prevention riders on destruction and damage apply
- Learn offers a Lesson from the player's sideboard, discard-then-draw, or neither.
  The CLI supplies sideboards for single games and best-of-three games; the latter
  use the cards left outside the deck after sideboarding. Python callers can pass
  `sideboard=` to `Player` or `sideboard_a=` / `sideboard_b=` to `run_match`.
  The `choose_learn(game, me, lessons)` hook returns `("lesson", card)`,
  `("discard", card)`, or `None`
- Infect deals poison counters to players and -1/-1 counters to creatures, in
  combat and through damage abilities or fights. Devoid makes a card colorless
  while retaining its colored mana requirements. Exalted instances stack when
  exactly one creature attacks; combat predictions include these bonuses and poison
- Proliferate on counter-bearing permanents and players, including repeated
  proliferation, Saga chapters, keyword counters, and poison loss at ten counters.
  The optional `choose_proliferate(game, me)` AI hook returns objects to choose;
  every existing counter type on each chosen object increases together
- Activated abilities in general ("{2}, {T}, Sacrifice this: ..."): mana, tap,
  sacrifice, discard, life and counter costs, "only as a sorcery", "only once
  each turn"; the default policy uses them with spare mana, and self-pumps on
  unblocked attackers
- Mana that can only be spent on some spells (Cavern of Souls, which also makes
  its creature uncounterable; creature-, artifact-, instant/sorcery- and
  Dragon-only mana), "choose a basic land type" lands, lands that enter tapped
  unless you control a basic land / an Equipment / a Plains or an Island, or
  behold a Jace, Clarion Conqueror, "can't block", library searches to hand,
  team pumps and counters on each creature you control
- Equipment: equip costs (and Dwarven Mauler's discount), stat, keyword and ward
  bonuses, falling off when the creature leaves; the default policy equips the
  best creature before combat. Leyline Axe starts on the battlefield.
  Conditional keywords ("as long as you control another Dwarf", "as long as an
  opponent has 10 or less life"), "whenever another Dwarf or Equipment you
  control enters" triggers (also once each turn), filtered "look at the top N"
- Warp (exiled at the end step, cast again from exile later), evoke, "if {U}{U}
  was spent" modes (hybrid costs paid in the colour that turns the mode on),
  offspring, plot, spree, harmonize (as flashback), X costs (X is all the spare
  mana) for X damage and "enters with X +1/+1 counters". Warp and evoke are only
  offered when the full cost can't be paid.
- Map (explore), Lander and Food tokens, "its controller creates Map tokens /
  may search for a basic land" (Get Lost, Erode), exile until this leaves the
  battlefield (Seam Rip, Pinnacle Starcage), graveyard triggers that return the
  card (Bloodghast) and "exile this card from your graveyard" abilities, damage
  equal to the number of Treasures/artifacts/creatures/lands you control
- Lifegain: "whenever you gain life" triggers and "if you gained life / gained
  3 or more life / gained and lost life this turn" conditions; "Ward—Pay N
  life"; "whenever you attack (with Lizards)", "whenever a creature you control
  attacks", "whenever you cast a Lizard spell", "enters or leaves the
  battlefield" triggers; named tokens; "put up to two noncreature permanents
  from the top seven onto the battlefield"
- Sacrifice: "whenever you sacrifice an artifact / a token" triggers and "as an
  additional cost, (pay {4} or) sacrifice an artifact or creature"; stun counters
  on a tapped creature; "can't be blocked this turn"; earthbend (the land stays a
  creature, but does not return when it dies); extra land drops and lands from
  the graveyard; affinity; quest counters with "when you do, if it has four or
  more"; tokens that get +1/+1 for each artifact you control
- Reanimator and Dimir staples: "mill N, you may put a permanent card from among
  them into your hand", "discard a card, if you do search for a creature",
  impending, "return a creature card from your graveyard to your hand", stun
  counters per discarded nonland card, "deals damage equal to that creature's
  power", shuffling a stunned creature away, Enduring creatures returning as
  enchantments, edicts that exile, Bringer of the Last Gift's mass swap, lands
  that become creatures for good. Terror of the Peaks' life tax is played as
  ward (pay 3 life); face-down permanents aren't modelled.
- Craft with artifact (exiles an artifact card from the graveyard, else an
  artifact token, else the cheapest other artifact, then returns the card
  transformed); Station (charge counters from tapping another creature; the
  default policy only stations when a parsed ability needs the charge);
  "enters with N net counters"; "draw a card for each artifact you control";
  "put ~ into its owner's library third from the top"
- London mulligan, drawing from an empty library, hand size, 60-turn cap

Not yet: auras, equipment tokens and attaching equipment by effects (Thorin), X in
anything but damage and +1/+1 counters, copy effects (Reflection of Kiki-Jiki),
casualty (never paid), day/night, Old-Growth Troll's return. Modal double-faced cards keep their land face in
`CardDef.land_face`, played with `Game.play_land(p, card, back=True)`.
Builtin runs report known coverage gaps; this is not an exhaustive rules audit.

Logged games (`--log`, or `run_match(log_game=...)`) also carry machine-readable
`AUDIT {json}` lines: `start` (players in play order, starting life, `turn_unit`
`player-turn`), `mulligan` and `keep` with the hand, every life change with
`before`/`delta`/`after` and its cause, `loss` with its cause, and `result` with the
winner, final life and player-turns. `seat` is the index in play order (0 went first).
`tests/test_audit.py` rebuilds each life total from these lines and checks the result.

### How AIs plug in

The AI class makes the main decisions (mulligans, main phase, attacks, blocks,
`respond` when it has priority). Everything else goes through optional hooks;
an AI that doesn't define one gets the default policy of the same name in
`mtgsim/engine/policy.py`:

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
| `mtgsim/cards/` | Card model (`model.py`), oracle-text templates (`patterns.py`), Scryfall JSON to `CardDef` (`parse.py`), tokens (`tokens.py`) |
| `mtgsim/removal.py`, `copies.py`, `auras.py`, ... | Template modules: one mechanic family each, joined to the tables in `cards/` |
| `mtgsim/carddb.py` | Card lookup and Scryfall fetch/cache |
| `mtgsim/build_carddb.py` | Builds `data/cards.sqlite3` from Scryfall bulk data or Forge |
| `mtgsim/decklist.py` | Decklist parsing |
| `mtgsim/engine/` | The rules engine: objects (`state.py`), mana payment (`mana.py`), the `Game` class (`game.py`) built from costs, targets, turns, stack, play, abilities, battlefield, resolve, effects and combat modules, effect-kind handlers (`kinds/`), and the default decisions (`policy.py`) |
| `mtgsim/identity.py`, `rules_events.py`, `continuous.py`, `actions.py` | Rules foundation: card identities and zones, rules events, scoped continuous effects, transactional actions |
| `mtgsim/ai.py` | `HeuristicAI` (default) and `BaselineAI` (the first, simpler player, kept for comparison) |
| `mtgsim/runner.py` | Match loop, statistics |
| `mtgsim/ranks.py` | Ranks and the ladder (`decks/ranks/`); `tiers.py` is its old name |
| `mtgsim/rating.py` | MMR, ranks and `LadderTracker` (live state of a ladder run, as JSON) |
| `mtgsim/ladder_report.py` | Live terminal line, text summary and HTML report of a ladder run |
| `mtgsim/forge.py` | Forge mode: .dck export, running Forge's `sim`, parsing results |
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

## Forge mode: broader rules coverage

`--engine forge` plays the games in [Forge](https://github.com/Card-Forge/forge),
an open-source (GPL-3) Java rules engine with broader card support and its own AI.
Forge is an independent comparison tool, not a ground-truth oracle: card scripts, rules
and pilot decisions can be wrong. Agreement between engines does not validate human win rates.

Setup (needs git, a JDK 17+ including `javac`, and Maven; about 1.5 GB):

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
- Forge has no option to choose who starts: the first game of a run is a coin flip and the
  loser of each game starts the next (107 of 107 cases in worker logs checked in October 2026).
  Left alone, a deck that loses most games would mostly be on the play, pulling every win rate
  toward 50%. The wrapper therefore runs Forge with its full game log, reads each game's
  starter from turn 1 of its `Turn: Turn N (Ai(k)-deck)` lines, and keeps only as many games
  of each starter as an even split needs, discarding the rest and stopping Forge once both
  halves are full. Which games are kept depends only on who started them, never on their own
  result. An unbroken 1..N turn sequence that matches `Game Outcome: Turn` also gives each
  game's length in player-turns.
- Discarded games cost time: when one deck wins a share p of games, about `n/2 / (1 - p)`
  games are played to fill its on-the-play half (twice as many as asked at 75%). Each worker
  plays at most 4 times its share; past that it keeps the remaining games whatever their
  starter, and the on-the-play/on-the-draw line in the output shows the skew. Games whose
  starter can't be read are discarded the same way.
  Close matchups, where play/draw matters most, always get an exact split. In a 12-game check
  (October 2026) of a Diamond deck against a Bronze one, which won 11 of 12, the cap was reached
  and the split was 2 on the play and 10 on the draw; Forge's own order put the winner on the
  play in 2 of 48 games.
- `sim` mode can play a best-of-three (`-m 3`), but it never turns on AI sideboarding, so all
  three games use the main deck, and one process plays only one match. Sideboarded best-of-three
  is not available through Forge's `sim`.
- About 3 to 4 seconds per game on a 4-core machine. `--jobs` runs several
  Java processes, which helps most on machines with more cores.
- `--clock` (default 120 s) calls a stuck game a draw. Forge can also emit draws
  after internal errors; inspect raw logs before interpreting them. The wrapper rejects
  unknown winners, duplicate/malformed results, nonzero exits and incomplete counts.
- Win rates reflect Forge's AI piloting both decks. It plays control and
  combo decks less well than a strong human.

`decks/forge/` has three opponents that use real, modern cards
(mono-red aggro, mono-green stompy, Rakdos midrange).


## Trust-validation benchmark

```
python3 -m mtgsim.benchmark --engine builtin -n 20 --out results/benchmark-builtin
python3 -m mtgsim.benchmark --engine forge --forge-dir ~/forge -n 20 --out results/benchmark-forge
python3 -m mtgsim.benchmark --engine both --forge-dir ~/forge -n 2 --clock 10 --worker-timeout 90 --out results/benchmark-smoke
```

The curated [manifest](benchmarks/small.json) references three existing aggro, midrange
and control fixtures and runs their three pairings. These are mixed-pool diagnostic lists;
comments in the original deck files do not certify format legality or tournament provenance.
Combo coverage is one compact curated fixture, `decks/combo/kiln_fiend_strobe.txt`
(Kiln Fiend plus double-strike spells; not a tournament list); copy-effect combos are
not covered. **No applicable human matchup rates are supplied.** Popularity and
BO3 tournament match rates cannot substitute for main-deck game outcomes.

`report.md` reports W/L/D, A's actual win probability with a 95% Wilson interval (draws are
non-wins), and score with half-credit for draws separately. Intervals capture sampling
uncertainty assuming independent games, not rules or pilot bias. The report gives coverage
details, missing evidence, descriptive engine gaps and a manual log-review procedure.
A few games only check the workflow; they cannot validate matchup accuracy. Builtin alternates
play/draw, with A starting first; Forge play/draw is observed per game (see Forge mode) and
reported as W–L–D on the play and on the draw, with unknowns counted separately. Turn units are
player-turns for both engines. Seeds are engine-specific, not paired games.
Both pilots can struggle with control and combo. Forge draws can include timeouts or errors.

`results.json` checkpoints each completed pairing/engine and records the manifest, deck bytes
and parsed main decks, all Python engine/module code, effective local card database/cache,
Python/platform, seed and run settings. Forge identity also includes jar bytes, all resource
names/contents (including symlink targets), Java executable/version/flags, jobs and clock.
Benchmark and crosscheck Forge workers use **fresh default preferences and isolated homes**;
installed/user preferences and inherited Java option variables are deliberately excluded.
`--worker-timeout` bounds each benchmark Java process including startup; by default the wrapper
allows 60 seconds startup plus `(clock + 5) * worker_games` seconds.

Builtin game logs (`--builtin-logs first`, the default, or `all`, written one game at a time)
and full Forge raw worker logs are kept in unique attempt directories,
including failed attempts. Checkpoints are atomic and an exclusive `.run.lock` prevents concurrent
writers; after a hard kill, remove that lock only after checking that its process has stopped.
Repeat the identical command to resume. Completed results are reused only when the complete
identity and result/log hashes match; changed inputs/settings require a **new `--out` directory**.
The final check rejects inputs changed during the run. Keep inputs immutable during experiments.
Changing `-n` starts a new experiment; it does not append games to the old sample.

`python3 -m mtgsim.crosscheck` retains the larger diagnostic suite, now with content-based
resume checks too. It refuses legacy caches without provenance or changed inputs; choose a new
`--out`, or explicitly use `--rerun` to replace the checkpoint. Its fractional-draw z statistics
are approximate review prompts, not evidence that a difference is beyond chance. Use the small
benchmark for clearer uncertainty and evidence reporting.

A custom manifest may add human evidence only after source review: each entry must identify
`matchup`, `unit: "main_deck_game"`, exact ordered `deck_sha256`, `source_url`, `event`, `format`,
`date`, `applicability`, `reviewed_by`, and integer `wins_a`, `wins_b`, `draws`. Describe why the
format, lists, first-player distribution and game conditions apply. The loader checks structure
and exact deck hashes; it cannot verify a source's truth or a curator's applicability judgment.
Never enter inferred BO3-to-game conversions or invented rates. Leave `human_evidence` empty
and explain the missing data when applicable sources are unavailable.
