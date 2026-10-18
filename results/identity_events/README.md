# Physical identity, events and return scenarios

This batch follows [the first rules/evidence implementation](../rules_evidence/README.md).
It adds shared rules infrastructure and expands the explicit scenario suite from
17 to **53** across **eight declared capability subsets**. It does not expand the
oracle-text parser or establish complete card support.

## Physical cards and zone objects

Player library, hand, graveyard, exile, sideboard and the supported special casting
zones now store physical `CardInstance` values. Each has a process-local ID, original
owner and generation. Two copies of one definition compare as different physical
cards, including in temporary choice lists and sets. Definitions from CardDB remain
unchanged. Definition-based lookups are retained for compatibility; callers selecting
a particular copy must pass its instance. Repeated token blueprints create distinct
physical tokens.

Physical identity survives casting, resolution, death, exile, return and ownership
routing. A zone change invalidates frozen `ZoneRef` references. Alternate spell options
are cached by physical identity and generation, with origin checks before casting.
Battlefield faces preserve the physical front card; prepared spell copies leave their
source on the battlefield. The original owner's zones receive cards controlled by an
opponent when they leave.

Library shuffle/reorder operations and scry/dig cards that stay in the library preserve
their object references. Removed cards receive new generations when they enter other
zones. Duplicate insertion of a physical card into card zones is rejected. A number
of legacy tests formerly used object identity of cached definitions; they now assert
the identity of the actual physical cards they set up, retaining duplicate-copy checks.

## Events and supported replacements

`game.rule_events` provides typed event delivery and immutable card-state snapshots.
The existing supported trigger dispatch goes through this boundary. Logged games
retain history; ordinary runs can consume listeners without retaining it.
Battlefield entry/departure, draw/discard and migrated generic moves emit zone-change
records, including ownership, generation and last-known counters/power when relevant.

Regeneration and existing graveyard-to-exile replacements use a shared bounded
pipeline. Applicability is recomputed after each chosen replacement; an individual
replacement applies once. The affected controller can choose among applicable IDs.
Regeneration preserves the battlefield object and clears damage/combat participation;
finality and other supported exile replacements prevent death events and false
"creature died this turn" flags. Tokens still die and trigger even though their
cards do not remain in the graveyard.

Graveyard self-return references are captured at activation/trigger queuing. Moving
the source away and returning it before resolution cannot satisfy the old reference.
Persist/undying and rebound retain generation checks without the old ad hoc cloning
used to distinguish same-name copies.

This is the supported replacement subset, not an arbitrary replacement-text interpreter.
Some older effect paths still mutate identity-aware zones directly without a paired
zone-change event. Full replay, simultaneous-event scheduling, continuous-effect
layers, and a general legal-action/cost transaction API remain outside this batch.
See [the API and restrictions](../../rules/README.md) and the capability catalog.

## Evidence and inventory

[Behavior report](behavior/README.md) · [Scenario ledger](behavior/ledger.json) ·
[Per-card CSV](behavior/cards.csv) · [Full scenario/capability summary](behavior/report.json)

The report covers **34,922** local database entries. Direct current card evidence is
still limited to **Isamaru and Shuko**. All other entries inherit shared identity
capability evidence, with additional applicable capabilities inferred from parsed
metadata. Those **34,920 inferred rows are not newly verified cards**. Each card
retains unclassified requirements beyond the declared subsets; complete rules support
remains unmeasured.

Template recognition remains **8,533 fully matched (24.43%)**, 97 simplified and
26,292 partial. Every per-card template status is checked against the previous
database inventory. CSV schema 2 stores an inferred scenario count plus capability
IDs, allowing the scenario IDs to be joined from the summary without repeating the
base suite tens of thousands of times.

## Verification

- The [full Python suite](python-tests.txt): **897 tests ran, 896 passed, one skipped**.
  The [focused checks](focused-tests.txt) exercise identity and rules scenarios directly.
- All **53 mapped scenarios pass** under their recorded code/test/data identity.
  Stale identities, missing evidence, errors and duplicates remain visible or rejected.
- [Engine smoke](engine-smoke/report.md): 80 built-in games over four curated pairings,
  20 per pairing, seed 1. This checks workflow and interaction stability; it does not
  establish human matchup accuracy or statistically significant strategy differences.
- The current Python probe and pinned Forge harness compare the same three bounded
  scenarios: legend rule, creature-target legality and equip stack/attachment state.
  Results and retained inputs are in [comparison.json](comparison.json),
  [python-probe.json](python-probe.json), [forge-probe.log](forge-probe.log) and
  [forge-tests.txt](forge-tests.txt). These do not independently validate the other
  50 scenarios. The prototype Forge-script exile mapping remains outside production
  and outside the runtime comparison.
