"""Report versioned scenario evidence separately from template recognition.

    python3 -m mtgsim.behavior_coverage --run --save results/behavior-coverage
    python3 -m mtgsim.behavior_coverage --ledger results/behavior-coverage/ledger.json --save results/behavior-review

Requires the offline database and a source checkout containing tests. Only explicitly
mapped scenarios count. This bounded suite cannot certify complete card support.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
import unittest

from .carddb import CardDB
from .coverage import _faces, card_coverage
from .provenance import ROOT, atomic_json, digest, file_hash, output_lock, runtime_identity

CAPABILITIES = ROOT / "rules" / "capabilities.json"
SCENARIOS = ROOT / "rules" / "scenarios.json"
OUTCOMES = ("pass", "fail", "error", "not_run", "stale")


def load_catalogs(capabilities=CAPABILITIES, scenarios=SCENARIOS):
    catalog, manifest = json.loads(Path(capabilities).read_text()), json.loads(Path(scenarios).read_text())
    if catalog.get("schema") != 1 or manifest.get("schema") != 1 or catalog["scope"] != manifest["scope"]:
        raise ValueError("unsupported or inconsistent catalog schema/scope")
    caps = {c["id"]: c for c in catalog["capabilities"]}
    ids = [s["id"] for s in manifest["scenarios"]]
    tests = [s["test"] for s in manifest["scenarios"]]
    if len(caps) != len(catalog["capabilities"]) or len(set(ids)) != len(ids) or len(set(tests)) != len(tests):
        raise ValueError("duplicate capability, scenario or test mapping")
    for c in caps.values():
        if c["state"] not in ("implemented_subset", "partial", "absent", "unassessed"):
            raise ValueError("unknown capability support state")
        if any(dep not in caps for dep in c["requires"]):
            raise ValueError("unknown capability dependency")
    def visit(key, path):
        if key in path:
            raise ValueError("cyclic capability dependency")
        for dep in caps[key]["requires"]:
            visit(dep, path | {key})
    for key in caps:
        visit(key, set())
    for s in manifest["scenarios"]:
        if not s["capabilities"] or any(c not in caps for c in s["capabilities"]):
            raise ValueError("unknown or missing scenario capability")
        if not s["test"].startswith("tests.") or type(s["version"]) is not int or s["version"] < 1:
            raise ValueError("invalid scenario test/version")
        if not s.get("expected_source", {}).get("reference"):
            raise ValueError("scenario expectation needs a source")
    return catalog, manifest


def identity(catalog, manifest):
    return digest({"runtime": runtime_identity(), "catalog": catalog, "manifest": manifest,
                   "tests": {p.relative_to(ROOT).as_posix(): file_hash(p)
                             for p in sorted((ROOT / "tests").rglob("*.py"))}})


def execute(manifest, run_identity, folder):
    """Run each mapped unittest exactly once and retain its output as evidence."""
    folder = Path(folder)
    traces = folder / "traces"
    traces.mkdir(parents=True, exist_ok=True)
    records = []
    for scenario in manifest["scenarios"]:
        output = io.StringIO()
        suite = unittest.defaultTestLoader.loadTestsFromName(scenario["test"])
        count = suite.countTestCases()
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
        outcome = ("error" if count != 1 or result.errors or result.unexpectedSuccesses else
                   "not_run" if result.skipped or result.expectedFailures else
                   "fail" if result.failures else "pass")
        # A filename derived from the ID hash cannot escape the output directory.
        trace = traces / (digest(scenario["id"])[:20] + ".txt")
        trace.write_text(output.getvalue(), encoding="utf-8")
        records.append({"schema": 1, "scenario_id": scenario["id"],
                        "scenario_hash": digest(scenario), "run_identity": run_identity,
                        "outcome": outcome, "engine": "builtin", "tests_run": result.testsRun,
                        "trace": trace.relative_to(folder).as_posix(), "trace_sha256": file_hash(trace)})
    atomic_json(folder / "ledger.json", {"schema": 1, "records": records})
    return records


def evaluate(manifest, records, run_identity, folder):
    """Missing/stale/failed evidence stays visible; duplicates are rejected."""
    indexed = {}
    known = {s["id"] for s in manifest["scenarios"]}
    for row in records:
        key = row["scenario_id"]
        if key in indexed:
            raise ValueError(f"duplicate scenario evidence: {key}")
        if key not in known:
            raise ValueError(f"evidence for a removed/unknown scenario: {key}; use its original scope")
        indexed[key] = row
    folder = Path(folder).resolve()
    rows = []
    for scenario in manifest["scenarios"]:
        record = indexed.get(scenario["id"])
        outcome = "not_run"
        if record is not None:
            outcome = record.get("outcome")
            if outcome not in OUTCOMES or record.get("schema") != 1:
                raise ValueError("invalid evidence schema/outcome")
            trace = (folder / record.get("trace", "")).resolve()
            if folder not in trace.parents:
                raise ValueError("evidence trace must be inside its run folder")
            if (record.get("run_identity") != run_identity or record.get("scenario_hash") != digest(scenario)
                    or record.get("engine") != "builtin" or not trace.is_file()
                    or not record.get("trace_sha256") or file_hash(trace) != record["trace_sha256"]):
                outcome = "stale"
        rows.append({**scenario, "outcome": outcome})
    return rows


def evidence_status(rows, *, complete=False, capabilities_supported=True):
    counts = Counter(r["outcome"] for r in rows)
    if counts["fail"] or counts["error"]:
        return "has_failures"
    if rows and complete and capabilities_supported and counts["pass"] == len(rows):
        return "scoped_suite_passes"
    return "some_scenarios_pass" if counts["pass"] else "not_measured"


def card_row(card, scenarios, catalog):
    """Join actual parsed metadata with bounded direct/capability scenario evidence."""
    requirements = {"zones.object_identity"} if any(c["id"] == "zones.object_identity" for c in catalog["capabilities"]) else set()
    known = {c["id"] for c in catalog["capabilities"]}
    for face in _faces(card):
        if not face.is_land and "actions.atomic" in known:
            requirements.add("actions.atomic")
        if "continuous.pt_keywords" in known and (face.is_creature or face.aura_flags or
                any(a.kind == "animate" for a in face.activated)):
            requirements.add("continuous.pt_keywords")
        if face.legendary:
            requirements.add("sba.legend")
        if face.equip_cost is not None:
            requirements.add("stack.equip")
        effects = list(face.spell_effects) + [e for t in face.triggers for e in t.effects]
        effects += [e for a in face.activated for e in a.effects]
        if any(e.target in ("creature", "creature_mine", "creature_pw") for e in effects):
            requirements.add("targets.creature")
        if any(e.kind in ("destroy", "wrath", "wrath_pw", "bounce") for e in effects):
            requirements.add("removal.core")
        if any(e.kind == "regenerate" for e in effects):
            requirements.add("replacement.supported")
        if face.gy_activated or face.keywords & {"persist", "undying"} or any(
                e.kind in ("return_self_gy", "gy_move", "reanimate_one") for e in effects):
            requirements.add("graveyard.return")
    caps = {c["id"]: c for c in catalog["capabilities"]}
    pending = list(requirements)
    while pending:
        for dep in caps.get(pending.pop(), {}).get("requires", []):
            if dep not in requirements:
                requirements.add(dep)
                pending.append(dep)
    direct = [s for s in scenarios if card.name in s["direct_cards"]]
    related = [s for s in scenarios if requirements.intersection(s["capabilities"])]
    unique = {s["id"]: s for s in direct + related}
    gaps = sorted(c for c in requirements if c not in caps or caps[c]["state"] != "implemented_subset")
    return {"name": card.name, "template_status": card_coverage(card).status,
            "required_capabilities": sorted(requirements), "declared_gaps": gaps,
            "current_direct_scenarios": [s["id"] for s in direct if s["outcome"] == "pass"],
            "current_capability_scenarios": [s["id"] for s in related if s["outcome"] == "pass"],
            "failures": [s["id"] for s in unique.values() if s["outcome"] in ("fail", "error")],
            "untested_requirements": sorted(c for c in requirements if not any(
                c in s["capabilities"] and s["outcome"] == "pass" for s in related)),
            "requirements_complete": False,
            "unclassified_requirements": ["Rules beyond the declared capability subsets are not assessed"],
            "evidence_status": evidence_status(list(unique.values()), capabilities_supported=not gaps)}


def build_report(db, catalog, manifest, scenarios, run_identity):
    if db._all is None:
        raise ValueError("offline database required; run python3 -m mtgsim.build_carddb")
    cards = []
    for (name,) in db._all.execute("SELECT name FROM cards ORDER BY key"):
        try:
            row = card_row(db.get(name), scenarios, catalog)
            row["name"] = name
        except Exception as exc:
            row = {"name": name, "template_status": "parse_error", "evidence_status": "not_measured",
                   "error": f"{type(exc).__name__}: {exc}"}
        cards.append(row)
    capabilities = []
    for capability in catalog["capabilities"]:
        related = [s for s in scenarios if capability["id"] in s["capabilities"]]
        capabilities.append({**capability, "required_scenarios": len(related),
                             "outcomes": dict(Counter(s["outcome"] for s in related)),
                             "evidence_status": evidence_status(related, complete=True,
                                 capabilities_supported=capability["state"] == "implemented_subset")})
    by_id = {c["id"]: c for c in capabilities}
    def dependency_passes(key):
        cap = by_id[key]
        return cap["evidence_status"] == "scoped_suite_passes" and all(dependency_passes(d) for d in cap["requires"])
    for capability in capabilities:
        if capability["evidence_status"] == "scoped_suite_passes" and not dependency_passes(capability["id"]):
            capability["evidence_status"] = "some_scenarios_pass"
    return {"schema": 1, "scope": manifest["scope"], "run_identity": run_identity,
            "card_denominator": len(cards), "scenario_denominator": len(scenarios),
            "outcomes": {o: sum(s["outcome"] == o for s in scenarios) for o in OUTCOMES},
            "cards_with_current_direct_evidence": sum(bool(c.get("current_direct_scenarios")) for c in cards),
            "cards_with_only_current_capability_evidence": sum(bool(c.get("current_capability_scenarios")) and
                not c.get("current_direct_scenarios") for c in cards),
            "complete_rules_support": "not measured", "capabilities": capabilities,
            "scenarios": scenarios, "cards": cards}


def save(report, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    fields = ["name", "template_status", "required_capabilities", "declared_gaps", "current_direct_scenarios",
              "current_capability_scenario_count", "failures", "untested_requirements", "evidence_status", "error"]
    with (folder / "cards.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in report["cards"]:
            row = dict(row, current_capability_scenario_count=len(row.get("current_capability_scenarios", [])))
            writer.writerow({k: json.dumps(v) if isinstance(v, list) else v for k, v in row.items()})
    atomic_json(folder / "report.json", {k: v for k, v in report.items() if k != "cards"} | {
        "cards_csv_sha256": file_hash(folder / "cards.csv"),
        "cards_csv_schema": 2,
        "inferred_scenario_lookup": "Join required_capabilities to scenarios[].capabilities; CSV records their unique count.",
        "card_requirements_scope": "Only declared capability subsets assessed; remaining rules unclassified. "
                                   "No card is designated completely rules-supported."})
    lines = ["# Behavior evidence", "", f"Scope: `{report['scope']}`. Identity: `{report['run_identity']}`.", "",
             f"Inventory: {report['card_denominator']:,} distinct local database entries. "
             f"Required scenarios: {report['scenario_denominator']}.", "",
             "Complete rules support: **not measured**. Passing scenarios establish only their stated assertions. "
             "Capability evidence is inferred from shared rules, and is not direct testing of every card.", "",
             f"Cards with current direct evidence: {report['cards_with_current_direct_evidence']:,}. "
             f"Cards with only current capability evidence: {report['cards_with_only_current_capability_evidence']:,}.", "",
             "| Outcome | Scenarios |", "| --- | ---: |"]
    lines += [f"| {o} | {report['outcomes'][o]} |" for o in OUTCOMES]
    lines += ["", "| Capability | Declared state | Evidence in this scope |", "| --- | --- | --- |"]
    lines += [f"| {c['id']} | {c['state']} | {c['evidence_status']} |" for c in report["capabilities"]]
    lines += ["", "[Per-card evidence](cards.csv) · [Full report, restrictions and scenarios](report.json)", ""]
    (folder / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", action="store_true", help="execute the mapped scenarios and write a new ledger")
    ap.add_argument("--ledger", type=Path, help="evaluate an existing ledger, validating identities and traces")
    ap.add_argument("--save", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.run and args.ledger:
        ap.error("choose --run or --ledger")
    with output_lock(args.save):
        return run(args, ap)


def run(args, ap):
    catalog, manifest = load_catalogs()
    current = identity(catalog, manifest)
    if args.run:
        if (args.save / "ledger.json").exists():
            ap.error("evidence already exists; use a fresh output directory")
        records, base = execute(manifest, current, args.save), args.save
    elif args.ledger:
        ledger = json.loads(args.ledger.read_text())
        if ledger.get("schema") != 1:
            ap.error("unsupported ledger schema")
        records, base = ledger["records"], args.ledger.parent
    else:
        records, base = [], args.save
    scenarios = evaluate(manifest, records, current, base)
    db = CardDB(offline=True)
    try:
        report = build_report(db, catalog, manifest, scenarios, current)
        save(report, args.save)
    finally:
        if db._all is not None:
            db._all.close()
    print(f"{report['outcomes']} / {report['scenario_denominator']} required scenarios; {args.save / 'README.md'}")
    return int(args.run and any(report["outcomes"][o] for o in ("fail", "error", "not_run", "stale")))


if __name__ == "__main__":
    raise SystemExit(main())
