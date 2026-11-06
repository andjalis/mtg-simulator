# sim-gplayers plan (player-effect verbs), 2026-11-06

Work list: `lists/players.csv` (3,675 units, 1,703 sole). Measured against `origin/claude/grammar-5`: the
untargeted player subjects of grammar round 3 (`cx_grammar_players`) already take most "defending player loses N
life" / "each player draws, then discards" units (about 240 sole of the list's 1,703). What is left, by shape
(sole cards in the baseline list, a rough ceiling: many cards have a second blocker):

| # | Shape | Sole (units) | Engine kind | New? |
| --- | --- | ---: | --- | --- |
| 1 | `deals N/X damage to <recipient>`, source ~ / it / he / she | ~300 of the 541+88 "damage" units | `damage` (target any / creature / player / prev ...), `cx_group` + `damage` for "each creature [qualifiers]", `cx_players` + damage for player sets | one new kind `cx_damage` only for a source other than the resolving object |
| 2 | two recipients: `deals N damage to A and M damage to B` (B = you, itself, that creature's controller, any other target, each creature ...) | 32 (31) | two `damage` Effects; "that creature's controller" = controller of prev | no |
| 3 | targeted player subjects: `target player/opponent draws / discards / mills / loses / gains ...` (+ chains, "you may have") | 88 (137) | existing kinds with target `player` (filter `opp`); discard reads its player from target | needs core subject (see gaps) |
| 4 | imperative chains: `draw N cards, then discard N cards [at random]`, `discard N cards, then draw ...` | 85 (163) | `draw`, `discard`, `discard_random` | no |
| 5 | discard variants: `at random`, `their hand`, `a <type> card`, `that many` | ~40 | `discard_random` (needs target-player reading), `discard_hand` (target-aware), `discard` | small target-aware kinds in `engine/kinds/cx_grammar_players.py` |
| 6 | other creature as source: `that creature / enchanted creature / target creature you control deals damage equal to its power to ...` (bite) | 28+37 | `cx_damage` with `source` = prev / host / target | new kind `cx_damage` (source + amount from the source's power) |
| 7 | `that much` / `equal to <quantity>` amounts | 34+ | xq from core / gcond | coordinate with sim-gcond; no own quantity parsing |

Not mine: prevention / replacement ("if a source would deal damage ...", "the next time ...": static lane), look /
reveal digs (mostly multi-sentence, zones lane), additional costs, "if you do" (gcond).

## Damage rules that must be exact
- Source: "~" is the resolving spell / the permanent (existing `damage` uses item.source or item.card). "it" /
  "he" / "she" only when it means the same object (a self trigger or ability); "it" in a trigger about another
  creature ("whenever a creature ..., it deals") must use that creature as the source or be rejected.
- Recipient sets: "each opponent" / "each player" / "each other opponent" go through `cx_players` with a damage
  Part (real damage, not life loss: lifelink, prevention and protection must apply); "each creature [without
  flying / defending player controls / blocking it]" through `cx_group`.
- "divided as you choose" stays with cx_damage.py (or is rejected); "any other target" uses `other`/distinct.
- Two recipients in one sentence: "that creature's controller" is the controller of the first target (prev).

## Interface gaps (asked sim-grammar)
1. **Verb objects as targets.** For "~ deals 3 damage to any target", the subject is the *source*, and the target
   comes from the verb's object. Needed: a Part that carries its own target (e.g. `Part(..., target="any")` or
   `data["target"]`) so `assemble` doesn't put it on `subject.target`, and the subject passed on as the source
   (`data["source"] = "self" | "prev" | "host"`).
2. **Targeted player subjects**: "target player" / "target opponent" ("you may have target player ...") as a
   `player` subject with a real target (target `player`, filter `opp`), since `cx_players` today only names
   untargeted players.
3. Optional "may" in a player clause ("defending player may draw a card"): the player's choice; accept only with
   a decision hook, else reject.

## Order of PRs
1. `gplayers-1b`: damage family (shapes 1 and 2, subject ~ / it with self-meaning), aim 80+ full.
2. `gplayers-2`: targeted player subjects + imperative chains + discard variants (shapes 3 to 5).
3. `gplayers-3`: other-creature sources and power-based damage (shape 6), "that much" amounts with gcond.

## Tests ready to write (tests/test_cx_grammar_players2.py)
Parse + resolve: Fiery Temper style "~ deals 3 damage to any target", "it deals 2 damage to each creature without
flying" (group, flying spared), "~ deals 3 damage to target creature and 3 damage to that creature's controller"
(controller of prev takes damage, lifelink / prevention honoured), "deals N damage to each opponent" (deal_damage,
not life loss), rejections ("divided as you choose", "it" in a non-self trigger, unknown recipients).
