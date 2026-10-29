# Codex card-coverage round 4

`mtgsim/cx_tutors.py` adds fixed-count and bounded search templates using the existing
search effect. It validates card types, type unions, basic lands, subtypes, subtype
permanents and numeric mana-value bounds. A bound is repeated for each alternative,
and permanent searches exclude Kindred instants and sorceries. Unknown colors,
supertypes, X-dependent filters and different-name restrictions remain unsupported
by these new templates. Single-card library-top searches are left to round 2.

Fresh 34,129-entry censuses against main `b8d12a6`: **28 cards improve; 24 become
fully template-matched**. Full matches rise from 12,557 to 12,581; partials fall
from 21,330 to 21,306. Recorded simplifications stay at 242. Zero parser exceptions
or status regressions. This measures recognition, not complete rules correctness.

New full matches include Congregation at Dawn, Ranger of Eos, Brightglass Gearhulk,
Reshape the Earth, Zur the Enchanter and the fixed-cost Rebel/Mercenary tutor families.
The complete before/after list is in `coverage-delta.json`. Remaining ignored clauses
are only Behold the Beyond's discard-hand instruction, Captain America's token
instruction, Defiant Vanguard's delayed destruction and Planar Engineering's
sacrifice instruction. These residual clauses belong to Claude; already covered
searches are not todos. No costs, triggers, sacrifice or token code changed.

Twelve new tests prove physical duplicate selection, a single shuffle, fewer-than-max
searches, mana-value filtering on each alternative, owner isolation, subtype/permanent
filtering, existing activated-ability payment, ETB searching and casts by both pilots.
Full suite: **1,630 pass, one optional skip**, all 1,631 discovered tests executed.
An unused test import was removed after the full run; the exact cleanup was verified
and all twelve focused tests rerun. Runtime source is unchanged since the full run.
Lint, whitespace and required local parser comparison pass; 28 database parses change
with no new exceptions. No AI strength claim is made.

Only a new template module, its registration lines, a new test file and this report
changed. BACKLOG.md, results/residual_batch/, and Claude's branches were not edited.
Branch `codex/cards-4` is independent of rounds 1–3. GitHub API access still blocks
PR creation, remote CI verification and merge. Rebase onto current main immediately
before creating the PR, rerun relevant checks if its source has changed, and merge
only after green CI.
