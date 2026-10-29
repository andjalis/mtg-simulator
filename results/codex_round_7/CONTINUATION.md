# Card-coverage continuation handoff

Requested future start: **2026-10-29 at 11:12:31 UTC**, 5.5 hours after the
scheduling request was handled. **No cloud task was scheduled:** this session
exposes no scheduling or planned-task creation tool. This file is a ready-to-use
task prompt and handoff, not a scheduled automation.

Continue card-coverage rounds in andjalis/mtg-simulator. Read current AGENTS.md first.
Fetch current main and preserve any existing agent work. Rounds 1–7 are independent
Codex branches, `codex/cards-1` through `codex/cards-7`, each with its own report in
`results/codex_round_N/`. Check their delivery.json files and current remote state.
The GitHub API was blocked by the cloud network policy. A saved environment draft
adds only api.github.com; it must be reviewed and published in environment settings
to take effect. Git fetch/push works, but is not evidence that PR/CI access works.

When API access is available, rebase each round onto current main immediately
before opening its PR. Preserve all module registrations at the end of
mtgsim/cards/__init__.py. Run the relevant checks after conflicts or source changes.
Create one PR per round against main, attach each actual PR URL to the task,
verify remote CI is green and merge through that PR. Do not push directly to main
or infer green CI from local tests. Reports describe historical measured bases;
refresh results if rebasing changes their claims materially.

Then start codex/cards-8 from fresh main. Re-parse the complete offline database
with python3 -m mtgsim.database_coverage. Re-parse candidate cards before choosing
work, and exclude already covered cards/effects from todos. The accompanying
continuation-candidates.json records only residual clauses on reviewed cards that
remain partial with all seven rounds applied. It is a candidate shortlist, not an
exhaustive ranking or a promise that a whole card can be implemented at once.

Codex owns graveyard/recursion/mill, exile/blink/linked exile/foretell/suspend/adventure,
library search/scry/surveil/shuffle, copies/populate/clones, spell reductions and
alternative/additional costs, and planeswalker loyalty abilities. Claude owns
triggers, counters, tokens, auras/equipment/vehicles, combat rules, static anthems,
sacrifice and activated-ability costs. Leave mixed cards to the owner of their
largest unmatched clause. Reuse foundations and add general templates, not card names.

New work belongs in mtgsim/cx_<family>.py and tests/test_cx_<family>.py. Append each
module's registration on its own lines. Do not edit another family's module except
for tiny bug fixes. Do not edit BACKLOG.md or results/residual_batch/. Record each
new round in results/codex_round_N/. Never push claude/* branches.

Prove engine behavior, including exact physical cards, target legality, owner vs
controller, stale references, zone changes and failure cases. Keep unsupported
clauses readable. Run the full suite with the offline DB present, python3
scripts/lint.py, and python3 scripts/parse_diff.py local --show 5 before pushing.
Use existing platform Git authentication without extracting credentials.

Verification notes for this workspace: /workspace/mtg-simulator/.venv/bin/python3
provides Python 3.12 and pyflakes. The offline database is ignored; worktrees link
to /workspace/mtg-simulator/mtgsim/data/cards.sqlite3. Temporary verification runners
raise re._MAXCACHE to 32768 to avoid template-regex cache churn, without changing
production. Full-suite runners verify the exact discovered/executed test-ID multiset.
Combined integration evidence, when finalized, is recorded separately from each
round's individual measurements and does not represent merged or CI-approved work.
