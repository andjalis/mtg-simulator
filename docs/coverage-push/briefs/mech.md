# Lane: named mechanics (you are `sim-mech`, branch prefix `claude/mech`, worktree ~/mtg-worktrees/mech)
Read COMMON.md in this folder first.

Your units: lane `mechanic` (874 units, 530 cards blocked by a single one). Each is a whole game mechanic that
needs real engine support, so pick by cards completed per code. Candidates from units.csv (affected cards):
Contraptions ("whenever you crank this contraption", 45; needs a contraption deck/sprockets, probably a
simplification-free subset is impossible, so check), Max speed / "Start your engines" ("N+ | flying", 38),
Sieges (Battles: "when this siege enters", 36; check what battle support exists), splice onto Arcane (22),
Rooms ("when you unlock this door", 18), Attractions (18), specialize (15), spellbooks (13), prepared (12),
banding (14), beam me up, reinforce, freerunning, recover, double team, web-slinging, escalate, morph with reveal
costs, hexproof from COLOR, undaunted, paradigm, buyback costs.

Start with a quick survey (an hour at most): for each candidate estimate engine work vs cards completed and what
existing systems it builds on (grep the repo; some may be partly done, e.g. `alt_casts.py`, keyword modules).
Send the ranked survey to the lead before coding, then do them in that order, one mechanic per PR. Some (e.g.
Contraptions/Attractions) need data not in cards.sqlite3; flag those to the lead rather than faking them.
New code in `mtgsim/cx_mech*.py` (+ `engine/kinds/cx_mech.py`).
