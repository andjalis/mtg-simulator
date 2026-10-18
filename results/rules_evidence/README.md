# Rules systems and evidence: first implementation batch

Implemented 2026-10-18, following the [architecture audit](../rules_architecture/README.md).

## Changes and measured scope

- Target validation now uses the same current-state membership checks as target
  enumeration, including type, controller, filters and presence. Explicit illegal
  cast targets are rejected before payment. This is not a general casting rollback API.
- The normal legend rule asks the controller which same-name legendary permanent
  to keep. Losers go through the death/zone-move path, respecting owner routing and
  bypassing destruction/regeneration/sacrifice. Legend-rule exceptions remain outside
  the declared subset. The engine still lacks a general simultaneous-event pipeline.
- Equip uses the stack and checks the target again on resolution. Removing the source,
  removing/changing control of the target, or animating the source is covered. Equipment
  that changes controller can still resolve onto the original controller's creature;
  its bonus and eventual detachment continue to work across controllers.
- A versioned capability catalog, explicit unittest scenario manifest and atomic
  evidence ledger now produce a separate behavior report. Stale inputs or trace
  contents, missing results, errors, skips and duplicate records cannot become passes.
  Existing template coverage APIs/statuses are unchanged.

The [behavior report](behavior/README.md) joins the 34,922-entry local database to
17 explicitly mapped scenarios. It distinguishes direct evidence for Isamaru and
Shuko from inferred evidence for shared capabilities. **Complete card rules support
remains unmeasured.** Every card retains unclassified requirements beyond this scope.
The parser itself was not expanded: the previous 8,533 fully template-matched entries
(24.43%) remain a recognition measurement, not a conformance count.

## Controlled Forge comparison

A real local Forge runtime was built from pinned commit
`77b6f5ae95f7f11d5a718c52a977470131db0fe1` (`2.0.16-SNAPSHOT`), using Maven 3.9.11
and a workspace-local JDK 21. The application retains its stdlib-only dependencies.
Build tools/Forge files are local and ignored by git; the pin, harness and results
are committed. Use `--engine forge --forge-dir ./forge` in this workspace.

The runtime's script index has 34,086 distinct front card names. This differs from
our database's scope/alias conventions and does not establish a supported-card rate.
Jar/tool identities are in [runtime.json](runtime.json), with full resource identity
also in the [engine smoke checkpoint](engine-smoke/results.json).

| Controlled assertion | Python | Forge |
| --- | --- | --- |
| Two Isamaru under one controller, after state-based actions | One remains | One remains |
| Creature-target effect against Island | Rejected | Rejected |
| Shuko equip before resolution | Stack size 1; unattached | Stack size 1; unattached |
| Shuko equip after resolution | Attached | Attached |

Three compared scenario records agree and conform to these bounded expectations.
See [comparison.json](comparison.json), [Python observations](python-probe.json),
[Forge log](forge-probe.log) and [Forge test result](forge-tests.txt). The comparator
also distinguishes agreement from conformance: two engines agreeing on a wrong
value does not satisfy the expectation. Missing/duplicate/malformed observations
are rejected.

Forge's equip case places a zero-cost ability explicitly on the stack; it does not
test the complete UI/AI activation/cost-payment path. This experiment demonstrates
controlled state/action assertions through Forge's test harness, **not** a general
external action API or custom-AI bridge. The Python script-importer exile-to-destroy
observation remains failing and is excluded: it tests our prototype importer, not
the Forge runtime. Production loading does not use that importer.

## Validation

- Full Python suite: 877 tests ran, 876 passed, one skipped. The two subsequently
  added comparator tests also passed separately. [Full output](python-tests.txt)
  and [comparator output](comparison-tests.txt). All 31 focused rules/report/comparison
  checks also passed after the final CSV formatting fix ([output](focused-tests.txt)).
- All 17 behavior scenarios pass; reporting checks cover stale hashes, duplicates,
  unknown/missing mappings, absent evidence, real assertion failures and skips,
  dependency cycles and direct-versus-inferred evidence.
- Forge TestNG harness: three tests passed, no failures/errors/skips. The reusable
  [wrapper](../../scripts/forge_rules_probe.sh) was run with isolated preferences.
- [Live adapter smoke](engine-smoke/report.md): four curated pairings, two games per
  engine per pairing, seed 1, 15-second clock, 120-second worker timeout. Eight Python
  and eight Forge games completed, with no draws. Counts are workflow checks; this
  sample cannot assess matchup accuracy or measure a reliable speed difference.
- Saved game-result/log hashes and evidence identities were checked. The optional
  pinned installer and probe wrapper pass shell syntax checks.

Reproduction commands and scope details: [rules/README.md](../../rules/README.md).
The original audit and old observations remain historical evidence at their recorded
revision; rerunning its probe now observes the fixed behavior plus the remaining
prototype importer gap.
