# Codex card-coverage round 3

`mtgsim/cx_milling.py` extends general mill templates with larger English counts,
paid X quantities and explicit selection wording for cards milled this way.
It reuses existing `mill` and `mill_pick` effects, the stack's X amount and
per-resolution physical-card tracking. No engine, targeting, AI, trigger, token,
counter or activated-cost implementation changes.

Fresh 34,129-entry censuses against main `b8d12a6`: **13 cards improve; 4 become
fully template-matched**. New full matches: Bramble Familiar // Fetch Quest,
Fractured Sanity, Jace Beleren, Psychic Drain. Full matches rise from 12,557 to
12,561; partials fall from 21,330 to 21,326. The 242 simplifications are unchanged;
zero parser exceptions and zero status regressions. Template recognition does not
prove full Magic rules correctness.

`coverage-delta.json` records before/after clauses across all faces. Remaining
gaps stay visible, including Archive Trap's alternative-cost condition, Increasing
Confusion's graveyard-cast replacement, Vivien's sacrifice-dependent search,
Startled Awake's return/transformed face and Summons of Saruman's special flashback
cost and cast permission. Already full mills are not parser todos. Claude's token,
counter and trigger gaps are left for Claude; incidental improvements use the
same shared effect templates and introduce no work in those families.

Seventeen new tests cover exact card identities and counts, both/all players,
short libraries, X=0, paid X, target restrictions, union filtering, optional bounds,
failed selections and separation from previous mill resolutions. HeuristicAI plans
and casts Psychic Drain; BaselineAI's existing mill-target policy declines it.
Explicit legal targets still cast and resolve correctly with BaselineAI. No pilot
strength claim or AI behavior change is made.

Full suite: **1,635 pass, one optional skip**, all 1,636 discovered tests executed.
Lint, whitespace checks and required local parser comparison pass. Thirteen raw
database parses change with zero new exceptions. Temporary runners enlarge the
regex cache only during verification; production configuration is unchanged.

Branch `codex/cards-3` is independent of rounds 1 and 2. GitHub API access blocks
PR creation, remote CI verification and merge. Rebase onto current main immediately
before creating its PR, rerun checks if source changes, and merge only after green
CI. BACKLOG.md, results/residual_batch/, and Claude's branches were not edited.
