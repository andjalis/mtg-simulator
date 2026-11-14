# The effect grammar: adding a verb family

`mtgsim/cx_grammar.py` is the fallback parser for sentences no template matches. It reads a sentence as
**subject + verb chain + duration**, hands each verb phrase to a registered **verb parser**, and turns what the
parsers return into Effects (spells, triggers, abilities) or static records (permanent lines). Verb families live
in their own modules, so several people can add verbs without touching the same file.

```
Target creature you control  gets +2/+0 and gains first strike  until end of turn.
└── subject ───────────────┘ └── verb chain (2 phrases) ───────┘ └── duration ───┘
```

The core (`cx_grammar.py`) owns subjects, durations, chain splitting, assembling Effects, static lines, "for each"
quantities and noun-phrase matching. **Don't edit it to add verbs.** If you need it changed (a new subject kind,
a duration, a hook), ask sim-grammar.

## Where things go

| What | File |
| --- | --- |
| Verb parsers for one family | `mtgsim/cx_grammar_<family>.py`, found and imported automatically (any module named `cx_grammar_*`) |
| New engine kinds, only when no existing kind fits | `mtgsim/engine/kinds/cx_grammar_<family>.py`, also imported automatically |
| Tests | `tests/test_cx_grammar_<family>.py` |

Existing families: `stats` (gets ±N/±N, base P/T), `keywords` (gains / loses / has, can't attack / block / be
blocked, attacks if able), `color` (becomes COLOR) and `players` (gain / lose life, draw, discard, mill for
untargeted player subjects).

## The interface

```python
from .cx_grammar import Part, verb

@verb(r"gets? ([+-]\d+)/([+-]\d+)", heads=("get", "gets"), subjects=("permanent", "group", "host"))
def gets(m, clause):
    if clause.duration != "eot":
        return None                      # reject: the sentence stays ignored
    return [Part("pump", int(m[1]), int(m[2]))]
```

`@verb(pattern, heads=..., subjects=...)` registers a parser:

- `pattern` is **fullmatched**, case-insensitively, against `clause.verb`.
- `heads` lists the words the phrase can start with. The core uses every family's heads to find where the subject
  ends and to split a chain ("gets +1/+1 and gains flying", "discards a card, then draws a card").
- `subjects` lists the subject kinds the verb accepts (see below). It defaults to `("permanent", "group")`.

The parser is called as `parse(match, clause)` and returns **a list of `Part`s, or `None` to reject**. Parsers
are tried in module-name order, then registration order. The first one that returns a list wins, so a parser that
returns `None` lets the next one try the phrase.

`clause` is a `Clause`:

| Field | Meaning |
| --- | --- |
| `verb` | the phrase in lower case, without the subject, a leading "also" or the duration: `"gets +2/+0"` |
| `text` | the same phrase as written (original case, for subtype names and the like) |
| `duration` | `"eot"` (until end of turn), `"turn"` (this turn), `"combat"` (this combat), `""` (none: a one-shot change that lasts, or a player action) or `"static"` (a static ability line) |
| `subject` | a `Subject` (below) |

`clause.subject` is a `Subject`, which a verb usually only needs to check by `kind`:

| kind | Example | Assembled as |
| --- | --- | --- |
| `permanent` | "target creature", "up to two target creatures each", "~", "it" | first Part on the target (`subject.target`, `subject.data`), later Parts on `prev`; repeated `subject.copies` times with `distinct` |
| `group` | "creatures you control", "each Goblin", "other attacking creatures", "creatures target player controls" | one `cx_group` Effect: inner Parts applied to each member, the set fixed on resolution |
| `player` | "you", "each player", "each opponent", "that player", "defending player", "that creature's controller", "its owner" (`subject.who`) | one `cx_players` Effect: inner Parts applied verb by verb to each named player, with target `that_controller` (handlers read the player from `target`) |
| `host` | "enchanted creature", "equipped creature" | target `host` (one-shot), or the attachment's bonus and keywords (static) |
| `imperative` | a sentence that starts with a verb registered with `subjects=(..., "imperative")`: "Destroy target creature." (`who` "you") | every Part must carry its own `obj` (below) |

Players have `who` "target" for "target player" / "target opponent" (target `player`, `data["filter"] = "opp"`
for an opponent). They are assembled as `cx_players` with `data["side"]`, and the default AI picks that player by
side (`engine/policy.default_choose_target`). A `cx_group` over "creatures target player controls" gets a side too.

### Objects: `Part(..., obj=Subject)`

