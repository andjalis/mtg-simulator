# Lane: effect grammar (you are `sim-grammar`, branch prefix `claude/grammar`, worktree ~/mtg-worktrees/grammar)
Read COMMON.md in this folder first.

The biggest pool: 17,769 `effect` units, 7,582 cards each blocked by a single one. Today every sentence is matched
by a whole-sentence regex template (`cards/patterns.py`, the many `cx_*.py` modules, `data/wordings/`). The long
tail is the same few building blocks recombined: a selector ("target spell or permanent", "N target creatures",
"~", "it", "that creature", "enchanted creature", "COLOR creatures you control") + a verb ("becomes COLOR / an
artifact creature / an Island", "gets +N/+N", "gains/loses <keyword>", "has base power and toughness N/N",
"can't block / be blocked by COLOR creatures", "deals N damage to", tap/untap, destroy/exile/return) + a duration
("until end of turn", "until your next turn", "as long as ...", static) + qualifiers (colour, type, controller,
"with flying", "for each ...").

Your job: build `mtgsim/cx_grammar.py`, a compositional parser used as a FALLBACK in `cards/parse.py`
`_parse_effects` after every existing template has failed (one-line hook). It parses selector / verb / object /
duration into the engine's EXISTING effect kinds and selectors wherever they exist (study `engine/kinds/`,
`engine/targets.py`, `continuous.py`, `cx_next_turn.py`, `cx_recolor.py` first), adding a kind in
`engine/kinds/cx_grammar.py` only when nothing fits. It must reject (return None) anything it can't execute
faithfully, so the fallback can never turn a line "full" falsely.

Round 1: the framework, the selector grammar, and the verb family that completes the most cards (check
units.csv: colour/type changes, P/T and keyword changes, "can't" restrictions are good candidates); measure it.
Later rounds: one verb family or qualifier family per PR. Report full-card deltas; the aim is hundreds per round.

Update from lead: a new lane `sim-static` owns cost modifiers, replacement/prevention ("if ... would ...",
"prevent"), conditional self-statics ("as long as <condition>, ~ ...") and entering rules. You keep one-shot and
"until ..." effects and static grants "<selector> get/have/gain/can't ...".

Update 2 from lead: two more lanes started: sim-tokens (token descriptions and create/populate verbs) and
sim-counters (put/remove/move/double counters, counter quantities and conditions). Leave those shapes to them.
