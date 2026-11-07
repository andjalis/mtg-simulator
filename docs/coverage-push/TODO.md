# Coverage push: to-do list

Snapshot 2026-11-06 22:15 UTC. How the push works: [README.md](README.md). Bugs and follow-ups are GitHub issues
(labels `counted-full-but-wrong`, `follow-up`, `parked`, `lane:<name>`); this file is the overview plus the work
that isn't an issue.

## 1. Resume the team (after a pause, a reboot or a new lead session)

1. `cd ~/mtg-simulator && git checkout main && git pull --ff-only`; check that the nightly run on main is green.
   The briefs, plans and handoff notes in this folder are the source of truth (not the local copy): replace
   `~/mtg-worktrees/briefs` with a link to `~/mtg-simulator/docs/coverage-push` (keep `lists/` local; it is
   regenerated), and have the lead commit brief and status changes back here in small docs PRs.
2. Restart the local gate workers (see README "Tools") and check `~/mtg-worktrees/gate.log`.
3. List open PRs (`gh pr list`) and issues; approved PRs carry `lead-approved`. Run
   `~/mtg-worktrees/bin/merge_batch.sh` for a batch (it runs a census after merging).
4. Start agents again as herdr panes in their worktrees (`herdr agent start sim-<lane> --kind claude --pane <id>
   -- --model opus|sonnet --permission-mode auto`) with the prompt "Read briefs/COMMON.md and briefs/<lane>.md and
   follow them". Briefs: `~/mtg-worktrees/briefs/` (copies in [briefs/](briefs/)). Each agent first merges
   origin/main into its branches and answers open review comments on its PRs.
5. Ping sim-audit after each batch with the merged PR numbers.

## 2. Lead to-dos

- [ ] Merge the approved backlog in batches as gates pass; keep stacked PRs in order (oldest first).
- [ ] After each batch: census, update the table in README.md, ping sim-audit, refresh `briefs/lists/units-latest.csv`.
- [ ] Update `BACKLOG.md` (link this folder and the issues; retire clauses fixed by the push).
- [ ] Owner action: edit `.github/workflows/tests.yml`: `push: branches: [main]` plus a `concurrency` group with
      `cancel-in-progress: true` (halves CI load; needs the repo owner because of the workflow scope).
- [ ] Owner action (recommended): a fine-grained token limited to andjalis/mtg-simulator for the agent team.
- [ ] Re-enable the GitHub "Pilot gate" workflow only if the local gate is retired.
- [ ] If sim-review2 stays the bottleneck (the grammar stack is 9+ PRs deep), add a third reviewer for it.
- [ ] Track the audit error rate per batch (first audit: 9 of 33 sampled cards wrong); it should fall.
- [ ] When a lane's list runs low, move its agent to the biggest open family (section 5).

## 3. Open PRs (53 at the snapshot; "(approved)" = lead-approved)

