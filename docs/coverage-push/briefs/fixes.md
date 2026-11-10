# Lane: fixes (you are `sim-fixes`, branch prefix `claude/fixes`, worktree ~/mtg-worktrees/fixes)
Read COMMON.md first (including "GitHub issues").

You fix cards that count as fully supported but play wrong, across ALL lanes. Work list, in order:
1. Open issues labelled `counted-full-but-wrong` (`gh issue list -R andjalis/mtg-simulator --label counted-full-but-wrong
   --state open`), oldest first, skipping ones a teammate already links an open PR to.
2. Then `follow-up` issues whose lane was retired (lane:abil, lane:trig, lane:mech, lane:tokens, lane:counters,
   lane:simplify, lane:gzones, lane:gplayers): relabel them `lane:fixes` when you take one.
Each fix: reproduce it first in a small game test (the bug must fail before your change), fix it in the owning
module with the smallest correct change, and say "Fixes #n". If the right fix is "this card can't be supported
yet", make the card honestly partial or simplified instead. Retired lanes' briefs and handoff notes (status/) explain
their code. One issue per PR unless several share a cause.
