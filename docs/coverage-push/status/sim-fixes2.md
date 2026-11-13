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
| Hecatomb | unless | AI choice | AI never sacrifices four creatures (keeps them; Hecatomb goes); rules path untested by force |
| Tyrannize | unless | correct | target pays 7 life at 20, discards at 8 |
| Urborg Justice | unless/edict | correct | 2 deaths -> opponent sacrifices 2 |
| Elvish Pioneer | hand->bf | correct | basic land enters tapped |
| Goblin Lackey | hand->bf | correct | on combat damage puts a Goblin from hand |
| Belbe's Portal | hand->bf | correct | type chosen from the decklist (my first test had an empty deck) |
| Gaea's Touch | hand->bf | correct | once per turn, sorcery speed |
| Songs of the Damned | mana | correct | {B} per creature card in graveyard |
| Culling Ritual | mana | correct | 3 destroyed -> 3 mana |
| Mana Geyser | mana | correct | {R} per tapped opposing land |
| Alabaster Potion | prevent | AI-never-uses | AI at 5 life with WWWWW doesn't cast it |
| Samite Censer-Bearer | prevent | correct | prevents 1 to each of my creatures only |
| Switcheroo | exchange | correct | AI swaps its 1/1 for their 5/5 |
| Legerdemain | exchange | minor | a pair sharing no type can be chosen; resolves as a no-op (rules: illegal choice) |
| Shifting Borders | exchange | correct | AI takes their dual land for an Island |
| Daring Thief | exchange | correct | untap trigger swaps sharing artifacts |
| Invasion of Amonkhet | Siege | correct | mills 3 each, opponent discards, you draw; defense 4, protector set |
| Invasion of Theros | Siege | can't tell | tutor parse only |
| Burning Hands | other | wrong | can't target planeswalkers (pre-existing: 45 cards, #359, PR #366); green branch correct |
| Ray of Enfeeblement | other | correct | -4/-4 white, -4/-1 otherwise |

Result: 38 sampled. 6 wrong (Settle the Score, Blood Curdle, Kayla's Command, Druid's Call, Icy Prison, Burning Hands),
from 4 causes, all filed and fixed in a PR. 2 AI choices / AI-unused, 1 minor, 3 can't tell. Two of the causes are
broader than #349: linked exile (on main, 11 cards incl. Oblivion Ring) and creature-or-planeswalker damage
(pre-existing, ~45 cards).

## Next
- #345 (remove counters from bound objects and suspended cards).