When the verb names its own object ("~ deals 3 damage to **any target**", "**Destroy** up to two target
artifacts"), read the object with `cx_grammar.object_phrase(text)`. It reads what `subject()` reads, plus "any
target", "target creature or planeswalker" and "target player or planeswalker", and returns a Subject or None. Then
return `Part(kind, ..., obj=that_subject)`. `assemble()` places the Part by its object:

- `permanent`: target `obj.target`, the object's data merged, repeated `obj.copies` times with `distinct`;
- `group`: a `cx_group` with this Part as its inner effect;
- a target player: target `player` (filter `opp` for an opponent);
- an untargeted player: target `none` with `data["who"]`, which your kind resolves with
  `cx_grammar.players(game, p, who, item, prev, target)`.

The clause subject (`self` / `prev` / `host` / `permanent`) goes in `data["source"]`. Parts without an object
belong to the subject: "~ deals 2 damage to any target and gets +1/+0 until end of turn" pumps ~. A group or
player subject can't have Parts with objects (the sentence is rejected).

### Riders: `@rider(pattern)`

A rider wraps a whole sentence ("B unless that player pays {2}", "B if C"). Its pattern is fullmatched against
the sentence (no final period) **before** the subject is split off, and riders are tried before verbs. It is
called as `parse(match, inner)`, where `inner(text)` parses a sub-sentence with the whole grammar and returns
Effects or None. Return Effects (for example the inner ones with a `cond` added), or None.

### Parts

A `Part(kind, amount=0, amount2=0, data={})` is one Effect without its target. The grammar adds targets, and
`data` is merged into the Effect's data. Use **existing kinds** wherever one fits (see `engine/kinds/`). Inside
groups and player subjects, inner handlers are called directly with `target=` the member, so a kind must read
its object from `target`.

For "for each <thing>" and ", where X is …", the core sets `data["xq"]`. `Game.resolve` multiplies the Effect's
`amount` (and `amount2` for pumps), and `cx_group` / `cx_players` multiply their inner amounts. A "for each"
sentence is accepted only if some Effect's kind is in `_SCALED` or carries `data["scales"] = True`. Set
`scales` on Parts whose amount is a count.

**Family rules** (any meaning the engine reads at a check, such as who can block whom): return
`Part("cx_static", data={"rule": name, "value": v})` for a static line. The core records it on the card, as
`advanced_rules[name]` for "~ …", `[name + "@host"]` for "enchanted / equipped creature …", or
`[name + "@group"]` as `(group spec, v)` for a group. For "this turn", return `Part("cx_rule_turn", data={"rule":
name, "value": v})`, which is kept on the target for the turn. Your engine check then reads every value that
applies to a permanent with `cx_grammar.static_rules(game, perm, name)` (see `cx_grammar_evasion.block_forbidden`,
which `engine/state.can_block` asks).

**Static lines** (`duration == "static"`): apart from `cx_static`, only three Part kinds mean something. `pump` becomes an anthem (group)
or the attachment's bonus (host). `grant` with `data["keyword"]`, and `cx_temp_kw` with `data["keywords"]`, become
a static keyword grant. Any other kind makes the line unsupported. A static verb must accept
`clause.duration == "static"` explicitly.

A static line may carry a **condition gate** ("As long as C, ...", "... as long as C", "During your turn, ...") or
a **quantity scale** ("gets +1/+1 for each Q", "gets +X/+0, where X is Q"). `cx_static_gate` peels them off, reads
the rest with the same static verbs and records the result in `advanced_rules["gated"]`; `static_rules` returns a
gated `cx_static` value only while its condition holds, so family rules need nothing extra. See
`docs/coverage-push/plans/static-gate.md`.

Shared helpers in `cx_grammar`: `keyword_list(text)` (known keywords or None) and `count(word)` ("a"/"two"/"3" →
int or None). `cx_grammar_color.colors(text)` reads colour words.

## Rejection rules

The grammar must never turn a line "full" unless the engine really does what the text says.

1. **Understand every word or return None.** Don't drop a qualifier, a condition or a rider to make a phrase fit.
2. **Check the duration.** A one-shot P/T or keyword change without "until end of turn" isn't a pump. "This turn"
   only fits restrictions. Reject durations your effect can't honour.
3. **Check the subject kind** if the verb means something different for it (most do: `subjects=`).
4. **Use the engine's kinds as they behave**, including how they choose targets: set `data["side"] = "mine"` or
   `"theirs"` on Parts of kinds the default AI doesn't know, so `policy.default_choose_target` aims them right.
5. **An approximation is a simplification**, not a full card: record it the way existing templates do, or reject.
6. **Statics must not read themselves.** The core rejects anthems conditioned on power or toughness and keyword
   grants conditioned on keywords. Keep that in mind for new static meanings.

## Testing a family

Put tests in `tests/test_cx_grammar_<family>.py`:

- parse sentences with `mtgsim.cx_grammar.parse_sentence` and assert the kinds (and `None` for what you reject);
- parse real cards from the database (skip when `mtgsim/data/cards.sqlite3` is missing) and check they come out full;
- resolve the effects in a game (`tests/test_cx_grammar.py` has a `Base` with `perm`, `cast` and `spell` helpers).

Run `.venv/bin/python -m unittest tests.test_cx_grammar tests.test_cx_grammar_<family>`.
