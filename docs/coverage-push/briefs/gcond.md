# Lane: grammar riders: conditions and amounts (you are `sim-gcond`, branch prefix `claude/gcond`, worktree ~/mtg-worktrees/gcond)
Read COMMON.md and gram-common.md first. Work list: lists/conditions.csv (5,266 units, 2,534 cards blocked by one).
You make riders that attach to ANY grammar verb: "If <condition>, <effect>", "<effect> if <condition>",
"<effect> for each <thing>", "... equal to <quantity>", "where X is <quantity>", "unless <player> pays ...",
"<effect> instead" (an alternative effect when a condition holds). Reuse `cx_condlib.py` (conditions) and the
quantity tables (`cx_night_quantity.py`, `counting.py`, sim-grammar's round 4 "for each" quantities): extend
them, don't fork them. Static "as long as <condition>, ~ ..." self-statics belong to sim-static; costs ("costs
less if") are done (#186). Your riders must compose with sim-gzones' and sim-gplayers' verbs through the registry.
