# Codex card-coverage round 1: graveyard-to-library targets

Branch: `codex/cards-1`. Baseline: `57a1c523c5b0ee5fbf3fe673a1049a098fd2952c`.
Candidates were selected from a fresh complete offline `mtgsim.database_coverage`
re-parse. The ignored database is shared read-only with the isolated worktree.

## Implementation and ownership

`mtgsim/cx_graveyard.py` adds complete-clause templates for placing one target
card from your graveyard on top of your library:

- Any ordinary card, or a permanent card.
- Explicit card types and two-type unions.
- Mandatory and optional single targets.

The templates reuse `grave_library_top` and `graveyard_card`, including the
existing exact-identity/generation checks. They add no new targeting category,
handler, trigger parser, activated cost, counter, token, combat or Aura logic.
The only shared source edit is this module's three registration lines at the end
of `mtgsim/cards/__init__.py`. `BACKLOG.md`, `results/residual_batch/`, Claude's
branches and existing family modules are unchanged.

Non-target selections, subtype predicates, multiple targets, relational “other”
targets and other players' graveyards are deliberately left ignored. Broader
mechanic families are not claimed complete. Example cards already fully matched
before this round are excluded from the selection.

## Behavioral evidence

`tests/test_cx_graveyard.py` contains sixteen behavior tests covering:

- Exact type/controller filters and inclusive unions.
- Physical duplicate selection, ownership, top-of-library placement and next draw.
- Illegal/stale targets and cards leaving then re-entering a graveyard.
- Optional zero targets, required targets and resolution legality.
- Normal casting, automatic targets, explicit choices and the existing ETB path.
- Unsupported qualifier wording staying visible.

Reproduce from this worktree:

```sh
python3 -m mtgsim.database_coverage --save results/codex_round_1/after --progress --top 30
python3 -m unittest tests.test_cx_graveyard -q
python3 scripts/lint.py
python3 scripts/parse_diff.py local --show 5
```

Measurements and full-suite outcomes are recorded in `validation.json` and
`coverage-delta.json`. Local long-running validation uses a temporary Python
regex-cache capacity of 32,768, without changing production defaults or assertions.
Parser coverage is separate from complete Magic rules correctness.

## Measured result

The before/after censuses compare all **34,129 entries** through the same CardDB
lookup and coverage classifier: **10 cards improve**, including **9 newly full
matches**, with zero parser exceptions and zero status regressions. Full matches
increase from **12,054 to 12,063**; 231 recorded simplifications are unchanged.
Runo Stromkirk remains partial with its unrelated clauses visible.

The final complete suite executes **1,579 tests** across 119 modules: **1,578 pass**,
one optional test skips, and no tests fail. Discovered and executed IDs match
exactly. Runtime/test hashes remain unchanged after the run. Lint has zero findings;
`parse_diff.py local --show 5` finds the same ten changed cards and zero new parser
exceptions. The initial standalone-import failure was fixed by deferring the
Effect import, followed by this complete final rerun.

Both HeuristicAI and BaselineAI plan and cast an actual offline-database Reclaim
and preserve the selected physical card. This is a functional comparison, not a
win-rate or pilot-strength claim.

## Delivery gate

One PR is required for this round; it must target `main`, be rebased onto current
`main` before opening, and merge only after CI is green. No direct push to `main`
or `claude/*` is permitted. If the GitHub API is unavailable, a pushed feature
branch does not count as a created PR or green CI. The delivery state is recorded
separately in `delivery.json`.
