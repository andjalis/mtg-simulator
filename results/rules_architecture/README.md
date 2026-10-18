# Rules architecture audit and implementation strategy

Audited 2026-10-18 at engine commit `ddd3ce952f7130031f4cb332a187c6151c876063`.
This report changes the implementation plan; it does not add rules support.

## Recommendation

Use Forge for broad-card-pool simulations now, with its own AI and documented limits.
Develop the Python engine as an explicitly bounded, fast environment for our own AI.
Expand it by shared rules systems and interaction scenarios, then add card templates in
small batches on top of those systems. A production Forge-script importer should wait
for stricter semantic validation. Rewriting the engine or translating every script at
once would postpone useful results and retain many of the same correctness problems.

The current **8,533 / 34,922 (24.43%)** is the number of local database entries fully
matched by templates. Another 97 have recorded simplifications, 26,292 are partial,
and none failed to parse. See the [database inventory](../database_coverage/README.md).
The denominator includes basic lands and entries outside ordinary constructed Magic;
it is not a promise to simulate every card in every format. A count of fully
rules-supported cards is **not established** by these measurements.

## What exists and what needs strengthening

| Area | Evidence in current implementation | Consequence / next change |
| --- | --- | --- |
| Structured definitions | `cards.py` already has `Effect`, `Trigger`, `Activated`, `AltCost` and a 132-field `CardDef`; oracle parsing produces these objects. | Keep the intermediate representation. Add validated effect/cost/target schemas and parser source provenance incrementally. |
| State and identity | `Permanent` separates controller and owner. Graveyard/exile have tracked zone versions, but hand/library contain name-equal `CardDef` objects; equality/hash use card name. | Separate immutable definitions from physical card instances and zone-change object identities. Migrate one zone path at a time; protect duplicate-name and leave/return behavior with tests. This is a structural risk, not a claim that every duplicate-card interaction fails. |
| Legal actions and priority | Stack, response hooks and APNAP trigger grouping exist. `cast` explicitly delegates timing checks to callers; target enumeration and validation differ; equip attaches directly. | Put legal-action validation and execution behind one API, with explicit permissions for casting during resolution. Both pilots should select from the same legal actions. |
| State-based actions | Repeated creature/planeswalker death checks and counter cancellation exist. No legend-rule handling is present. | Centralize simultaneous state changes and player choices. Start with the demonstrated legend-rule gap and simultaneous death/last-known-information cases. |
| Events and replacements | `fire`, `pending`, `destroy`, `dies`, regeneration, rebound and other mechanic modules supply useful pieces. | Introduce a typed event/context contract and shared zone-move/replacement pipeline; retain existing modules while migrating. Test competing replacements and delayed effects explicitly. |
| Continuous effects | Power, toughness, types and keywords are computed through properties and special fields (`Permanent._base`, `_pt_bonus`, `has`). | Add ordered continuous effects, timestamps and dependencies for a declared subset of rules layers before expanding copy/type-changing effects. Current property calculations do not constitute a general layer system. |
| AI and rules | `ai.py` contains its own combat projections; `engine.py` also contains default choices and action heuristics. | Keep AI decisions outside legality. Share pure combat calculations where possible and test projections against actual combat transitions. AI-vs-baseline results measure strategy in the same engine, not independent rules correctness. |

The central engine is 4,486 lines, the card parser 2,336, and the heuristic AI 1,529
at this revision. File size alone does not justify a rewrite; the concrete semantic
gaps below justify extracting shared contracts. Module extraction without changing
those contracts would not improve correctness.

## Reproduced observations

Run from the repository root, with the offline database installed:

```sh
python3 results/rules_architecture/probe.py > /tmp/rules-architecture-observations.json
```

Saved output: [observations.json](observations.json). The script reports known failures
as data and exits successfully when the audit completes; it is not a CI conformance gate.
Fixtures construct small game states directly, independently of AI game outcomes.

| Scenario | Required behavior | Observed at audited revision |
| --- | --- | --- |
| Two Isamaru, Hound of Konda under one controller | Controller chooses one to keep; the other goes to its owner's graveyard. | Both remain after state-based actions. Isamaru is `full` in template coverage. |
| Activate Shuko equip, holding priority | Activation goes on the stack; attachment happens on resolution. | Host changes immediately; stack stays empty. Shuko is `full`. |
| Validate a creature-target damage effect against Island | Reject the noncreature land. | Enumeration excludes it, but `legal_target` accepts it. This probes the validator, not a claim that the default AI routinely chooses lands for burn. |
| Translate a Forge `ChangeZone` battlefield-to-exile ability | Preserve exile semantics or refuse translation. | Prototype produces `destroy`, which differs for indestructible, regeneration and death triggers. |

These examples demonstrate why matching all printed text cannot establish complete
support, even for a card with no printed ability text. They are a prioritized bug list,
not an exhaustive audit of the Comprehensive Rules.

## Forge evaluation

There are two distinct integrations:

