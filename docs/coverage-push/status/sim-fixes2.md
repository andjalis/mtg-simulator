# sim-fixes2

## PRs (stacked, base integration/grammar-wave-2)
- #350 (#285 Everflame Eidolon), #351 (pilot-gate lib: false positive; Ancient Animus verified), #352 (#271 backup),
  #354 (Animus AI fight valuation).
- Audit of #349 fixes: #363 (#358 linked exile), #366 (#359 creature or planeswalker), #367 (#360 counter on "a"
  creature), #370 (#361 host-trigger "that much").
- #296 and #297 were already fixed in wave 2 (verified, commented).

## Audit of PR #349 (grammar wave 2), 2026-11-13
198 newly full cards (coverage_check vs origin/main; matches the pilot gate). I sampled 38 across #327-#334 and Sieges,
weighted toward targets, players and conditions, and played each in a small game (HeuristicAI/Scripted, log on)
against its Oracle text.

| Card | Area | Verdict | Evidence / issue |
| --- | --- | --- | --- |
| Settle the Score | counters | wrong | no planeswalker: can't be cast at all (#360, PR #367) |
| Blood Curdle | counters | wrong | no creature of mine: can't be cast (#360) |
| Humiliate | counters | correct* | discard + counter OK; same #360 issue without a creature |
| Kayla's Command | counters | wrong (mode 2) | same #360 shape; parse checked only |
| Incremental Growth | counters | correct | AI puts 1/2/3 counters on three own creatures |
| Sylvan Smite | counters | correct | counter only when not the starting player; bite works |
| Ring of Valkas | counters | correct | haste; upkeep counter only on a red creature |
| Serrated Biskelion | counters | correct | -1/-1 on itself and the target |
| Another Chance | gy return | correct | mill 2, up to two creature cards back |
| Unseal the Necropolis | gy return | correct | each player mills 3, two creature cards back |
| Witherbloom Command | gy return | can't tell | modes parse right; not played |
| Druid's Call | tokens | wrong | 0 tokens ("that many" not passed to Aura triggers); tokens would go to the damage source's controller (#361, PR #370) |
| Hornet Nest | tokens | correct | 3 damage -> three 1/1 flying deathtouch Insects |
| Saber Ants | tokens | correct | 2 damage -> 2 Insects |
| Fresh Meat | tokens | correct | 2 deaths -> two 3/3 Beasts |
| Icy Prison | unless | wrong | ETB exile always fizzles: no target policy for blink_link_exile; the same bug hits Oblivion Ring, Journey to Nowhere, Fiend Hunter (11 cards; on main via #348) (#358, PR #363) |
| Rogue Elephant | unless | correct | sacrifices a Forest, else itself |
| Mold Demon | unless | correct | sacrifices two Swamps |
| Hecatomb | unless | correct (AI choice) | engine pays the four creatures when the player agrees; HeuristicAI declines (checked in #394) |
| Tyrannize | unless | correct | target pays 7 life at 20, discards at 8 |
| Urborg Justice | unless/edict | correct | 2 deaths -> opponent sacrifices 2 |
| Elvish Pioneer | hand->bf | correct | basic land enters tapped |
| Goblin Lackey | hand->bf | correct | on combat damage puts a Goblin from hand |
| Belbe's Portal | hand->bf | correct | type chosen from the decklist (my first test had an empty deck) |
| Gaea's Touch | hand->bf | correct | once per turn, sorcery speed |
| Songs of the Damned | mana | correct | {B} per creature card in graveyard |
| Culling Ritual | mana | correct | 3 destroyed -> 3 mana |
| Mana Geyser | mana | correct | {R} per tapped opposing land |
| Alabaster Potion | prevent | correct | cast at the opponent's end step (respond_extras): gains X life. My first check only tried the main phase |
| Samite Censer-Bearer | prevent | correct | prevents 1 to each of my creatures only |
| Switcheroo | exchange | correct | AI swaps its 1/1 for their 5/5 |
| Legerdemain | exchange | wrong | a pair sharing no type could be chosen, then a no-op (#393, PR #394) |
| Shifting Borders | exchange | correct | AI takes their dual land for an Island |
| Daring Thief | exchange | correct | untap trigger swaps sharing artifacts |
| Invasion of Amonkhet | Siege | correct | mills 3 each, opponent discards, you draw; defense 4, protector set |
| Invasion of Theros | Siege | can't tell | tutor parse only |
| Burning Hands | other | wrong | can't target planeswalkers (pre-existing: 45 cards, #359, PR #366); green branch correct |
| Ray of Enfeeblement | other | correct | -4/-4 white, -4/-1 otherwise |

Result: 38 sampled. 7 wrong (Settle the Score, Blood Curdle, Kayla's Command, Druid's Call, Icy Prison, Burning Hands,
Legerdemain), from 5 causes, all filed and fixed in a PR; 3 can't tell. (Corrected 2026-11-13: Alabaster Potion
and Hecatomb are correct; Legerdemain was a real bug.) Two of the causes are
broader than #349: linked exile (on main, 11 cards incl. Oblivion Ring) and creature-or-planeswalker damage
(pre-existing, ~45 cards).

## #345 (counter removal), in progress
- Slice 1, PR #376: "that creature", removed-this-way totals, remove-and-put (+3: Blitz Leech, Decimator Beetle,
  Nexus Mentality). Found #377 (AI lets mandatory debuff triggers fizzle).
- Slice 2, PR #381: time counters on permanents/suspended cards (+5: Fury Charm, Timebender,
  Shivan Sand-Mage, Timecrafting, Dust of Moments).
- Slice 3, PR #402: Clockwork creatures + end-of-combat for blockers (+5 incl. Kjeldoran Home Guard).
- Slice 4, PR #409: abilities of suspended cards (+2: Deep-Sea Kraken, Pardic Dragon).
- Left (1 card per unit): Nihilith (head), Greater Gargadon (exile activation), Curse of the Cabal,
  damage-prevention-by-counter replacements, Suncleanser.
- Also: #377 (PR #386), #393 Legerdemain (PR #394), #367 review fixes merged up the stack.