- #262 [claude/mech-9] Splice: several cards onto one Arcane spell
- #242 [claude/abil-7] One damage sentence in general: selector targets, source relations, qu
- #241 [claude/gzones-2] Library destinations: tucks stop passing through the graveyard; gramma
- #240 [claude/mech-8] Bestowed Aura keeps the card's activated abilities
- #239 [claude/gcond-2] Condition riders: casting facts, referents, 'instead'; ETB/landfall 'i
- #238 [claude/static-6] Attack and block restrictions with a condition ('can't attack/block un
- #237 [claude/grammar-12] Grammar prohibition family: <players> can't cast <spell description> [
- #236 [claude/grammar-11] Grammar land-type family: <land> becomes a Swamp [in addition] [until 
- #235 [claude/mech-7] Rooms: cast either half, unlock the other door
- #234 [claude/simplify-9] Tap-locks as a persistent link, not one skipped untap
- #233 [claude/grammar-10] Grammar control family: gain control of <np> [until end of turn], unta
- #232 [claude/gzones-3] Removal wordings: stop swallowing qualifiers, exile no longer destroys
- #231 [claude/grammar-9] Grammar tap family: tap / untap / tap or untap, doesn't untap during (
- #230 [claude/static-5] A colour chosen as a permanent enters: Gates, Thriving lands, protecti
- #229 [claude/grammar-8] Grammar evasion family + static family rules (can't be blocked by / ex
- #228 [claude/gzones-1b] Grammar zones family: destroy / exile / bounce objects and player edic
- #227 [claude/simplify-8] Backup grants every ability listed below it
- #226 [claude/grammar-6] Grammar animation family: becomes [N/N] [colours] [subtypes] [types] c
- #225 [claude/simplify-7] Wordings: keep the 'an opponent controls' restriction on targets (approved)
- #224 [claude/static-4] Damage modifiers over a source filter and a recipient filter (double /
- #223 [claude/simplify-6] Mana: counted amounts and enchanted-land extra mana in its own colours
- #222 [claude/grammar-7] AI plays grammar effects: @ai_value group/player values, threaten, dis
- #221 [claude/trig-4] Attack-with heads, Aura upkeep-of-controller heads, attackers cleared 
- #220 [claude/static-anthem-fix] Fix: anthem group words read as colours, card types, states and singul
- #219 [claude/mech-6] Spacecraft are artifact creatures once charged
- #218 [claude/mech-5] Prepared self targets, hexproof from a colour
- #217 [claude/counters-4] Counters: enters with / put counters equal to a quantity or for each t
- #216 [claude/abil-5] Fix: bare '{T}: Add two mana of any one color' lines produced nothing 
- #215 [claude/gcond-1b] Grammar quantities: devotion, noun-phrase counts, turn history, greate
- #214 [claude/abil-4] Restricted mana in general, restricted pool mana, X / different / comb
- #213 [claude/static-3] Static damage prevention over a source filter and protected subjects
- #212 [claude/abil-3] Graveyard returns: sacrifice costs, activation restrictions, counters 
- #211 [claude/tokens-5] Token counts (devotion, previous object's stats, count first) and defi
- #210 [claude/mech-4] Freerunning, Prowl, Web-slinging, Beam me up, Reinforce, Recover
- #209 [claude/mech-fix-nocost] Cards with no printed mana cost can't be cast normally from hand
- #208 [claude/gplayers-2] Grammar player verbs: imperative draw/discard chains, random and whole
- #207 [claude/grammar-5] Pluggable grammar: verb registry, family modules, GRAMMAR.md
- #205 [claude/tokens-4] Token subjects 'they / that player' and token choices
- #204 [claude/tokens-3] Tokens that are copies of that creature / it
- #203 [claude/tokens-2] Token riders: end-of-combat / end-step removal, keywords until end of 
- #202 [claude/grammar-4] Grammar quantities: 'for each <thing>' and 'where X is' scale grammar 
- #201 [claude/trig-3] Trigger events: surveil, explores, coin flip, life loss, player damage
- #200 [claude/simplify-4] Unearth as an activated ability from the graveyard
- #199 [claude/simplify-3] Target player draws/gains/loses: a real player target
- #198 [claude/trig-2] Delayed 'when that creature dies this turn' watcher
- #197 [claude/gplayers-1b] Grammar damage verbs: <source> deals N damage to <recipient>
- #196 [claude/simplify-2] Madness: exile on discard, cast for the madness cost
- #195 [claude/static-2] Devotion and most-common-color conditions, devotion quantity, ~ isn't 
- #194 [claude/counters-3] Counters: distribute, remove, move counters; him/her as the card itsel
- #193 [claude/grammar-3] Grammar: target-player AI fix (#189 follow-up), player subjects, stati
- #192 [claude/counters-2] Counters: per-counter amounts (pump/draw/life/damage for each X counte
- #191 [claude/tokens-1] Token descriptions as a general sub-grammar (cx_tokens) (approved)
- #190 [claude/counters-1] Counters: each of up to N targets, X-entry for any counter kind, poiso (approved)

## 4. Open issues at the snapshot

