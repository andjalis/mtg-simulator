# Codex card-coverage round 2

General library-top search templates in `mtgsim/cx_library.py` reuse the existing
search effect, tutor policy, physical-card zones and shuffle implementation.
Known type filters, explicit unions, optional searches and unrestricted single-card
searches are supported. Unknown qualifiers and multiple-card selections remain
visible gaps. No engine, AI, trigger or activated-cost modules changed.

Fresh 34,129-entry offline censuses: **6 cards improve; 5 become fully template-matched**.
Full matches rise from 12,427 to 12,432; partials fall from 21,468 to 21,463.
There are 234 recorded simplifications and zero parser exceptions before and after.
No status regressions. Full template matching measures recognition, not complete
Magic rules correctness.

Newly full: Bringer of the Black Dawn, Cruel Tutor, Imperial Seal, Vampiric Tutor,
and Worldly Tutor. Liliana Vess's library search improves through the existing
loyalty path; its graveyard-to-battlefield ultimate remains ignored. These are
outcomes of shared templates, not per-card exceptions. Already full tutors such
as Mystical Tutor and Enlightened Tutor are not parser todos.

Eleven new tests cover exact duplicate identity, the next draw, candidate filters,
shuffle ordering, unsuccessful and empty searches, opponent-zone isolation,
unsupported filters, and ordinary casting by both HeuristicAI and BaselineAI.
The full suite ran all 1,622 discovered tests: **1,621 pass, one optional skip**.
Lint and the required local parser comparison pass; six database parses change,
with zero new exceptions. This is functional pilot evidence, not a strength claim.
See `validation.json`, `coverage-delta.json`, and `parse-diff.md`.

Code and tests are isolated on `codex/cards-2`, based on main commit
`16f8132`. Round 1 is independent and is not a dependency. PR creation, remote CI
verification and merge are blocked by GitHub API access. Rebase onto current main
immediately before creating the PR and rerun checks if its source has changed.
Never merge without green CI. BACKLOG.md, results/residual_batch/, and Claude's
branches were not edited.

Integration follow-up: the unsupported multi-card test now uses a different-name
restriction, preserving its purpose after round 4 adds ordinary bounded searches.
All eleven focused tests pass again; runtime source is unchanged.
