# Shared +1/+1 counter costs

Activated abilities can now remove a fixed number of +1/+1 counters from among
creatures their controller controls. The payment can use a single creature,
several creatures, or the ability's own source. Opposing creatures, noncreature
permanents and other counter types are excluded.

The joint payment planner allocates counters without spending them and searches
alternate allocations when a donor is needed for mana. Mana abilities are used
before the other costs: a creature consumed for mana cannot also donate counters.
A surviving mana creature may tap and donate counters, and a donor may subsequently
be sacrificed for a separate activation cost. A simultaneous single-counter cost
on the source is reserved separately so it cannot be paid with the same counter.

Counter removal happens during activation, before the ability resolves. An illegal
target or failed payment restores state through the existing action transaction.
If the ability later loses its target, its costs remain paid. Losing the last
counters that keep a donor alive does not cancel the ability.

This uses deterministic engine payment choices; it does not add a manual donor
selection interface or change attack heuristics. Variable X, "one or more", "any
number", unspecified counter types, shared costs on spells and noncreature donors
remain outside this implementation. Their unsupported text is preserved.

The local database has ten cards containing "counters from among creatures you
control". The targeted before/after parser comparison improves two:

- **Hopeful Initiate:** all text is now template-matched, including the training
  support from the preceding batch and its artifact/enchantment removal ability.
- **Novijen Sages:** its shared counter cost and draw ability are now recognized;
  Graft 4 remains unsupported.

`coverage-delta.json` records the same-database comparison with the previous cost
parser, retaining the training/dethrone implementation in both versions. This is
a targeted inventory, not a full-database census or complete rules certification.

Reproduce behavioral checks from the repository root:

```sh
.venv/bin/python -m unittest tests.test_shared_counter_costs tests.test_costs_types_triggers tests.test_training_dethrone tests.test_zone_actions_layers -q
.venv/bin/python -m unittest discover -s tests -t . -v
.venv/bin/python scripts/lint.py
```
