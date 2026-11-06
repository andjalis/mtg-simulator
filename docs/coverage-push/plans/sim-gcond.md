# sim-gcond plan: rider grammar (conditions, quantities, unless, instead)

Survey: work list `lists/conditions.csv` (5,266 units, 2,534 sole). Each unit was mapped to a raw card sentence
(4,941 of 5,220 found in the 2026-11-06 census), split into rider and body, and both halves were run through the
current parser (`_if_cond` / `cx_condlib.parse`, `clauses._xq`, `_parse_effects`). Sole cards per bucket:

| Bucket | sole | Which half blocks |
| --- | --- | --- |
| "... equal to Q" / ", where X is Q" | 753 | Q unknown in 1,059 units (530 sole); Q known but scaled body fails 155 sole |
| "If C, B" | 640 | C unknown 514 (217 with body already ok); body only 126 |
| "B for each T" | 261 | body 156 (verbs: other lanes); T unknown with body ok 105 |
| "unless ..." | 206 | no rider exists; 58 sole have a parsable body |
| "... instead" | 207 | no general mechanism (32 sole are c+ b+ already); C unknown 113 |
| "as long as" | 260 | 237 are self/group statics (sim-static); 23 "for as long as" durations |
| suffix "B if C" | 40 | no suffix rider in the effect parser |

"If you do" alone is in 306 units (53 sole), but 242 of them are blocked by the body (other lanes' verbs).
They compose for free through the existing gate code once the bodies parse.

## Shapes, ranked by expected newly full cards

1. **Quantity grammar** (`mtgsim/cx_grammar_quantity.py`, evaluated in a new `("cxq", ...)` X-quantity).
   A compositional reader for Q instead of more `_xq` rows: `<ref>'s power|toughness|mana value` (its / that
   card's / that creature's / the exiled card's / target creature's), `your devotion to COLOR[ and COLOR]`,
   `the number of <noun phrase> [you control|an opponent controls|on the battlefield|in <zone>]` (reusing
   `cx_grammar._noun` / `permanent_templates.selector` / `cx_condlib._filter`), `the number of <things> that
   <event> this turn` (died, you've cast, drawn, discarded, attacked with), `the number of opponents [you
   attacked this turn]`, `the greatest <stat> among <np>`, `the total power of <np>`, `the number of colors of mana
   spent to cast ~`, `N plus Q`, `twice Q`, `half Q, rounded up|down`. Engine: the generic `xq` scaling in
   `engine/resolve.py` plus `x_quantity`. Hooks: one line in `clauses._xq` (fallback to my module) and one line
   in `engine/costs.x_quantity` (dispatch `cxq`). Estimate 150-220 newly full cards.
2. **Condition grammar** (extend `cx_condlib`, no fork): mana spent (`{M} was spent`, `at least N COLOR mana`,
   `mana from a Treasure`), cast-from zone (graveyard / exile / hand / during your main phase / using teamwork
   is out), `~ is a(n) <type>`, the previous object (`it's a creature card`, `that card/creature/permanent/land is
   COLOR|<type>|nonbasic`, `it has toxic`), turn history (`you had a land enter`, `you've cast a spell from your
   hand`, `N or more damage was dealt to it this turn`, `you discarded`), `you have a full party`, the commander
   ones. These attach through the existing "If C, B" path in `_parse_effects` (Effect.cond) to template and
   grammar bodies alike. Estimate 120-180.
3. **Riders `B unless P <action>` and suffix `B if C`**: new kind `cx_unless` (payer = you / its controller / they
   / that player / any player / defending player; costs {M}, N life, sacrifice / discard / return a permanent,
   reusing the gate cost payers), with the AI deciding for the payer. Estimate 60-100.
4. **"If C, B instead"**: the previous sentence's effects get `cond = not C`, the new ones `cond = C` (same
   scoping as `parse_otherwise`); also "B instead if C" and "if kicked: instead". Estimate 50-90.
5. "For as long as <cond>" effect durations (23 sole): later, if time allows.

## Interface needs (asking sim-grammar)
* A **sentence rider hook** in `cx_grammar` (riders are not verbs): `@rider(pattern)` tried on the whole
  sentence before the subject split, given a callback that parses the inner sentence, so `unless`, suffix `if`,
  `instead` and quantities compose with every family's verbs. Until then riders work through `_parse_effects`,
  which already re-enters the grammar fallback for the body.
* `_SCALED` should take any kind whose amount is a count (damage, create_token, counters, surveil, scry), or the
  core should scale every Part flagged `scales=True`.

## Tricky rules
* A condition is checked on resolution (CR 608.2c) except intervening-if triggers (checked on trigger and on
  resolution); keep `Effect.cond` semantics.
* "unless" gives the choice to the named player, who may decline even when able. The AI pays only when the
  outcome it avoids costs more than the payment.
* "instead" replaces only the effect it refers to (the previous sentence), never the rest of the ability.
* The value of Q is locked when the effect resolves. "its power" after a destroy or exile uses last-known
  information.
* No silent narrowing: commander / team / multi-opponent wordings are rejected or recorded as simplifications.

## Tests
`tests/test_cx_grammar_cond.py` and `tests/test_cx_grammar_quantity.py`: the parsed kinds and conds, real DB
cards coming out full (Gray Merchant's devotion, Hero's Downfall-style riders, Mana Leak-style "unless pays"),
and each rider resolved in a game, both with the condition true and with it false.
