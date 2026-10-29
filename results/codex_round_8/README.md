# Codex card-coverage round 8

`mtgsim/cx_recycle.py` implements general whole-zone graveyard/library recycling,
including self or targeted graveyards, all players' graveyards, and hand/graveyard
resets followed by a numeric draw count. Cards retain their physical identity and
owner. Every affected library is shuffled before any follow-up drawing, and draws
occur in active-player order. Shuffling is not searching, milling or discarding.
Sources on the stack are excluded; normal spell/flashback completion handles them.

All new mechanic logic lives in the new module. Thirteen registration/dispatch lines
join it to the card templates, shared effect registry, default targeting and generic
AI minor-effect values. Existing kinds' values and other mechanic-family modules are
unchanged. Explicit targets may recycle either legal player; default targeting uses
a legal self target. The new effect can be planned without claiming optimal strategy.

Fresh 34,129-entry censuses against main `688e854`: **29 cards improve; 13 become
fully template-matched**. Full matches rise from 12,578 to 12,591; partials fall
from 21,308 to 21,295. Recorded simplifications stay at 243. Zero parser exceptions
or status regressions. Full template recognition is not complete rules verification.

New full matches: Blessed Respite, Clear the Mind, Cranial Archive, Echo of Eons,
Feldon's Cane, Game Plan, Learn from the Past, Mnemonic Nexus, Reminisce, The Mending
of Dominaria, Thran Foundry, Time Reversal and Timetwister. Remaining clauses on
Time Spiral, Day's Undoing, Primal Command and other partials remain visible in
coverage-delta.json. Existing counters, triggers, sacrifice, gift and activated-cost
implementations are reused, with no new code added to those families.

Eighteen new tests prove exact physical duplicates and zone generations, self/other
ownership, untouched hands/exile when excluded, single shuffles, all-recycle-before-
first-draw sequencing, active-player order, short/empty libraries, no discard/search/
mill side effects, numeric draw counts, required target legality, player hexproof,
stale graveyard references, ordinary spell sources, flashback sources and an exiled
activation-cost source. Both pilots plan and cast Timetwister. Four gameplay smoke
runs with both pilots exercise repeated recycling and finish; one reaches the
configured 40-turn cap. policy-smoke.json records functional evidence, not a strength
estimate. No win-rate improvement is claimed.

Full standalone suite: **1,639 pass, one optional skip**, all 1,640 discovered tests
executed with exact inventory matching. Lint, whitespace and required local parser
comparison pass: 29 raw database parses change with zero new exceptions.

## Combined compatibility evidence

A separate detached checkout applies rounds 1–8 to fresh main 688e854, preserving
Claude's intervening changes. All **112 new behavior tests** and standalone imports
pass together. Its full suite executes all 1,734 discovered tests: **1,733 pass and
one optional test skips**. Lint and combined local parser comparison pass. The raw
comparison changes 130 database parses, including a paid-X behavior correction on
a card whose coverage classification stays partial.

The combined fresh census improves **129 distinct cards**, including **86 newly full
matches**: 12,664 full, 243 simplified, 21,222 partial, zero parse errors. No status
regressions or internal selection-marker leaks occur. Source hashes and exact test
inventories are recorded in integration-validation.json. The integration measurements
are separate from this round's standalone measurements and do not represent merged
or remotely CI-approved work.

## Delivery and continuation

Branch `codex/cards-8` is independent of rounds 1–7. GitHub API access remains blocked,
so PR creation, remote CI verification and merge are pending. Rebase each round onto
current main immediately before opening its PR, rerun checks when source changes,
and merge only after green remote CI. No direct main or Claude-branch writes occurred.
BACKLOG.md and results/residual_batch/ were untouched by this work.

CONTINUATION.md records the requested **2026-10-29 11:12:31 UTC** continuation and
provides a ready-to-use prompt. **No cloud task was scheduled**: this session has no
scheduling tool. continuation-candidates.json refreshes the previous shortlist with
all eight rounds applied; it contains 26 remaining partial cards and only their
residual ignored clauses. Completed recycling cards have been removed from the todo
shortlist. This is a reviewed sample, not an exhaustive impact ranking.
