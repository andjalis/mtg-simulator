# Card wordings as data

Most cards the engine can't fully play fail on one sentence whose wording the parser doesn't recognise,
while the effect itself already exists. For those, add a wording entry to a JSON file in this folder.
No Python changes are needed.

`mtgsim/wordings.py` loads these files. `core.json` holds the general one-sentence effects (damage, draw,
life, counters, simple removal); its entries are tried before the effect templates still written in Python
(`mtgsim/cards/patterns.py` and the mechanic modules), in the order they appear in the file. Each other file
belongs to the mechanic module of the same name (`removal.json` to `removal.py`, `batch1.json` to
`batch1_templates.py`) and is tried just before that module's Python templates. Add new entries to `core.json`
unless one of the other files is plainly about the same mechanic.

## When an entry is the right fix

- The unmatched clause is one whole sentence, for example `Ignored: "You gain 3 life and scry 1."` in
  `--coverage` output.
- The effect kind already exists: `grep -rn '@kind("draw")' mtgsim/engine/kinds/` finds its handler. An
  entry can only use existing kinds and the `data` keys their handler reads. A new kind, or a rule the
  engine doesn't have, is engine work. Leave it for the engine-cards thread.
- The wording is general. Write `~ deals (\d+) damage to target creature`, never one card's name.

## An entry

```json
{
  "match": "~ deals (\\d+) damage to target creature or planeswalker",
  "effect": "damage",
  "amount": "$1:int",
  "target": "creature_pw",
  "example": "~ deals 3 damage to target creature or planeswalker",
  "cards": ["Lightning Strike"]
}
```

| Key | Meaning |
| --- | --- |
| `match` | A Python regex for the whole sentence (it is used with `re.fullmatch`, ignoring case). Write it without the final period; the card's own name is `~`. JSON needs every backslash doubled: `\\d+`, `\\+1/\\+1`, `\\{T\\}`. |
| `effect` | The effect kind, such as `damage`, `draw`, `gain_life`, `destroy`, `p1_counters`. |
| `amount`, `amount2` | Numbers. Default 0. |
| `target` | `any`, `creature`, `creature_pw`, `player`, `self`, `prev` (the previous effect's target), and so on; see the comment on `Effect` in `mtgsim/cards/model.py`. Default `none`. |
| `filter`, `cond` | Strings the effect's handler reads. Copy them from an existing entry of the same kind. |
| `data` | An object of extra fields for the handler. Copy the keys from an entry or a Python template of the same kind. |
| `effects` | Instead of the keys above: a list of effect objects (each with `effect`, `amount`, ...) when one sentence does two things. |
| `example` | Required. A real sentence the entry matches, as the parser sees it: no final period, the card's name as `~`. |
| `cards` | Required. One or more real cards that use this sentence. |
| `note` | Optional. Anything a reader should know. |

Any value can refer to what the regex captured:

| Value | Gives |
| --- | --- |
| `"$1"` | the text of group 1 (null when the group did not take part) |
| `"$1:int"` | group 1 as a number: `"3"` gives 3 |
| `"$1:num"` | a number word or digit: `"two"` gives 2, `"a"` gives 1 |
| `"$1:lower"` | group 1 in lower case |
| `"$1:bool"` | true when group 1 took part, for optional parts like `( tapped)?` |
| `{"$map": "$1:lower", "values": {"it": "prev", "~": "self"}}` | a lookup table on the group's text |

Use `(?:...)` for groups you don't refer to, so group numbers stay simple.

## Steps

1. Find the sentence. `python3 -m mtgsim DECK.txt --coverage` or `python3 -m mtgsim.database_coverage` lists
   ignored clauses. For one card, `python3 -c "from mtgsim.carddb import CardDB; c = CardDB(offline=True).get('Card Name');
   print(c.oracle, c.unsupported)"` shows its Oracle text and the sentences the parser ignored.
2. Find a similar entry in `core.json` (search for the effect kind) and copy it.
3. Edit `match`, the values, `example` and `cards`. Add the entry at the end of the file, unless a broader
   entry above would also match your sentence: the first entry that matches wins, so a narrow wording goes
   before a broad one.
4. Run the checks:

   ```
   python3 -m unittest tests.test_wordings          # every entry loads and matches its example
   python3 scripts/parse_diff.py local --show 5     # which cards now parse differently
   ```

   `test_wordings` fails when an entry has a bad key or reference, when its example doesn't match, or when an
   earlier template already takes the example (then your entry never runs). `parse_diff` should list the cards
   you meant to fix, and nothing else. If other cards changed, your `match` is too broad.
5. Commit the JSON change and open a pull request. CI runs the same checks.

## What stays in Python

Templates that compute something (a token with keywords, a colour list, a mana cost, nested abilities) or
that return `NO_MATCH` to pass a sentence on stay in the mechanic modules (`removal.py`, `copies.py`, ...)
and `mtgsim/cards/patterns.py`. Moving more of them here happens when a simple value form covers them.
