# Lane: statics, cost modifiers, replacement and prevention (you are `sim-static`, branch prefix `claude/static`, worktree ~/mtg-worktrees/static)
Read COMMON.md in this folder first.

Your units are a slice of lane `effect` in units.csv: lines that describe a continuous rule rather than a one-shot
action. Shapes (search units.csv for them; each has dozens of variants):
- cost modifiers: "COLOR (creature) spells you cast cost {M} less/more", "spells your opponents cast that target ~
  cost {M} more", "~ costs {x} less to cast, where x is ...", "as an additional cost to cast COLOR permanent spells, you may pay N life ..."
- replacement / prevention: "if a COLOR source would deal damage to you, prevent N of that damage", "if ~ would
  die / be put into a graveyard ..., instead", "excess damage is dealt to that creature's controller instead",
  "the next time a source ... would deal damage ..., prevent that damage"
- conditional self-statics: "as long as your devotion to COLOR (and COLOR) is less than N, ~ isn't a creature",
  "~ gets N/N as long as COLOR is the most common color ...", other "as long as <condition>, ~ ..." lines
- entering rules: "if at least N COLOR mana was spent to cast ~, ~ enters with ...", "~ enters tapped. As it
  enters, choose a color ...", "choose a color other than COLOR", hexproof/protection-from variants as statics
Build general rules: a condition library (reuse `cx_condlib.py`), a cost-modifier rule over a spell filter, a
prevention/replacement rule over a source filter. Existing homes to study first: `cx_statics.py`,
`cx_shields.py`, `cx_replace.py`, `discounts.py`, `continuous.py`, `engine/costs.py`. New code in
`mtgsim/cx_static*.py` (+ `engine/kinds/cx_static.py`), one-line hooks only in shared files.

Boundary with sim-grammar (Opus, compositional selector/verb parser in `cx_grammar.py`): grammar owns one-shot
and "until ..." effects and static grants of the form "<selector> get/have/gain/can't ...". You own costs,
replacement/prevention, conditional self-statics and entering rules. If a line is ambiguous, message the lead.
