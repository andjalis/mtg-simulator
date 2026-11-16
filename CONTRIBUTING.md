# Contributing and merging

Work lands through pull requests. Card threads (and any other author) open a PR and move on to the next
task; one **integrator** merges green PRs in batches. Nobody waits on CI for their own PR.

## Checks

| Check | When | Cost | What it covers |
| --- | --- | --- | --- |
| `python3 scripts/fast_check.py` | every push and PR (CI job `fast check`) | about 2 min on CI | pyflakes, every card parsed (none may raise), short seeded games, all test modules except the slow ones |
| `parse-diff` | every PR | a few minutes | every card parsed with the base and head code; lists cards whose parse changed, fails if one starts raising |
| Nightly (`nightly.yml`) | 03:17 UTC daily and on demand | about 20 min per Python version | the slow test modules, the full suite on Python 3.10, 3.13 and 3.14, every card parsed |

These CI checks remain required. Local verification depends on what changed, as described below.
A test module that grows past a minute goes into `SLOW_TESTS` in `scripts/fast_check.py`, so it
runs nightly instead of on every PR.

### Local verification

Choose checks that can detect a plausible failure caused by the change:

| Change | Local verification |
| --- | --- |
| Documentation only | Review the diff and changed links/references; run `git diff --check`. No runtime suite. |
| Removal of unused scratch scripts or historical reports/results | Check references in code, tests, CI and docs, including indirect loaders or globs. Run `git diff --check`; add lint or a small import/startup check when executable files are involved. No full suite unless a runtime dependency or behavior change is discovered. |
| Bounded engine, AI, card or parser change | Run focused behavior tests and related regressions during editing. Run `python3 scripts/fast_check.py` once the batch is ready, before pushing. For parser changes, also run `python3 scripts/parse_diff.py local --show 5` and review the changed cards. |
| Broad engine or shared-infrastructure change; integration of multiple branches | Run relevant focused checks while editing, then the full suite on the completed change or integrated batch, plus the fast check and parse-diff where applicable. |

Build the card database with `python3 -m mtgsim.build_carddb` if needed for the selected checks.
Use `--no-lint` for the fast check only when pyflakes is unavailable, and report that limitation.
Refresh coverage at capability-batch completion when required by the task, rather than after
each small edit. AI changes still need the behavioral measurements specified in `AGENTS.md`.

Reuse successful checks for the same relevant code and inputs. Do not rerun the full suite,
whole-database parse-diff or coverage census after an unrelated documentation edit or just to
report completion again. After a relevant code, data, test or dependency change, rerun affected
checks; broaden them for failures or unresolved concerns. When checks overlap, report their
existing evidence instead of repeating them solely because another workflow phase started.
Reserve heavy local runs on `.agents/STATUS.md` when other agents share the machine.

Record the commands and outcomes, identify the tested revision or batch, and state checks not
run. This policy does not bypass required CI, nightly checks or explicit task acceptance checks.

## For authors

1. Branch from `main`, make the change, and run the applicable local checks above.
2. Open the PR (draft is fine) and note what changed in the PR body. Do not wait for CI or poll it.
3. If CI fails later, the integrator or a notification will send it back; fix on the same branch.
4. Keep PRs in your lane's files (see below) so batches merge without conflicts.

### Adding a template module (no shared line to edit)

A new mechanic module (`mtgsim/<name>.py` exporting `EFFECT_PATTERNS`, `SUBS`, `TRIGGERS`, `KEYWORDS`, ...) joins the
parser through its own registration file, not through a line in `mtgsim/cards/__init__.py`: add
`mtgsim/cards/registry/NNNN_<name>.py` that imports the module (`from ... import <name> as _<name>`) and names what
it adds (`EFFECT_PATTERNS = _<name>.EFFECT_PATTERNS`, likewise `SUBS`, `TRIGGERS`, `KEYWORDS`, `PRIORITY_PATTERNS`,
`FACE_LINE_PARSERS`). Files load in filename order and earlier patterns win, so take the next free number above
the highest one (they step by ten; two branches picking the same number is fine, the name breaks the tie). A
whole-line parser that used to be wired into `cards/face_lines.py` (`if _x.parse_line(line, st): return None`)
goes in the same file as `LINE_HOOKS = {"keyword": (_<name>.parse_line,)}`; the stages (`special`, `ward`,
`static`, `keyword`) are listed in `face_lines.LINE_HOOK_STAGES`. A new `mtgsim/engine/kinds/<name>.py` needs no
import line at all: `engine/resolve.py` imports every kind module not yet loaded. `mtgsim/cards/registry/__init__.py`
documents the fields; `tests/test_registry.py` checks names and fields.

Converting an older PR that still appends to the tail of `cards/__init__.py` or `engine/kinds/__init__.py`: take
`main`'s version of that file, then move the PR's appended `from .. import X as _X` / `_EFFECT_PATTERNS += ...`
lines into a new registry file as above (drop the `engine/kinds/__init__.py` import line). Lines appended below
`_registry.load_all(...)` still work during the transition, so keeping them there is an acceptable quick fix.

## For the integrator

Once or twice a day, or when several PRs are open:

1. List open PRs whose `fast check` is green (`parse-diff` must not have failed either).
2. Order them so PRs touching the same files go one after another; independent ones can go together.
3. Merge each into `main` (squash). After each merge that touches shared files, update the next
   PR's branch (`update_pull_request_branch`) and wait for its fast check again.
4. Skip a PR whose check is red or pending and leave it for its author; do not re-run or bypass checks.
5. Check the latest nightly run. If it is red, find the merge since the last green night that broke it,
   and fix or revert it before merging more card rounds.

A PR that changes `mtgsim/data` builders, the parser, or the engine for a new mechanic should get a
look at the parse-diff list before merging; pure card rounds do not need a review beyond green checks.

mtg-gauntlet has no Actions minutes until 1 November 2026: run its tests locally and say so in the PR.
