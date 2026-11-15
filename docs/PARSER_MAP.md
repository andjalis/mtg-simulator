# Parser map: where card text goes

Read this before exploring the parser. It is the route a card's text takes, where each kind of rule
lives and how to look at a parse in seconds, so a task can start from the right file instead of from
`cards/parse.py`. Adding a verb to the compositional grammar is in [`mtgsim/GRAMMAR.md`](../mtgsim/GRAMMAR.md).
Where new code goes is in `AGENTS.md` ("Where new code goes"). If this map is wrong or missing a
piece you had to work out, fix it in the same branch.

## Look before you read code

```
python3 scripts/coverage_check.py --cards "Card A" "Card B"            # status + the exact unsupported lines (0.3 s)
python3 scripts/coverage_check.py --cards "Card A" --parse             # + Oracle text and everything it parsed into
python3 scripts/coverage_check.py --line "Exile that creature until ~ leaves the battlefield."   # one effect sentence
python3 scripts/coverage_check.py                                      # this checkout vs origin/main: gained/lost full, changed parses (cached)
```

Use these instead of writing your own sqlite or `_parse_effects` snippets. Oracle text is
normalised before matching: the card's own name and "this creature/spell/..." become `~`.

## The route

```
CardDB.get(name) ─► cards/parse.py  _parse_face
                     │  one Oracle line at a time through the line parsers in cards/face_lines.py, in order:
                     │    _face_special_lines        speed gates, graveyard abilities, kicker, ability words, keyword lines
                     │    _face_mode_and_ward_lines  modal spells, ward
                     │    _face_land_and_mana_lines  lands, mana abilities
                     │    _face_cost_and_static_lines cost changes and statics (cx_static_* modules, cx_grammar.parse_static)
                     │    _face_keyword_ability_lines keyworded abilities
                     │    _face_ability_lines        activated abilities (_parse_ability) and triggers (_parse_trigger)
                     │  a line nobody consumes lands in face.unsupported (what --cards prints)
                     ▼
     triggers:  _parse_trigger_line ─► _TRIGGERS templates (cards/clauses.py)
                                        └─ ("ev",) entry: cx_events.split_head, the shared "When(ever) <subject> <event>" grammar
     effects:   _parse_effects(text) ─► (effects, unmatched_sentences)
```

`_parse_effects` (cards/parse.py) first applies every `_SUBS` rewrite, then for each sentence tries, in order:

1. `residual_templates.parse_effect`, `advanced_templates.parse_effect`
2. sentence riders that attach to the effects before them: `cx_statics.counter_rider`, `exile_permissions`,
   `chance_templates`, `cx_tokens.parse_rider`, `_opt_rider` ("you may ...") and others listed there
3. `If C, B`: `_if_cond(C)` (backed by `cx_condlib`) + `cx_grammar_cond.if_body(B)`; the effects get `cond`
4. `_EFFECT_PATTERNS`: whole-sentence regexes, first fullmatch wins. `cards/patterns.py` plus every family
   module's `EFFECT_PATTERNS`, joined at the end of `cards/__init__.py` (so join order matters)
5. fallbacks: `_split_compound` ("A and B"), `card_referent`, `cx_suspect.parse_otherwise`,
   `cx_grammar.parse_fallback` (the compositional grammar), `cx_multi_target.lift` (counted targets)
6. otherwise the sentence is unmatched. Afterwards `cx_grammar_cond.resolve_instead` binds "... instead".

## Shared libraries: reuse, don't re-implement

| Need | Where | Entry point |
| --- | --- | --- |
| A condition ("if you control a Wizard", "as long as ...", intervening if) | `cx_condlib.py` | add `@rule(pattern)` returning a code; `check(game, p, code, item, source, prev)` evaluates it |
| A quantity ("equal to Q", ", where X is Q", "for each Q") | `cards/clauses._xq`, fallback `cx_grammar_quantity.py` | sets `data["xq"]`; `Game.resolve` scales the amount |
| A permanent selector ("nontoken artifact or creature you control") | `permanent_templates.selector(text)` / `matches(game, perm, spec, controller)` | specs: `types_any`, `traits`, `alts`, ... |
| The grammar's noun phrases | `cx_grammar.py` (`subject`, `object_phrase`, `desc_matches`) | see `mtgsim/GRAMMAR.md` |
| Trigger heads (subjects + events) | `cx_events.py` | `split_head(line)` |
| Conditional / scaled statics | `cx_static_gate.py`, `cx_statics.py`, `cx_static_*.py` | `cx_grammar.static_rules(game, perm, name)` at check time |
| Layers (P/T, keywords) | `continuous.py` | layers 6 and 7b-7d |

## At runtime

- An `Effect(kind, amount, amount2, target, filter, cond, data)` resolves through `engine/kinds`:
  `@kind("name") def name(game, p, eff, target, item, prev, ...)` gets whichever arguments it names.
  Add a kind to the matching family module (`damage`, `cards`, `graveyard`, `permanents`, `stats`, `other`).
- `target` strings: slot targets (`creature`, `any`, `player`, ...; chosen when cast and checked again on
  resolution in `engine/targets.py`), `self` (the source), `host` (enchanted / equipped), `none`,
  and `prev`.
- **`prev`, "it" and "that creature":** in `engine/stack.py` (resolving an item) `prev` starts as the
  trigger's context permanent (the creature it triggered on), becomes each legal slot target in turn, and
  becomes `None` when a slot target is illegal. So "Destroy target creature. Its controller ..." reads the
  target, and "Whenever a creature blocks, ... that creature" reads the context. Which events put the
  creature in the context is decided by the event (`cx_events`, `cx_tokens.event_amount_ctx`); check
  before binding "that creature".
- The default AI picks targets in `engine/policy.default_choose_target`. Kinds it doesn't know need
  `data["side"] = "mine"` or `"theirs"`.

## Tests

One file per module: `tests/test_<module>.py`. `tests/test_cx_grammar.py` has a `Base` class with
`perm`, `cast` and `spell` helpers for resolving effects in a real game. Parse real cards through
`CardDB(offline=True).get(name)` and skip when `mtgsim/data/cards.sqlite3` is missing.

## Check budget (several agents share one machine)

| When | Run | Not |
| --- | --- | --- |
| while editing | the focused test modules you touch; `coverage_check.py --cards ...` | the full suite |
| after a parser batch | `coverage_check.py` (cached; lists gained/lost full and changed parses) | `parse_diff.py` (minutes per run; the PR CI runs it) |
| once, before the final commit | `PATH="$HOME/.local/share/venvs/pyflakes/bin:$PATH" python3 scripts/fast_check.py` | repeating it after unrelated edits |
| lint | `~/.local/share/venvs/pyflakes/bin/python scripts/lint.py` (system python has no pyflakes) | `pip install` |

Run the full suite only when a brief asks for it or you changed shared engine code broadly (the lead
runs it at integration). Don't `sleep` and poll a background run: wait for it in the foreground.

## Traps

- Python 3.10: no backslashes inside f-string expressions, no 3.11+ syntax.
- A static must not read itself (anthems conditioned on power, keyword grants conditioned on keywords).
- Never drop a word to make a line fit: unknown qualifiers, conditions or riders keep the line unsupported.
- `cards/__init__.py` joins pattern lists in order; a broad pattern joined early can shadow later ones.
