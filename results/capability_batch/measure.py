"""Compare two complete database-coverage reports and rank reusable wording families.

Run from the repository root:
  python results/capability_batch/measure.py
The input reports come from python -m mtgsim.database_coverage --save DIR.
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FAMILIES = [
    ('targeted permanent operations', r'\btarget\b.*(?:\bgets\b|\bgains\b|\bwith\b|\byou control\b)|^(?:destroy|exile|tap|untap) target'),
    ('counter operations', r'(?:\bput\b|\bremove\b|\bdouble\b|enters with).*\bcounters?\b'),
    ('keyword grants', r'\b(?:have|has|gain|gains)\b.*\b(?:flying|haste|trample|vigilance|lifelink|first strike|deathtouch|reach|menace|shroud|hexproof|indestructible)\b'),
    ('granted triggered abilities', r'\bgains? "when'),
]


def rows(path):
    with path.open(newline='') as stream:
        return {row['name']: row for row in csv.DictReader(stream)}


def rank(data):
    result = []
    for family, pattern in FAMILIES:
        affected, potential = [], []
        for row in data.values():
            lines = [s for s in row['ignored_text'].splitlines() if s.strip()]
            if any(re.search(pattern, s, re.I) for s in lines):
                affected.append(row['name'])
                if not row['simplifications'] and all(re.search(pattern, s, re.I) for s in lines):
                    potential.append(row['name'])
        result.append({'family': family, 'affected_cards': len(affected),
                       'potential_full_matches_upper_bound': len(potential), 'examples': potential[:5]})
    return sorted(result, key=lambda r: (-r['potential_full_matches_upper_bound'], -r['affected_cards']))


def main():
    before, after = rows(ROOT / 'before/cards.csv'), rows(ROOT / 'after/cards.csv')
    assert before.keys() == after.keys(), 'Card inventories differ'
    changed = [{'name': name, 'before': before[name], 'after': after[name]}
               for name in before if before[name] != after[name]]
    order = {'parse_error': -1, 'partial': 0, 'simplified': 1, 'full': 2}
    regressions = [r for r in changed if order[r['after']['status']] < order[r['before']['status']]]
    new_full = [r['name'] for r in changed if r['after']['status'] == 'full' and r['before']['status'] != 'full']
    improved = [r for r in changed if order[r['after']['status']] > order[r['before']['status']] or
                len(r['after']['ignored_text'].splitlines()) < len(r['before']['ignored_text'].splitlines())]
    report = {'cards_compared': len(before), 'changed_classifications_or_ignored_text': len(changed),
              'improved_cards': len(improved), 'newly_full_template_matches': len(new_full),
              'status_regressions': regressions, 'newly_full_cards': new_full, 'changes': changed,
              'meaning': 'Template matching and ignored-text measurements, not complete Magic rules correctness.'}
    (ROOT / 'coverage-delta.json').write_text(json.dumps(report, indent=2) + '\n')
    ranking = {'method': 'Broad wording families; counts overlap and are upper bounds, not promised gains. '
                        'All four selected for conservative reusable subsets.',
               'ranking': rank(before), 'remaining': rank(after)}
    (ROOT / 'selected-families.json').write_text(json.dumps(ranking, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('cards_compared', 'changed_classifications_or_ignored_text',
                      'improved_cards', 'newly_full_template_matches')}, indent=2))
    print('Status regressions:', len(regressions))


if __name__ == '__main__':
    main()