- #282 Wordings drop 'up to one' (target becomes mandatory) and a controller qualifier combined with another filter (counted-full-but-wrong, lane:simplify)
- #281 Wordings drop 'an opponent controls' from targets: Faebloom Trick can tap your own creature (counted-full-but-wrong, lane:simplify)
- #280 Grammar fallback strips 'you may have', making the effect mandatory (follow-up, lane:grammar)
- #279 Evermind (no printed mana cost) can be cast from hand for {0} (counted-full-but-wrong, lane:mech)
- #278 Explore with an empty library does nothing (follow-up, lane:mech)
- #277 HeuristicAI never casts group effects, set-base effects and threaten spells (follow-up, lane:grammar)
- #276 Splice / cost variants clear the Arcane spell's own cost_reduction (follow-up, lane:mech)
- #275 AI picks the same object for every 'two / up to N target' effect, and the engine accepts it (counted-full-but-wrong, lane:grammar)
- #274 Bestowed Aura drops the card's triggered abilities (follow-up, lane:mech)
- #273 Group effects with 'where X is' use 1 instead of X (Overwhelming Stampede, Jolrael, Firebird, Cultivator of Blades) (counted-full-but-wrong, lane:grammar)
- #272 Tap-lock: own source and locked target untapping in the same step depends on list order (follow-up, lane:simplify)
- #271 Backup grants all of the source's triggered/activated abilities, not only those below the keyword (parked, lane:simplify)
- #270 Hexproof from <colour> reads printed colours, not colour-changing effects (follow-up, lane:mech)
- #269 Devotion counts hybrid symbols only as their first colour (follow-up, lane:tokens)
- #268 Recover / Beam me up always pay; Beam bounces the cheapest creature (may be a token); Reinforce isn't a discard (follow-up, lane:mech)
- #267 Divided damage: a player target that becomes illegal still takes its share (follow-up, lane:simplify)
- #266 Activated-ability bans (Pithing Needle, Linvala) should apply to channel/unearth ability variants (follow-up, lane:simplify)
- #265 Madness is always cast when possible (optional), and cleanup settles triggers before damage removal (follow-up, lane:simplify)
- #264 Day/night edge rules: nightbound entering with neither, extra turns, transform only via day/night (follow-up, lane:simplify)
- #263 Cost modifiers: increases are applied after the older reductions, not before (601.2f) (follow-up, lane:static)
- #261 Warstorm Surge: 'it deals damage equal to its power' uses the enchantment's power (0), not the entering creature's (counted-full-but-wrong, lane:gplayers)
- #260 Compound split makes the caster do the second verb of 'Target player <A> and <B>' (mills/draws/loses life) (counted-full-but-wrong, lane:simplify)
- #259 Chosen-colour anthems: 'Creatures you control of the chosen color get +N/+N' (follow-up, lane:static)
- #258 cost_of: apply all cost increases before all reductions (601.2f) (follow-up, lane:static)
- #257 Remove/move counters drop 'you may': the AI always does it (follow-up, lane:counters)
- #256 Spellbooks: 'draft a card from ~'s spellbook' (~13+ cards) (parked, lane:mech)
- #255 Contraptions (~45 cards) and Attractions (~18 cards) (parked, lane:mech)
- #254 Battles / Sieges (~36 cards) (parked, lane:mech)
- #253 'Target player/opponent creates <token>' (~10 cards) (follow-up, lane:tokens)
- #252 Station tiers are checked at resolution, not at trigger time (follow-up, lane:mech)
- #251 Splice onto Arcane: only one splice per cast (follow-up, lane:mech)
- #250 Reflexive 'When you do' payoff targets are chosen at cast, not after the action (follow-up, lane:trig)
- #249 Daybound card entering at night should enter transformed (follow-up, lane:simplify)
- #248 'Army' (and 'Face-down') missing from creature subtypes: Great Goblin, Secret Plans do nothing (counted-full-but-wrong, lane:simplify)
- #247 Mass Diminish: AI can't cast it (cx_set_base with a target player has no side) (counted-full-but-wrong, lane:grammar)
- #246 Smokestack counted full but does nothing (soot counter core bug) (counted-full-but-wrong, lane:grammar)
- #245 'Becomes blocked by a creature' triggers only for the first blocker (counted-full-but-wrong, lane:trig)
- #244 Embercleave counts last combat's attackers: game.attackers never cleared (counted-full-but-wrong, lane:trig)
- #243 Spacecraft never become creatures after Station (27 cards counted full) (counted-full-but-wrong, lane:mech)

## 5. Remaining work by family (grammar first)

Estimates are upper bounds from the agents' plans ([plans/](plans/)); many cards have a second blocker.

- **sim-grammar**: after the stack #193 -> #202 -> #207 -> #222 -> #226 -> #229 -> #231 -> #233 -> #236 merges:
  plain prohibitions ("your opponents can't cast spells this turn", "you can't cast creature spells", "creatures
  can't attack you"), then the top of the fresh work list; keep the open stack under ~8 PRs.
- **sim-gzones**: #228 (+116), #232 (wording fix), #241 (+26) open; next graveyard card moves (return target <card>
  from your graveyard to hand/battlefield, exact origin, ~44), blink (~29), safe back-references (~30 of 91).
- **sim-gplayers**: damage verb (~300 sole), targeted player subjects and draw/discard chains (~200),
  creature-sourced damage "equal to its power" with the AI damage_amount helper (PR 3), two-recipient damage (~32).
