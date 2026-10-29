# Codex card-coverage round 6

`mtgsim/cx_selection.py` adds general library-top selections that keep a fixed
number, or all cards of known types/subtypes, and put the remainder on the bottom.
It reuses `dig`, physical-card zone tracking, the existing selection policy and
shared X amount handling. Type unions, subtype filters and several equivalent
sentence layouts are supported. Graveyard remainders, battlefield destinations,
unknown qualifiers and independently variable keep counts stay unsupported.

A tiny shared-parser bug fix protects supported paid-X sequences before the legacy
printed-mana-value substitution. The hook applies only to X-cost instants/sorceries;
all normalization and effect construction live in the new module. Enshrined Memories
now examines the paid X, not its printed mana value. Flash of Insight's ordinary
hand cast also uses paid X; its special flashback cost remains a genuine gap.
Unsupported activated costs retain readable text and no new internal marker leaks.

Fresh 34,129-entry censuses against main `b8d12a6`: **18 cards improve; 12 become
fully template-matched**. Full matches rise from 12,557 to 12,569; partials fall
from 21,330 to 21,318. Recorded simplifications stay at 242. Zero parser exceptions,
status regressions or CXSELECTION marker leaks across the complete after census.
Template recognition is not complete Magic rules verification.

New full matches include Goblin Ringleader, Enlistment Officer, Grave Defiler,
Sylvan Messenger, Enshrined Memories, Lair Delve, Merfolk Wayfinder, Experimental
Augury and Prophetic Bolt. coverage-delta.json includes all changed residuals.
Remaining clauses on Garruk, Marina, See the Truth and Witness the Future stay
visible. Already covered effects are not todos. Nineteen raw database parses change:
Flash of Insight's behavior improves without changing its partial classification.

Thirteen new tests cover exact physical duplicates, bounded windows, bottom ordering,
all matching types, subtypes, no-match/empty libraries, owner isolation, no accidental
draw/scry/search/mill events, X=0, short libraries, unsupported descriptors and paid
X with different printed mana values. Both pilots cast the synthetic paid-X selection.
Separate actual-card checks in policy-smoke.json prove both pilots' ordinary Flash of
Insight cast selects an exact card inside the paid-X window. These are functional
checks, not strength measurements.

Full suite: **1,631 pass, one optional skip**, all 1,632 discovered tests executed.
Lint, whitespace and required local parser comparison pass, with zero new exceptions.
Verification hashes identify the final runtime and test source. Earlier validation
was repeated after correcting optional-you normalization and guarding paid-X protection.
No AI, trigger, counter, token, combat or activated-cost code changed.

Branch `codex/cards-6` is independent of rounds 1–5. GitHub API access blocks PR
creation, remote CI verification and merge. Rebase onto current main immediately
before creating its PR, rerun checks if source changes, and merge only after green
CI. BACKLOG.md, results/residual_batch/, and Claude's branches were not edited.
