# Bounded behavior evidence

`capabilities.json` declares fourteen supported subsets. `scenarios.json` maps 116
unittest methods to those subsets, records expected-value references and identifies
direct card fixtures. Setup, action sequences and assertions are the linked test
methods in `tests/test_rules_contracts.py`, `test_identity_events.py`, `test_regeneration.py`,
`test_return_counters.py`, `test_persist_wither_rebound.py`, `test_zone_actions_layers.py`,
`test_costs_types_triggers.py` and `test_tokens_phase_conditions.py`; their source and all test helpers enter
the evidence identity. Synthetic or modified card fixtures are capability evidence,
and are not assigned as direct evidence for the real card.

```sh
python3 -m mtgsim.behavior_coverage --run --save /tmp/behavior-run
python3 -m mtgsim.behavior_coverage --ledger /tmp/behavior-run/ledger.json --save /tmp/behavior-review
```

The runner saves a versioned JSON ledger atomically, one trace per mapped scenario,
a JSON summary, Markdown report and per-card CSV joined to the offline inventory.
It checks code, card data, catalog, scenario and test identities and trace contents.
Missing/stale scenarios remain in the denominator; duplicates and removed-scenario
records are rejected. Skips are `not_run`, assertion failures are `fail`, and setup
or loader failures are `error`. A lock protects each output directory. Use a fresh
directory for each new execution; report-only commands can reevaluate old evidence.

`scoped_suite_passes` applies only to a capability's declared subset and required
scenarios, including its dependencies. Card rows retain unclassified requirements
outside this initial scope, so no card receives a claim of complete rules support.
Per-card requirements currently recognize the base identity requirement, parsed
legend/equip metadata, creature targets, removal/regeneration and selected graveyard
return effects, nonland action handling, creature/animation/Role P/T handling, plus declared dependencies; this is an intentionally
incomplete classifier. Existing template coverage APIs/statuses remain unchanged.
Legacy tests without explicit manifest entries do not count as mapped evidence.
Casting validates required static targets before payment; action transactions cover failed payment and choice paths. See the API scope below.
Expectations are maintained from the cited rules and card text; this is not an
externally certified rules suite. Update the manifest version when expectations,
scope or required scenarios change.

CSV schema 2 records a unique inferred scenario count per card. Join its
`required_capabilities` to the scenarios in `report.json` for the scenario IDs;
direct scenario IDs remain explicit. This avoids repeating the base identity suite
tens of thousands of times in the inventory file. A shared capability pass is not
a direct test of every card that depends on it.

## Card identity and event API

Player card zones contain `CardInstance` objects with process-local `physical_id`,
immutable original owner, and a changing `generation`. Definitions from CardDB are
not modified. Physical instances compare by identity; raw `CardDef` comparisons and
zone lookups retain name-based compatibility. Use an instance, not a definition,
when selecting a particular copy. Cast variants retain their exact origin and a
generation check; battlefield faces keep the physical card in `Permanent.front`.
Copies of spells such as prepared spells do not move their source onto the stack.

`zone.reference(card)` returns a frozen `ZoneRef`; `ref.find(zone)` returns the
matching current object or `None`. Graveyard-return ability references are captured
when activated/queued, before opponents can move the card. Replacing a same-name
copy cannot satisfy the reference. Use `zone.shuffle(rng)` or `zone.reorder(cards)`
for reordering; these preserve generations. Looking at and putting back cards with
scry/dig also preserves unmoved objects. Physical instances cannot be duplicated
by list multiplication or inserted into two card zones simultaneously.

`game.rule_events` delivers typed `RulesEvent` records to `listeners`; logged games
also retain `history`. Normal runs avoid retaining that history. Battlefield changes
and paired CardZone/stack transfers record source/destination and immutable
pre-move snapshots. Legacy remove/pop plus append paths use the same boundary.
Initial fixture insertion and reordering do not emit paired movement events. Existing supported trigger delivery runs through this event boundary.
Regeneration and supported death-to-exile replacements share a bounded pipeline;
applicability is recomputed after each choice and each replacement applies once.
`choose_replacement(game, me, choices, intent)` can select among applicable IDs;
the default picks the first. These changes do not implement arbitrary replacement
scripts, a complete replay log or simultaneous-event scheduling. A removal without an eventual destination has no paired event; copies and characteristic views are not physical moves. See the capability restrictions before relying on event coverage.

The historical [coverage design](../results/rules_architecture/coverage-design.md)
describes later slices (broader requirement classification, source spans and more
mechanic families). The implementation currently uses an atomic JSON ledger rather
than JSONL. It does not implement those later slices or a general Forge policy bridge.

## Pinned Forge comparison

The [pin](forge/pin.json) selects source commit
`77b6f5ae95f7f11d5a718c52a977470131db0fe1`. Build with a JDK (including `javac`)
and Maven, then run the probe with isolated preferences:

```sh
scripts/install_forge.sh ./forge 77b6f5ae95f7f11d5a718c52a977470131db0fe1
bash scripts/forge_rules_probe.sh ./forge > /tmp/forge-rules-probe.log 2>&1
python3 results/rules_architecture/probe.py > /tmp/python-rules-probe.json
python3 -m mtgsim.rules_compare --builtin /tmp/python-rules-probe.json --forge-log /tmp/forge-rules-probe.log --save /tmp/rules-comparison.json
```

`MVN` may select a Maven executable and extra Maven options may be appended to the
probe command. Managed environments must configure Maven to use the inherited proxy
and trust its CA; keep TLS verification enabled. Build tools and Forge remain external
to the Python application. `--engine forge --forge-dir ./forge` selects this runtime.

