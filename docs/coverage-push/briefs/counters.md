# Lane: counters (you are `sim-counters`, branch prefix `claude/counters`, worktree ~/mtg-worktrees/counters)
Read COMMON.md in this folder first.

Your units: every unit in units.csv whose text contains "counter" that is about counters on permanents or players
(2,456 units, 1,074 cards completed by a single one; mostly lane `effect`). Skip "counter target spell" (that's
countering spells, not counters) and ability COSTS that remove counters (sim-abil owns costs). Shapes: put / remove /
move / double counters of any kind (+1/+1, -1/-1, charge, loyalty, named counters like quest, ki, time, oil,
stun, shield, flying/keyword counters), "for each counter on ~" quantities, "if ~ has N or more counters",
"enters with N counters" (plain; conditional entering like "if at least N COLOR mana was spent" belongs to
sim-static), "with a counter on it" selectors, proliferate variants, counters on players (poison, energy,
experience, rad). Build a general counter-noun + verb grammar so any counter kind works with any verb and
selector. Study `counter_mechanics.py`, `proliferate.py`, `engine/kinds/` first. New code in
`mtgsim/cx_counters*.py` (+ `engine/kinds/cx_counters.py`). Counter kinds the engine doesn't model must really work
(e.g. keyword counters grant the keyword) before a line counts as matched.
