#!/usr/bin/env python3
"""Local pilot-gate runner: runs the pilot gate locally, alongside the GitHub "Pilot gate" job, for andjalis/mtg-simulator PRs.

    local_gate.py <worker-name>      # e.g. gate1; run 2 of them for parallelism

Loops forever: picks the oldest open PR whose current head has no local gate result yet (claims it so another
worker skips it), checks out GitHub's merge ref (PR merged into current base), runs scripts/pilot_gate.py --fast
through the heavy queue, and posts/updates the PR comment marked <!-- pilot-gate --> with the head SHA.
Each round it also cancels queued duplicate Tests runs (push runs on PR branches, which repeat the PR's own run)."""
import json, os, subprocess, sys, time
from pathlib import Path

REPO = "andjalis/mtg-simulator"
SKIP = {91, 92}
HOME = Path.home()
WT = HOME / "mtg-worktrees" / sys.argv[1]
CLAIMS = HOME / "mtg-worktrees" / ".gate_claims"
LOG = HOME / "mtg-worktrees" / "gate.log"


def sh(*cmd, cwd=None, check=True):
    return subprocess.run(cmd, cwd=cwd, check=check, text=True, capture_output=True).stdout.strip()


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {sys.argv[1]}: {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def gated(pr, head):
    bodies = sh("gh", "api", f"repos/{REPO}/issues/{pr}/comments", "--paginate", "--jq",
                '.[] | select(.body | startswith("<!-- pilot-gate -->")) | .body')
    return f"head `{head[:9]}`" in bodies


def post(pr, text):
    cid = sh("gh", "api", f"repos/{REPO}/issues/{pr}/comments", "--paginate", "--jq",
             '.[] | select(.body | startswith("<!-- pilot-gate -->")) | .id').splitlines()
    f = WT.parent / f".gate-{sys.argv[1]}.md"
    f.write_text(text[:60000])
    if cid:
        sh("gh", "api", "-X", "PATCH", f"repos/{REPO}/issues/comments/{cid[-1]}", "-F", f"body=@{f}")
    else:
        sh("gh", "pr", "comment", str(pr), "--repo", REPO, "--body-file", str(f))


def cancel_redundant():
    runs = json.loads(sh("gh", "run", "list", "--repo", REPO, "--limit", "150", "--json",
                         "databaseId,status,workflowName,event,headBranch"))
    for r in runs:
        if r["status"] not in ("queued", "pending", "waiting"):
            continue
        # only exact duplicates: a push run on a PR branch repeats that PR's pull_request run
        if r["workflowName"] == "Tests" and r["event"] == "push" and r["headBranch"] != "main":
            sh("gh", "run", "cancel", str(r["databaseId"]), "--repo", REPO, check=False)


def one_round():
    prs = json.loads(sh("gh", "pr", "list", "--repo", REPO, "--state", "open", "--json",
                        "number,headRefOid,baseRefOid,isDraft"))
    CLAIMS.mkdir(exist_ok=True)
    for p in sorted(prs, key=lambda p: p["number"]):
        n, head = p["number"], p["headRefOid"]
        if n in SKIP or p["isDraft"]:
            continue
        claim = CLAIMS / f"{n}-{head[:9]}"
        try:
            claim.open("x").close()           # atomic: only one worker gates this head
        except FileExistsError:
            continue
        if gated(n, head):
            continue
        sh("git", "fetch", "-q", "origin", f"+refs/pull/{n}/merge:refs/gate/{n}", cwd=WT, check=False)
        merge = sh("git", "rev-parse", "-q", "--verify", f"refs/gate/{n}", cwd=WT, check=False)
        if not merge or sh("git", "rev-parse", f"{merge}^2", cwd=WT, check=False) != head:
            log(f"#{n}: GitHub merge ref not ready (conflict or stale); retry later")
            claim.unlink()
            continue
        base = sh("git", "rev-parse", f"{merge}^1", cwd=WT)
        tracked = sh("git", "diff", "--name-only", base, merge, cwd=WT).splitlines()
        if any(f == ".venv" or f.startswith((".venv/", "results/pilot_gate/")) for f in tracked):
            post(n, f"<!-- pilot-gate -->\n**Local gate (lead's Mac) for head `{head[:9]}`: NOT RUN.** The PR tracks `.venv` or "
                    "`results/pilot_gate/`; checking it out would delete the gate's environment. Remove them "
                    "(`git rm --cached ...`), push, and it will be gated automatically.")
            log(f"#{n}: skipped, tracks .venv/results")
            continue
        sh("git", "checkout", "-q", "--detach", merge, cwd=WT)
        log(f"#{n}: gating head {head[:9]} (merge {merge[:9]} on base {base[:9]})")
        start = time.time()
        r = subprocess.run([str(HOME / "mtg-worktrees/bin/heavy"), ".venv/bin/python", "scripts/pilot_gate.py",
                            "--base", base, "--fast"], cwd=WT, text=True, capture_output=True)
        verdicts = sorted((WT / "results/pilot_gate").glob("*/verdict.md"), key=os.path.getmtime)
        body = verdicts[-1].read_text() if verdicts and os.path.getmtime(verdicts[-1]) > start else \
            f"# Pilot gate: ERROR\n\n```\n{(r.stdout + r.stderr)[-3000:]}\n```\n"
        post(n, f"<!-- pilot-gate -->\n**Local gate (lead's Mac) for head `{head[:9]}`**, PR merged into base `{base[:9]}`, "
                f"{time.time() - start:.0f}s.\n\n{body}")
        log(f"#{n}: posted ({body.splitlines()[0]})")
        return True
    return False


if __name__ == "__main__":
    while True:
        try:
            cancel_redundant()
            if not one_round():
                time.sleep(60)
        except Exception as e:  # keep running; GitHub hiccups are common
            log(f"error: {e}")
            time.sleep(60)