The Java probe uses Forge's real card scripts and `AITest` setup. It emits three
`RULES_PROBE` JSON observations: one remaining Isamaru, rejection of Island for a
creature target, and Shuko's stack/attachment state before and after resolution.
The equip case inserts a zero-cost activation explicitly, so it does not exercise
Forge's UI/AI activation and cost-payment pipeline. Compare these common assertions
with the corresponding Python observations; additional fields are not comparable.
The fourth Python audit observation is about our script importer, not Forge's engine,
and is deliberately excluded from this cross-engine comparison.

This demonstrates a small controlled-scenario harness. It is not a custom-AI bridge,
not equivalent to full-game win-rate agreement, and not evidence that every Forge
card or every interaction works. New scenarios need an explicit setup/action mapping.
The Java probe references external Forge test APIs without copying their implementation.
The existing Forge script fixture provenance remains in `tests/fixtures/forge_scripts/README.md`.

## Actions and scoped continuous effects

`Action(kind, source, option=None, targets=None)` and the existing action tuples go
through `game.do_action(player, action)`. `game.can_perform(player, action)` probes
the same path and restores engine state and RNG. Cast, equip, loyalty and general
or legacy activation APIs use nested transactions: invalid choices, unavailable
additional costs, exceptions and rejected targets restore existing objects in
place, including physical generations, tapped state, life, counters, pending
triggers and logs. Event observers receive buffered events only after commit;
priority and resolution begin afterward. Policies must return choices without
external side effects. Policy-owned state and physical-ID allocation are not
rolled back. `cast` retains its low-level timing permission for effect-granted
casts; `do_action` enforces ordinary casting timing. Land play, cycling and other
special actions remain separate. This is not a complete priority-permission or
cost-choice search system; the current payment policy can reject an action even
when a different combination of resources could have paid it.

`game.add_continuous_effect(permanent, operation, ...)` supports `grant`, `remove`,
`set_base`, `modify` and `switch`. The engine applies keyword operations, base P/T,
modifiers, counters and switching in that order. Animations and Cursed Role
attachments get timestamps, so a newer base-setting effect wins. Same-layer
`depends_on` IDs override timestamp order; cycle edges fall back to timestamps.
Optional `source` binds an effect to a battlefield source; omitting it allows a
resolved effect to survive its source. `until_eot=True` expires at cleanup. Saved
last-known P/T survives departure and effects do not follow the new battlefield
object after reentry. No new Oracle templates are claimed by this API.

Copy, control, text and characteristic-defining layers, inferred
Oracle dependencies and comprehensive keyword-grant timestamps remain outside
this slice. Type/color operations are described below. Registered keyword operations follow the existing keyword baseline.
The mapped cases exercise these bounded contracts, not every card interaction.

Alternate land faces, crafted backs, enchantment returns and manifested views supply their physical card before battlefield entry is published. Discover emits library-to-exile moves, casts the found card directly from exile or moves it into hand, then returns the other cards to the library. These traces do not establish full face-down or Discover conformance.

## Joint costs, type/color views and phase triggers

`mtgsim/costs.py` enumerates supported sacrifice sets (including `sac_n`) and a craft
material before mana payment. A source consumed for one cost is reserved from the
others; an ordinary source can still tap for mana and then be sacrificed. Additional
mana alternatives and reserved X mana use the same plan during validation and
execution. This preserves the existing convoke/improvise/delve policies rather than
introducing a general solver for all mana abilities and optional-cost combinations.

The continuous API now includes set/add/remove operations for types, subtypes and
colors. Pass `types`/`subtypes` as iterables of names and `colors` as WUBRG symbols.
Type/subtype operations run in layer 4 and colors in layer 5. Callers explicitly
supply subtype changes and basic land mana abilities; the API does not infer them.
No general type/color Oracle parser is introduced. `Permanent.card` stores the
current characteristic view, refreshed at effect and relevant state changes;
`copiable_card` holds the underlying copiable values and `front` the physical card.
Source departure, cleanup, animation and crew timestamps refresh these views.
Last-known characteristics remain on the departing object. Copy/control/text layers,
complete legacy timestamp integration and comprehensive copy rules remain outside.

Upkeep/end-step events fan out `each_upkeep`, `opp_upkeep` and `each_end_step` with
the phase player as context. New templates accept each upkeep, each player's upkeep,
each opponent's upkeep, each end step and the end step. Recognized intervening-if
conditions are checked at triggering and resolution. A general source-sacrifice
effect checks membership of the original permanent. Unknown conditions, unknown
token keywords and unsupported relative-clause copy selectors remain visible in
ignored text; Madness is not added. Direct Oracle fixtures and synthetic scenarios
have separate manifest mappings. These contracts do not establish full card support.

## Decayed and bounded conditions

Decayed creatures cannot block. Declaring one as an attacker queues its keyword
ability on the normal stack. Resolving it creates a one-shot end-of-combat trigger
that sacrifices the original permanent if its trigger controller still controls it.
Removing decayed afterward does not remove the delayed trigger; leaving and
returning creates a different permanent. Entering the battlefield attacking does
not trigger it. End-of-combat priority also runs when no attackers survive.
Unknown token keywords such as devour and changeling remain reported as gaps;
supported keyword lists accept commas and a final conjunction.

The shared condition helper recognizes exact/lower/upper hand-size and life-total
thresholds, a tapped/untapped source, and the absence of creatures with a supported
keyword (including Jadar's decayed check). Intervening-if gates are checked before
queuing and once when the complete ability starts resolving, rather than between
its effects. An ordinary conditional sentence inside an ability remains conditional
on that effect. Arbitrary Boolean predicates, library-size checks and alternate-win
effects remain outside this batch. Tests use Convalescent Care, Hollowborn Barghest,
Falcon Abomination, Jadar and Imaginary Pet as direct Oracle fixtures, alongside synthetic cases.
