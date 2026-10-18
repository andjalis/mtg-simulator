# Coverage and behavior evidence design

Design proposal, 2026-10-18. This file specifies the next implementation; the catalog,
scenario runner and reporting API below are not implemented by this audit.

## Independent measurements

Keep the existing `card_coverage`, CSV `status` values and CLI compatible. Treat
`full` as **fully template-matched** everywhere. Add orthogonal measurements instead
of relabeling all existing cards as behavior-verified.

| Dimension | Unit and denominator | States / meaning |
| --- | --- | --- |
| Template recognition | Distinct entries in a fingerprinted offline database, or copies in a named deck; label which. | Existing `full`, `simplified`, `partial`, `unknown`, `parse_error`. |
| Rules capability | Explicit capability IDs in a versioned engine capability catalog. | `implemented_subset`, `partial`, `absent`, `unassessed`; every entry states restrictions and required dependencies. Declaration alone is not passing evidence. |
| Scenario conformance | Versioned, applicable required scenarios for a declared scope. | `pass`, `fail`, `error`, `not_run`, `stale`; zero scenarios means not measured, never 100%. |
| Card behavior evidence | Cards with current direct scenarios, plus a separate count with only inferred capability evidence. | Counts and linked scenarios, outstanding failures and untested requirements. A passing scenario does not confer complete card support. |
| Independent comparison | Scenarios actually executed in each pinned engine with comparable setup/actions. | `agree`, `disagree`, `not_comparable`, `not_run`; Forge agreement is additional evidence, not certification. |

Today we can report 8,533/34,922 fully template-matched. A database-wide count of
cards with current behavior evidence is **not measured**. Existing tests are valuable
but lack a complete card/scenario manifest; do not infer a zero passing count or
claim all 8,533 have verified behavior. The audit's four observed failures are a
small, explicitly selected set, not a representative rate.

## Data model

Use JSON/JSONL and stdlib validation, with integer `schema` versions. Reuse
`mtgsim.provenance` code/data/runtime fingerprints and atomic file writing.

1. **Capability catalog**, proposed `rules/capabilities.json`: stable ID, description,
   support state, exact supported subset, restrictions, required capability IDs,
   implementation references and scenario IDs. Examples: `targets.creature`,
   `zones.object_identity`, `sba.legend`, `stack.equip`, `replacement.regeneration`.
   Basic game rules must be dependencies even when absent from printed oracle text.
2. **Card requirements**, generated per card/face: stable database key, source/oracle
   hash, parser version, recognized text spans, emitted effects, capability IDs and
   unclassified requirements. Keep front/back/adventure links. If no stable oracle ID
   exists in the DB, record the normalized database key and source hash; do not pretend
   the name alone is globally stable. Handwritten exceptions require a reason and review.
3. **Scenario manifest**, proposed `rules/scenarios.json`: stable scenario ID/version,
   direct card IDs (if any), capability IDs, scope assumptions, setup fixture, explicit
   action sequence/choices, assertion IDs, expected state, expected-value provenance
   and implementation test reference. Allow synthetic capability fixtures, but do not
   attribute them as direct card tests. Expectations come from reviewed rules/card
   text; attach a rules version/citation when available, and mark unreviewed sources.
4. **Execution ledger**, generated JSONL: run identity, scenario version/hash, engine
   identity, source/data hashes, outcome, actual assertions, trace/log hash and failure
   reason. Unsupported setup/runner errors are `error` or `not_run`, not passes.
   Never accept a cached pass if its identity or artifact hashes differ.

Example result shape (illustrative, deliberately a failure):

```json
{
  "schema": 1,
  "scenario_id": "sba.legend.two-isamaru",
  "scenario_version": 1,
  "engine": "builtin",
  "run_identity": "<content fingerprint>",
  "direct_cards": ["isamaru, hound of konda"],
  "capabilities": ["sba.legend"],
  "outcome": "fail",
  "assertions": [{"id": "one-remains", "expected": 1, "actual": 2}],
  "expected_source": {"kind": "reviewed-rule", "reference": "legend rule"},
  "trace_sha256": "<saved trace hash>"
}
```

The audit's `observations.json` is a separate schema for observations, not an initial
conformance ledger. Its `passed` booleans must not be ingested as reviewed evidence.

## Aggregation and display

Show separate columns in card reports:

`card | template_status | required_capabilities | declared_gaps | current_direct_scenarios
| current_capability_scenarios | failures | untested_requirements | evidence_status`

`evidence_status` is `not_measured`, `has_failures`, `some_scenarios_pass`, or
`scoped_suite_passes`. Use `scoped_suite_passes` only when every explicitly required
scenario in the named scope passes, all requirements are classified, and no required
capability is declared partial/absent/unassessed in that scope. Include the scope and
suite version beside it. Even that label does not mean all possible interactions work.
Global rules gaps are inherited by applicable cards/decks; a textless legendary
creature inherits `sba.legend`. Unclassified requirements block completeness claims.

At run level, distinguish inventory changes, changes in applicable required scenarios,
and execution results. A fixture may execute multiple assertions but counts once as
a scenario. Multiple runs or duplicate evidence cannot inflate the denominator.
Include failed, error, not-run and stale counts. Newly required scenarios immediately
enter the denominator; deleting/excluding one requires a recorded scope change.
For cross-engine comparisons, report each engine's outcome and the comparison status
separately. Pilot win rates, confidence intervals and performance remain benchmark
measurements, never scenario passes.

## First implementation slice

Start with a catalog and manifest for targeting, legend rule and equip response
windows, using the three reproducible built-in gaps in this audit. Include passing
baseline cases and negative/interaction cases, not just the demonstrated failures.
Have a small unittest-compatible runner write assertion results and retain raw
observations. Generate a separate behavior report joined to existing template rows;
do not alter existing statuses or count unmapped legacy tests as current evidence.

Acceptance checks for that slice:

- Missing manifest mapping, no scenarios, and an unknown capability produce an
  explicit unmeasured/incomplete result.
- A stale code/card/scenario identity invalidates a cached pass.
- Failed assertions and runner errors cannot be dropped from totals or counted as passes.
- Duplicate scenario records cannot inflate card or capability counts.
- An untested legend-rule dependency prevents a blanket support claim for Isamaru.
- A synthetic creature fixture is capability evidence; a directly named card fixture
  is separately counted as direct evidence.
- Existing deck/database template output and CSV status semantics remain compatible.

After the first slice works, map the existing interaction tests to scenarios in
bounded mechanic families. Expand metrics with the evidence actually available,
keeping the full database as an inventory rather than a claim of total conformance.