- **sim-gcond**: #239 (+72) open; next "unless <player> pays/sacrifices/discards" (payer chooses, ~206 sole),
  "If C, B instead" (~207), suffix "B if C" (~40), more quantity words for "equal to"/"where X is" (~530 sole).
- **sim-static**: priced/conditional prohibitions ("can't attack unless its controller pays {N}"), replacement and
  prevention ("if a COLOR source would deal damage to you, prevent N"), conditional self-statics ("as long as your
  devotion ... ~ isn't a creature"), entering rules ("enters with ... if N COLOR mana was spent").
- **sim-tokens**: token riders (round 2); target-player token creation (#253) once #193 merges.
- **sim-counters**: put/remove/move/double for every counter kind, "for each counter", "if it has N or more
  counters", player counters (poison, energy, rad).
- **sim-abil**: ability effects after the mana fix (#216): "activate only ...", control exchange, goad, prevention
  shields; remaining cost parts.
- **sim-trig**: events (surveil, explore, lose life during your turn / first time each turn, noncombat damage to an
  opponent, coin flip won, counters put on creatures, cards into an opponent's graveyard, attacks alone, beginning of
  combat, "cycle this card and when ~ dies"), plus #244 and #245.
- **sim-mech**: #243 Spacecraft first, then Rooms, prepared, specialize; keyword-cost leftovers (recover,
  reinforce, freerunning, gravestorm); banding last.
- **sim-simplify**: remaining simplifications (mutate 22, backup 20, enchanted-land extra mana 15, tap-lock 13,
  filter lands 10, mana pool emptying 9, harmonize 8, tribute 8), then #248 and #282.
- **Parked** (#254-#256): Battles/Sieges, Contraptions and Attractions, spellbooks (need engine systems or data).

## 6. Biggest remaining blockers in the latest census

Generated from `briefs/lists/units-latest.csv` (census of main d4e28c5). Regenerate with
`python3 -m mtgsim.blocking_units <census>/cards.csv --save <dir>`.

### `effect` units: 17,435 distinct, 7,379 cards blocked by a single one

| Sole | Affected | Unit | Examples |
| ---: | ---: | --- | --- |
| 9 | 11 | you get {M}, then you may put a sticker on a nonland permanent you own | Aerialephant; Ambassador Blorpityblorpboop; Bioluminary |
| 8 | 10 | as long as your devotion to COLOR is less than N, ~ isn't a creature | Erebos, Bleak-Hearted; Erebos, God of the Dead; Heliod, God of the Sun |
| 6 | 8 | it gets N/N until end of turn for each creature blocking it | Barreling Attack; Beastmaster's Magemark; Berserk Murlodont |
| 6 | 8 | ~ deals N damage to that land's controller | Ankh of Mishra; Cryoclasm; Dingus Egg |
| 6 | 6 | target spell or permanent becomes COLOR | Chaoslace; Deathlace; Lifelace |
| 5 | 12 | as long as your devotion to COLOR and COLOR is less than N, ~ isn't a creature | Athreos, God of Passage; Athreos, Shroud-Veiled; Ephara, God of the Po |
| 5 | 6 | protection from COLOR and from COLOR | Animar, Soul of Elements; Auriok Champion; Great Sable Stag |
| 5 | 6 | ~ deals N damage to it | Aether Flash; Barbed Foliage; Caltrops |
| 5 | 5 | COLOR legendary creatures you control have "bands with other legendary creatures." | Adventurers' Guildhouse; Cathedral of Serra; Mountain Stronghold |
| 5 | 5 | N or more target creatures become COLOR until end of turn | Dwarven Song; Heaven's Gate; Sea Kings' Blessing |
| 5 | 5 | choose a color other than COLOR | Black Dragon Gate; Citadel Gate; Cliffgate |
| 5 | 5 | enchanted creature can't be blocked by COLOR creatures | Black Scarab; Blue Scarab; Green Scarab |
| 5 | 5 | if a COLOR source would deal damage to you, prevent N of that damage | Sphere of Duty; Sphere of Grace; Sphere of Law |
| 5 | 5 | if at least N COLOR mana was spent to cast ~, ~ enters with a N/N counter on it | Ardenvale Paladin; Embereth Paladin; Garenbrig Paladin |
| 5 | 5 | put a N/N counter on equipped creature if it's COLOR | Ring of Evos Isle; Ring of Kalonia; Ring of Thune |

### `ability` units: 2,544 distinct, 1,112 cards blocked by a single one

| Sole | Affected | Unit | Examples |
| ---: | ---: | --- | --- |
| 5 | 5 | create a tapped planet land token named new planet with "{M}: add N mana of any color." | Artificial Anomaly; Gaseous Anomaly; Spatial Anomaly |
| 5 | 5 | ~ becomes an artifact creature until end of turn | Bespoke Battlewagon; Capenna Express; Earthrumbler |
| 4 | 6 | that creature deals damage equal to its power to ~ | Durkwood Tracker; Gargantuan Gorilla; Karplusan Yeti |
| 4 | 4 | target land becomes an island until end of turn | Dreamwinder; Floodchaser; Streambed Aquitects |
| 3 | 6 | target opponent gains control of ~ | Humble Defector; Jinxed Idol; Jinxed Ring |
| 3 | 4 | goad target creature | Glóin, Dwarf Emissary; Laser Screwdriver; Laurine, the Diversion |
| 3 | 4 | if this ability has been activated N or more times this turn, sacrifice ~ at the beginning of the next end ste | Dragon Whelp; Farrelite Priest; Initiates of the Ebon Hand |
| 3 | 3 | it deals N damage to target creature with flying | Goblin Skycutter; Sunset Strikemaster; Viridian Scout |
| 3 | 3 | return N target cards from an opponent's graveyard to their hand | Nullmage Advocate; Pulsemage Advocate; Spurnmage Advocate |
| 3 | 3 | spend this mana only to cast artifact spells or activate abilities of artifacts | Grand Architect; Slobad, Iron Goblin; Vedalken Engineer |
| 3 | 3 | target noncreature artifact becomes an artifact creature with power and toughness each equal to its mana value | Karn, Silver Golem; Sydri, Galvanic Genius; Toymaker |
| 3 | 3 | the next time a source of your choice would deal damage to any target this turn, prevent that damage | Circle of Despair; Martyr's Cause; Sanctum Guardian |
| 3 | 3 | you may tap or untap target artifact, creature, or land | Elder Druid; Mind Over Matter; Trickster Mage |
| 2 | 6 | spend this mana only to activate abilities | Cryptic Trilobite; James, Wandering Dad // Follow Him; Omen Hawker |
| 2 | 5 | ~ gets N/N or N/N until end of turn | Brightling; Endling; Greater Morphling |

### `trigger` units: 1,252 distinct, 484 cards blocked by a single one

| Sole | Affected | Unit | Examples |
| ---: | ---: | --- | --- |
| 12 | 121 | when you do | Ambergris, Agent of Balance; Ambergris, Agent of Tyranny; Anthropede |
| 7 | 17 | when that creature dies this turn | A Good Day to Die; Blessed Defiance; Burn Away |
| 5 | 7 | whenever you face a dilemma | Elim Garak, Simple Tailor; Gabriel Lorca, Mirror Menace; Jett Reno, Pr |
| 5 | 6 | whenever you attack while creatures you control have total power N or greater | Hologram Janeway; Kirk, Commanding Officer; La'An Noonien-Singh, Secur |
| 5 | 5 | when you cycle this card and when ~ dies | Bant Sojourners; Esper Sojourners; Grixis Sojourners |
| 4 | 9 | when a spell or ability an opponent controls causes you to discard this card | Ajani's Last Stand; Guerrilla Tactics; Mangara's Blessing |
| 4 | 5 | whenever you lose life during your turn | Shadowheart, Cleric of Order; Shadowheart, Cleric of Trickery; Shadowh |
| 4 | 4 | whenever a creature you control explores | Lurking Chupacabra; Merfolk Cave-Diver; Shadowed Caravel |
| 3 | 6 | whenever you surveil | Blood Operative; Copy Catchers; Dimir Spybug |
| 3 | 4 | whenever equipped creature attacks alone | Bilbo's Ring; Reaper's Talisman; S.H.I.E.L.D. Spy Kit |
| 3 | 3 | when ~ enters and whenever you cast a spell with mana value N or greater | Brinelin, the Moon Kraken; Flaring Cinder; Up the Beanstalk |
| 3 | 3 | whenever a player casts a spell of the chosen color | Curse of Wizardry; Jeweled Torque; Paradise Plume |
| 3 | 3 | whenever an opponent is dealt noncombat damage | Chandra's Spitfire; Massacre Girl, Most Wanted; Wildfire Elemental |
| 3 | 3 | whenever you cast a creature spell that has an adventure | Edgewall Innkeeper; Garenbrig Squire; Wandermare |
| 3 | 3 | whenever you cast a spell of the chosen color | Diamond Knight; Diamond Mare; Prism Ring |

### `cost` units: 254 distinct, 96 cards blocked by a single one

| Sole | Affected | Unit | Examples |
| ---: | ---: | --- | --- |
| 4 | 5 | {M}, {M} or {M}, {M} | Crystal Shard; Granite Shard; Heartwood Shard |
| 3 | 5 | {M}, reveal x COLOR cards from your hand, sacrifice ~ | Martyr of Ashes; Martyr of Bones; Martyr of Frost |
| 3 | 3 | {M}, put a card an opponent owns from exile into that player's graveyard | Cryptic Cruiser; Oracle of Dust; Void Attendant |
| 2 | 3 | {M}, collect evidence N | Cryptex; Forensic Researcher; Tenth District Hero |
| 2 | 2 | exile this card from your hand | Elvish Spirit Guide; Simian Spirit Guide |
| 2 | 2 | {M}, forage | Camellia, the Seedmiser; Thornvault Forager |
| 2 | 2 | {M}, sacrifice N other artifacts and/or creatures | Keskit, the Flesh Sculptor; Mondrak, Glory Dominus |
| 2 | 2 | {M}, sacrifice another creature or an enchantment | Skophos Warleader; Slaughter-Priest of Mogis |
| 2 | 2 | {M}, {M}, exile x cards from your graveyard | Necropolis Fiend; Taigam, Sidisi's Hand |
| 1 | 4 | {M}, sacrifice N other creatures | Eater of Hope; Elesh Norn // The Argent Etchings; Priest of Forgotten  |
| 1 | 3 | put a card from your hand on top of your library | Hidden Retreat; Leashling; Penance |
| 1 | 3 | {M}, blight N | Dawnhand Dissident; Evershrike's Gift; Gristle Glutton |
| 1 | 3 | {M}, {M}, remove x N/N counters from ~ | Auntie Blyte, Bad Influence; Chamber Sentry; Cruel Sadist |
| 1 | 2 | {M}, remove x charge counters from ~ | Infused Arrows; Kyren Toy |
| 1 | 2 | {M}, sacrifice N blood tokens | Falkenrath Forebear; Shilgengar, Sire of Famine |

### `mechanic` units: 864 distinct, 491 cards blocked by a single one

| Sole | Affected | Unit | Examples |
| ---: | ---: | --- | --- |
| 27 | 45 | whenever you crank this contraption | Accessories to Murder; Applied Aeronautics; Arms Depot |
| 18 | 36 | when this siege enters | Invasion of Alara // Awaken the Maelstrom; Invasion of Amonkhet // Laz |
| 10 | 14 | banding | Ayesha Tanaka; Benalish Hero; Benalish Infantry |
| 9 | 18 | open an attraction | "Lifetime" Pass Holder; Coming Attraction; Complaints Clerk |
| 9 | 15 | specialize {M} | Alora, Rogue Companion; Ambergris, Citadel Agent; Gale, Conduit of the |
| 9 | 9 | reinforce N—{M} | Bannerhide Krushok; Break Ties; Brighthearth Banneret |
| 8 | 13 | draft a card from ~'s spellbook | Bladehold Cleaver; Boseiju Pathlighter; Cursebound Witch |
| 8 | 12 | ~ becomes prepared | Abigale, Poet Laureate // Heroic Stanza; Bloodline Recollector // Ance |
| 8 | 10 | beam me up {M} | Adversary by Algorithm; Boarding Action; Energize |
| 7 | 11 | freerunning {M} | Achilles Davenport; Brotherhood Ambushers; Chain Assassination |
| 6 | 18 | when you unlock this door | Bottomless Pool // Locker Room; Central Elevator // Promising Stairs;  |
| 6 | 16 | double team | Amber-Plate Ainok; Champions of Tyr; Dragonblood Twins |
| 6 | 6 | recover {M} | Controvert; Grim Harvest; Icefall |
| 5 | 10 | web-slinging {M} | Amazing Spider-Girl; Arachne, Psionic Weaver; Scarlet Spider, Ben Reil |
| 5 | 5 | morph—reveal a COLOR card in your hand | Dragon's Eye Savants; Horde Ambusher; Ruthless Ripper |
