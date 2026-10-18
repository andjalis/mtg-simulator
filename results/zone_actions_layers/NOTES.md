# Zone movement, actions and continuous effects

This batch routes paired moves through identity-aware card-zone hooks, preserving
pre-move snapshots for legacy effects as well as explicit movement calls. Stack
entry/departure and alternate battlefield faces use the physical card. Discover
now records its exile stage and casts directly from exile; Manifest Dread keeps
the manifested physical card through entry and death. The graveyard exile-to-draw
path now actually places the card in exile.

`Action` and legacy tuples share dispatch. A legality probe uses the same execution
path with rollback. Transactions restore engine state, object identities and RNG,
and buffer event observers until commit. Required static targets are chosen before
paying; invalid late discard choices and overlapping mana/sacrifice resources do
not leave partial payments. Priority and resolution run after commit.

Continuous effects cover keyword operations, base P/T, additive modifiers and
counters, then switching. Base animations and Cursed Roles use timestamps. Explicit
same-layer dependencies, cycle handling, source lifetimes, cleanup expiry and saved
last-known P/T have mapped interaction tests. This adds infrastructure and fixes
existing behavior; it adds no Oracle parsing templates.

Evidence is scoped: [the behavior report](README.md), [scenario traces](traces),
[the full regression output](tests.txt), [smoke games](smoke/report.md), and
[three common Forge comparisons](comparison.json) record separate measurements.
The Forge probe exercises legend, creature-target and equip assertions; it does not
independently verify the new action or continuous-effect scenarios. Its raw output
is [preserved](forge-probe.log), with a narrow whitespace exception in .gitattributes.
The Python probe also retains the known importer exile/destroy gap, excluded from
the three runtime comparisons.

Read [the declared restrictions](../../rules/README.md) before interpreting results.
Special actions remain separate APIs, policies must avoid external side effects,
resource selection does not search every possible payment, and the full continuous
layer and keyword timestamp rules are not implemented. No card is labeled fully
rules-supported. Direct card evidence and inferred capability evidence stay separate.

## Measurements

74/74 mapped scenarios pass across 10 declared capability subsets. All 80 smoke
games completed and the three bounded Forge comparison sets agree. Template
recognition remains 8,533 full matches (24.43%), 97 simplified and 26,292 partial
out of 34,922 database entries, with no parse errors. There are two cards with
current direct scenario evidence and 34,920 with shared capability evidence only.
Complete card rules support remains unmeasured.

The full regression suite ran 918 tests: 917 passed and one was skipped. The
Cascade casting-lock fixture now casts its initiating spell before establishing
the lock in response, so the scenario exercises a legal sequence and still
checks that the discovered spell cannot be cast under the restriction.
