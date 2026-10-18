# Bounded behavior evidence

`capabilities.json` declares three supported subsets. `scenarios.json` maps 17
unittest methods to those subsets, records expected-value references and identifies
direct card fixtures. Setup, action sequences and assertions are the linked test
methods in `tests/test_rules_contracts.py`; their source and all test helpers enter
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
Per-card requirements currently recognize parsed legend/equip metadata and creature
targets in spells/triggers, plus declared dependencies; this is an intentionally
incomplete classifier. Existing template coverage APIs/statuses remain unchanged.
Legacy tests without explicit manifest entries do not count as mapped evidence.
Casting now rejects explicitly supplied illegal targets before payment. Automatic
target selection and the wider casting/cost transaction pipeline remain outside
this batch; this does not introduce a general legal-action API.
Expectations are maintained from the cited rules and card text; this is not an
externally certified rules suite. Update the manifest version when expectations,
scope or required scenarios change.

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
