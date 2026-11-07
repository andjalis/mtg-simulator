# Lane: tokens (you are `sim-tokens`, branch prefix `claude/tokens`, worktree ~/mtg-worktrees/tokens)
Read COMMON.md in this folder first.

Your units: every unit in units.csv whose text contains "token" (1,794 units, 756 cards completed by a single one;
mostly lane `effect`, some `ability`/`trigger`). The token *description* is its own sub-grammar: count, tapped /
attacking, P/T, colours, card types and subtypes, name ("named New Planet"), keywords (incl. ones the token
parser rejects today: "unsupported token keywords: changeling / firebending N / ..."), granted abilities in quotes
("with "{T}: Add one mana of any color."" / "~ can't block."), "that's a copy of", predefined tokens (Treasure,
Food, Clue, Blood, Map, Role ...), and "for each" counts. Make the token-description parser general so any
combination of these parts works, then the verbs around it ("create", "each player creates", "target opponent
creates", "populate", "tokens you control ..."). Study `cards/tokens.py`, `copies.py` and the existing token kinds
first. New code in `mtgsim/cx_tokens*.py` (+ `engine/kinds/cx_tokens.py`); hooks in `cards/tokens.py` are allowed
as one-liners.

Boundaries: sim-grammar (selector/verb grammar) doesn't parse token descriptions; sim-counters owns counter
sentences. If a sentence mixes them (e.g. "create a token, then put a +1/+1 counter on it"), do the token part and
tell the lead.
