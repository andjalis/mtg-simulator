"""Run unchanged coverage reporters with a preloaded, override-preserving CardDB.

Preloading full-name database rows avoids CardDB's growing front-face alias scan.
A separate ordinary CardDB checks 100 representative definitions for parity.
PYTHONPATH may select an isolated baseline checkout; that takes import priority.
"""
import argparse
import dataclasses
import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from mtgsim import behavior_coverage as bc
from mtgsim import database_coverage as dc
from mtgsim.carddb import CardDB
from mtgsim.provenance import atomic_json, file_hash, runtime_identity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--behavior', action='store_true')
    args = parser.parse_args()
    db, ordinary = CardDB(offline=True), CardDB(offline=True)
    try:
        rows = list(db._all.execute('SELECT name, data FROM cards ORDER BY key'))
        for name, data in rows:
            db.raw.setdefault(name.lower(), json.loads(data))
        samples = rows[::max(1, len(rows)//100)][:100]
        for name, _ in samples:
            assert dataclasses.asdict(db.get(name)) == dataclasses.asdict(ordinary.get(name)), name
        metadata = {'runtime': runtime_identity(), 'runner_sha256': file_hash(Path(__file__)),
                    'preload': 'setdefault preserves builtin/cache overrides; full SQL names only',
                    'ordinary_lookup_parity_samples': len(samples), 'inventory_entries': len(rows)}
        args.out.mkdir(parents=True, exist_ok=True)
        atomic_json(args.out/'measurement.json', metadata)
        report = dc.measure(db)
        dc.save_report(report, args.out/'database')
        assert not report.errors, report.errors
        print('Inventory:', report.as_dict()['counts'], flush=True)
        if args.behavior:
            catalog, manifest = bc.load_catalogs()
            identity = bc.identity(catalog, manifest)
            folder = args.out/'behavior'
            assert not (folder/'ledger.json').exists(), 'use a fresh evidence directory'
            records = bc.execute(manifest, identity, folder)
            scenarios = bc.evaluate(manifest, records, identity, folder)
            evidence = bc.build_report(db, catalog, manifest, scenarios, identity)
            bc.save(evidence, folder)
            print('Behavior:', evidence['outcomes'], flush=True)
            assert all(row['outcome']=='pass' for row in scenarios)
    finally:
        db._all.close()
        ordinary._all.close()


if __name__ == '__main__':
    main()
