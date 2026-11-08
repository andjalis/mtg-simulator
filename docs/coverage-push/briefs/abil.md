# Lane: activated-ability effects and costs (you are `sim-abil`, branch prefix `claude/abil`, worktree ~/mtg-worktrees/abil)
Read COMMON.md in this folder first.

Your units: lane `ability` (2,633 units, 1,183 cards blocked by a single one; these are sentences inside an
activated ability whose COST already parses) and lane `cost` (268 units, 130 cards: cost parts the cost parser
in `cards/parse.py` `_parse_ability_cost` doesn't model, e.g. "{M}, {M}" untap-symbol/odd costs, "remove a +1/+1
counter from a creature you control", "remove N quest counters from ~ and sacrifice it", "exile the top N cards
of your library", "exile this card from your hand", forage, collect evidence, blight).

Put new code in `mtgsim/cx_abil*.py` (+ `engine/kinds/cx_abil.py`) with a one-line hook in `_parse_ability_cost`
for cost parts. Study `cx_costs.py`, `cx_ability_effects.py`, `engine/costs.py`, `engine/abilities.py` first.

Overlap note: the effect-grammar lane (sim-grammar) is building a general selector/verb parser for plain sentences of
the "X becomes / gets / gains / loses / can't" shape. Skip those shapes in your first rounds; take costs and
ability-specific effects ("activate only ...", "if this ability has been activated N or more times this turn",
mana abilities like "add N mana of different colors", "spend this mana only to ...", charge-counter X effects,
"return this card from your graveyard to the battlefield", control exchange, goad, prevention shields).
Round 1 suggestion: the cost parts (all 130 sole cards are cheap wins), then the most-common ability units.
