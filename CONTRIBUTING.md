# Contributing and merging

Work lands through pull requests. Card threads (and any other author) open a PR and move on to the next
task; one **integrator** merges green PRs in batches. Nobody waits on CI for their own PR.

## Checks

| Check | When | Cost | What it covers |
| --- | --- | --- | --- |
| `python3 scripts/fast_check.py` | every push and PR (CI job `fast check`) | about 2 min on 4 cores | pyflakes, a 1-in-10 sample of the card database parsed (must not raise), short seeded games, all test modules except the slow ones |
| `parse-diff` | every PR | a few minutes | every card parsed with the base and head code; lists cards whose parse changed, fails if one starts raising |
| Nightly (`nightly.yml`) | 03:17 UTC daily and on demand | about 6 min per Python version | the slow test modules, the full suite on Python 3.10, 3.13 and 3.14, every card parsed |

Run `python3 scripts/fast_check.py` (add `--no-lint` without pyflakes) before pushing; build the card
database first with `python3 -m mtgsim.build_carddb`. A parser change should also run
`python3 scripts/parse_diff.py local --show 5`. A test module that grows past a minute goes into
`SLOW_TESTS` in `scripts/fast_check.py`, so it runs nightly instead of on every PR.

## For authors

1. Branch from `main`, make the change, run the fast check.
2. Open the PR (draft is fine) and note what changed in the PR body. Do not wait for CI or poll it.
3. If CI fails later, the integrator or a notification will send it back; fix on the same branch.
4. Keep PRs in your lane's files (see below) so batches merge without conflicts.

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
