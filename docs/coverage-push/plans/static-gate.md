# Design note: condition gate and quantity scale on grammar static lines (#398, #401, then #400)

Owner: sim-static. Base: `integration/grammar-wave-2`.

## Problem

`cx_grammar.parse_static` refuses any line with "as long as", "during", "for each" or "where", so every
conditional or scaled static needs its own regex module (`cx_conditions`, `cx_statics`, `face_lines`), each with
a fixed keyword list and P/T only. The grammar already reads the payloads (pumps, keyword grants, `cx_static`
family rules) and the libraries already read the conditions (`cx_condlib.as_static`) and quantities
(`cards.clauses._xq` with the `cx_grammar_quantity` fallback).

## Shape

One wrapper in front of the existing `parse_static` body, in a new module `mtgsim/cx_static_gate.py`:

```
As long as C, <static>.        <static> as long as C.        During your turn, <static>.
<subject> gets +N/+M for each Q[ and <more>].          <subject> gets +X/+X, where X is Q.
```

1. **Peel** the gate: C goes through `cx_condlib.as_static` (unknown C: the line stays ignored). "During your
   turn" is the `your_turn` code. After a leading gate, "it" in the body means the subject C names (`~`, or the
   enchanted / equipped creature).
2. **Peel** the scale: "for each Q" through `cx_grammar._count_spec`, ", where X is Q" through `_xq`; X in the
   P/T becomes ±1 and the pump is multiplied by Q's value. Only the pump scales; a fixed non-X component next to
   an X component is refused.
3. **Parse** the remaining static with the unchanged grammar (`_clauses(..., "static")`): pumps, keyword grants,
   `cx_temp_kw` flags and `cx_static` rules on `~`, the host, or a group.
4. **Record** gated / scaled payloads in one place, `advanced_rules["gated"]`, as
   `(code, scope, spec, payload)` rows (scope `self`, `host`, `group`; spec the grammar group spec;
   payload `("pt", p, t, xq)`, `("kw", keywords)` or `("rule", name, value)`). Plain lines keep their current
   records, so nothing already full changes its parse.
5. **Read** the rows where the engine already reads conditional statics: `cx_statics.pt_bonus` and
   `cx_statics.grants` (one call each) and `cx_grammar.static_rules` (gated family rules). The condition is
   checked with `cx_statics._holds(source, code, affected)` (source's point of view, "it" = the affected
   permanent, recursion guard), the quantity with `Game.x_quantity` from the source.

## Refusals (rejection rules)

- unknown condition or quantity; any quote, "until", "this turn", "except" left in the body;
- a P/T payload whose condition or quantity reads power / toughness (dependency loop), a keyword payload whose
  condition reads keywords, a group whose membership reads P/T (existing `_stat_conditioned` guard);
- an "Enchanted" line on a non-Aura, "Equipped" on a non-Equipment (existing guard);
- quantities of kind `stat` / `sac` / `spell` (referent not fixed for a static).

## Slices

1. #398 slice 1: gate with conditions `cx_condlib` already knows on payloads the grammar already reads.
2. #401 slice: scaled pumps (self, host, group); then CDA ("~'s power and toughness are each equal to Q").
3. #400 on that base: "can attack as though it didn't have defender" and other combat permissions as static /
   gated verbs.

Coordination: sim-340 (#397) hooks conditions and quantities into effect sentences; this note only touches
static lines, and both use `cx_condlib` / `_xq` unchanged (new phrases go into those libraries, not into
either hook).
