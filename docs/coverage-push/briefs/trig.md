# Lane: trigger heads (you are `sim-trig`, branch prefix `claude/trig`, worktree ~/mtg-worktrees/trig)
Read COMMON.md in this folder first.

Your units: lane `trigger` (1,253 units, 481 cards blocked by a single one): "Whenever/When/At ..." heads the
trigger grammar doesn't match, while its effect may already parse. The trigger grammar lives in
`cards/clauses.py` (_TRIGGERS) and `mtgsim/cx_events.py` (subject + event grammar with an engine observer);
study both and `engine/stack.py` `fire` first. New code in `mtgsim/cx_trig*.py` (+ `engine/kinds/cx_trig.py`);
extend `cx_events.py` where the subject/event grammar is the right home.

Biggest first: "when you do" (reflexive trigger after an optional action; 127 cards contain it), "when that
creature dies this turn" (delayed trigger on a target), then new events: surveil, explore, lose life
(during your turn / first time each turn), noncombat damage to an opponent, coin flip won, counters put on
creatures (N or more), cards put into an opponent's graveyard, "attacks alone", "at the beginning of your combat
step" / "of the upkeep of enchanted creature's controller", "cycle this card and when ~ dies", "when ~ enters and
whenever ...", spells of the chosen colour. Prefer adding events to the event grammar (one event completes every
card that uses it with any effect) over whole-head templates. Each new event must really fire in the engine.
