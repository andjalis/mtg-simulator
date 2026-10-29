# Codex card-coverage round 5

`mtgsim/cx_exile.py` adds immediate single-permanent blink wording through the
existing flicker handler and validated permanent selectors. It covers creature/type
unions, nontoken permanents, self blink, optional single targets and the singular
"their owner's control" wording. Two-sentence normalization is used only after the
selector validates, so unsupported clauses retain their original readable text.

Fresh 34,129-entry censuses against main `b8d12a6`: **20 cards improve; 16 become
fully template-matched**. Full matches rise from 12,557 to 12,573; partials fall
from 21,330 to 21,314. The 242 recorded simplifications are unchanged. Zero parser
exceptions or status regressions. Full template recognition is not complete rules
verification. `coverage-delta.json` records all changed cards and residual clauses.

New full matches include Blur, Flicker, Flicker of Fate, Against All Odds,
Aethergeode Miner, Felidar Guardian, Scrollshift and Teleportation Circle. The
remaining clauses on Emiel, Hallowed Respite and Soulherder concern counters or
conditional riders; Xho Cai still lacks its next-noncreature-spell cost reduction.
Already full cards in candidate-reparse.json are explicit controls, not todos.

Thirteen new tests prove physical identity, a new battlefield object, reset state,
owner/controller distinctions for stolen permanents, token disappearance, duplicate
isolation, stale-target rejection, optional targets, source exclusion and preservation
of unsupported selectors. Existing energy-cost payment is exercised without changing
cost code. Blur is cast with explicit targets by both pilots, then blinks and draws.
This is engine behavior evidence, not a claim that both pilots automatically choose
blink targets or a strength measurement.

Caster-control returns such as Cloudshift remain unsupported by these new templates:
a stolen creature must return under the correct controller, and the reused handler
returns under its owner. Multiple targets, tapped returns, transformed returns and
unsupported ownership selectors also stay visible. These are genuine residual gaps.

Full suite: **1,631 pass, one optional skip**, all 1,632 discovered tests executed.
Lint, whitespace and required local parser comparison pass; 20 database parses change
with zero new exceptions. No engine, AI, trigger, counter, token or activated-cost
modules changed. BACKLOG.md, results/residual_batch/, and Claude's branches were untouched.

Branch `codex/cards-5` is independent of rounds 1–4. GitHub API access blocks PR
creation, remote CI verification and merge. Rebase onto current main immediately
before creating the PR, rerun checks if its source changes, and merge only after
green CI.