| Integration | Already useful for | Limits |
| --- | --- | --- |
| `mtgsim.forge.run_forge_match` | Exports `.dck` files, runs the external Java `sim` process and returns outcomes. Benchmark/crosscheck paths preserve logs and fingerprint runtime resources with isolated worker preferences. | Forge pilots both decks. The adapter does not expose per-decision state/actions for `HeuristicAI`, controlled scenario setup or Python policy training. Those require a new bridge and feasibility work. |
| `mtgsim.forge_script` | Offline investigation of structured ability chains and APIs that the Python representation might express. It is not in the production card-loading path. | Translation is a subset with lossy mappings. In addition to exile-to-destroy, target/controller restrictions can collapse and semantic fields including `TargetMin`/`SorcerySpeed` appear in `NOISE`. Agreement with our parser is not independent correctness evidence. |

**Fresh checks:** 81 relevant Forge/coverage/crosscheck tests ran: 80 passed, one skipped
([test output](tests.txt)).
These validate adapter behavior with fake installations and parser fixtures, not
Forge's rules. Java 21 is available; `find_forge()` reports no configured installation
and Maven is absent. **No live Forge games or current Forge card census were run.**
The presence of a script/name would establish availability, not perfect implementation.

A fresh built-in smoke run completed 80 games across the four curated benchmark
pairings (20 each, seed 1). Its fingerprinted [report and logs](builtin-smoke/report.md)
are saved. This demonstrates workflow health; its small sample and partial card
coverage cannot validate rules or human matchup rates. No fresh speed comparison
between engines was measured.

**Historical evidence, not a current comparison:** the
[October 15/16 cross-check](../cross_check/README.md) recorded 60 matchups with 40
Forge games each and 300 built-in games each. Sixteen were flagged, with a median
12-point gap. That report predates the current engine and modern provenance checks;
its AI-versus-rules explanations are hypotheses. It reports roughly four hours on
four cores for the Forge run. The README's 3–4 seconds/game estimate is also historical;
neither number predicts throughput on this machine or these exact inputs.

Operational constraints already handled or exposed by the adapter include startup
and worker timeouts, result validation, full raw logs, draw reporting and observed
starting players. A play/draw quota may require discarded games, with a fourfold
per-worker cap and possible residual skew. A draw may reflect an internal error or
timeout. `sim` does not perform AI sideboarding, so it cannot supply sideboarded BO3
predictions. Keep Forge version/resources pinned and inspect logs when comparing
results. Forge's GPL-3 licensing also applies to the existing copied script fixtures;
preserve their provenance when extending that dataset.

**Decision:** retain and use the existing match adapter. Before building a custom-AI
bridge, run one bounded feasibility experiment: pin a Forge build, script a small
state/action trace and determine whether its API/test harness can supply the legal
choices and observations we need. Gate any larger integration on that result.
For correctness comparisons, align actions and state assertions in controlled
scenarios; comparing win rates with different pilots confounds rules and policy.

## Implementation batches, in order

| Batch | Deliverable | Acceptance gate |
| --- | --- | --- |
| 1: honest evidence | Implement the [coverage design](coverage-design.md): capability catalog, scenario manifest and evidence ledger beside existing template reports. | Unknown behavior remains unknown; stale or failed evidence cannot count as a passing scenario. Report a denominator for every metric. |
| 2: demonstrated rules gaps | Unify target membership checks, implement legend-rule choice, put equip activation on the stack. | The three built-in probes become real passing regression tests, including response/removal, control changes and duplicate-name cases. Failed actions must leave state unchanged. |
| 3: shared contracts | Migrate physical identity/zone moves, then typed events and costs; preserve current supported scenarios during each small migration. | Duplicate copies remain distinguishable; zone changes invalidate old references; owner/controller routing, last-known information and cost rollback are tested. |
| 4: continuous/replacement rules | Implement a declared subset of continuous layers, dependencies and replacement choices before adding mechanics that depend on them. | Interaction scenarios cover effect ordering, duration, simultaneous events and multiple applicable replacements. Remaining unsupported layers stay explicit. |
| 5: card families | Add validated templates or script translations for high-value families over those primitives. | Each batch identifies a capability dependency, adds positive/negative/interaction scenarios, updates evidence, and remeasures inventory. Forge import refuses unrepresented semantics. |

Within a batch, prioritize selected decks/format, shared dependencies, reproducible
correctness bugs and feasible scenario coverage. Use the existing gap counts as
upper bounds on parser reach, not additive benefits or an automatic task order.
For example, the large "equipment" gap includes varied unparsed effects even though
basic equip already exists; it is not a single missing primitive. Maintain a
separate backlog for multiplayer, unusual formats and nontraditional cards rather
than silently including them in a promise to support the entire local database.

README/AGENTS unsupported-feature lists have drifted (some aura, equipment and copy
subsets now exist). The capability catalog should become the authoritative scope,
with generated user-facing summaries, so prose and implementation stop diverging.
