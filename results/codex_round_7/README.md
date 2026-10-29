# Codex card-coverage round 7

`mtgsim/cx_recursion.py` adds non-targeted bounded graveyard-to-hand returns using
existing `gy_move` resolution. Known types, subtype/type intersections, inclusive
unions, fixed and paid-X choice counts, all-card returns and numeric/X mana-value
bounds are supported. Target requirements, related-card restrictions, chosen types,
supertypes and different ownership destinations are not silently discarded.

Fresh 34,129-entry censuses against main `b8d12a6`: **5 cards improve; 3 become
fully template-matched**. New full matches: A-Druidic Ritual, Another Chance,
Bond of Insight. Full matches rise from 12,557 to 12,560; partials fall from 21,330
to 21,327. The 242 simplifications are unchanged; zero parser exceptions or status
regressions. Template recognition is not complete rules verification.

Kairi retains its total-mana-value bounce clause. Gix's Command retains counter,
combat and sacrifice clauses for Claude. Only their shared graveyard-return bodies
improve; no code in those other families changed. Already matched cards/effects are
not todos. coverage-delta.json records exact before/after residuals across all faces.

Twelve new tests prove optional counts, inclusive filters, physical duplicates,
zone versions, owner isolation, subtype/type intersections, mana-value bounds,
more than 99 eligible cards, empty/zero selections, paid X and preservation of
unsupported restrictions. Another Chance casts and resolves with both pilots.
These are functional checks, not AI strength measurements.

Full suite: **1,630 pass, one optional skip**, all 1,631 discovered tests executed.
Lint, whitespace and the required local parser comparison pass. Five raw database
parses change with zero new exceptions. No engine, AI, trigger or activated-cost
modules changed. Protected backlog/results files and Claude's branches were untouched.

## Combined compatibility evidence

A separate temporary detached checkout applies rounds 1–7 together to main b8d12a6.
All **94 new behavior tests pass together**. Its complete suite executes all 1,713
discovered tests: **1,712 pass and one optional test skips**. Lint and the combined
local parser comparison pass, with no new exceptions. Source hashes are recorded in
integration-validation.json. One round-2 rejection example was updated to include a
different-name restriction after round 4 added ordinary bounded multi-card searches;
all eleven round-2 tests pass again and runtime source was unchanged by that cleanup.

The combined fresh census improves **100 distinct cards**, including **73 newly full
matches**: 12,630 full, 242 simplified, 21,257 partial, zero parse errors. No status
regressions or internal selection-marker leaks occur. See integration-coverage-delta.json,
integration-coverage-summary.json and integration-parse-diff.md. These measurements
are integration evidence only: the branches are not merged and remote CI is not verified.

## Delivery and continuation

Branch codex/cards-7 is independent of rounds 1–6; delivery.json records the API
blocker. Rebase each round onto current main immediately before creating its PR,
rerun checks when source changes, and merge only after green remote CI.

CONTINUATION.md contains a ready-to-use handoff for the requested 11:12:31 UTC
continuation. **No cloud task was scheduled**, because this session has no scheduling
tool. continuation-candidates.json lists 33 reviewed candidates freshly re-parsed
with all seven rounds applied. Every entry is still partial and includes only its
remaining ignored clauses; this is a shortlist, not an exhaustive impact ranking.
