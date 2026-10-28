"""Compare the previous complete census with this batch's complete census."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BEFORE = ROOT.parent / 'capability_batch/after'


def load(path):
    with path.open(newline='') as stream:
        return {r['name']: r for r in csv.DictReader(stream)}


def main():
    before, after = load(BEFORE / 'cards.csv'), load(ROOT / 'after/cards.csv')
    assert before.keys() == after.keys()
    order = {'parse_error': -1, 'partial': 0, 'simplified': 1, 'full': 2}
    changes = [{'name': name, 'before': before[name], 'after': after[name]}
               for name in before if before[name] != after[name]]
    improved = [r for r in changes if order[r['after']['status']] > order[r['before']['status']] or
                len(r['after']['ignored_text'].splitlines()) < len(r['before']['ignored_text'].splitlines())]
    regressions = [r for r in changes if order[r['after']['status']] < order[r['before']['status']]]
    new_full = [r['name'] for r in changes if r['after']['status'] == 'full' and r['before']['status'] != 'full']
    report = {'baseline': 'results/capability_batch/after', 'cards_compared': len(before),
              'changed_classifications_or_ignored_text': len(changes), 'improved_cards': len(improved),
              'newly_full_template_matches': len(new_full), 'status_regressions': regressions,
              'newly_full_cards': new_full, 'changes': changes,
              'meaning': 'Parser coverage, not verification of complete Magic rules correctness.'}
    (ROOT / 'coverage-delta.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('cards_compared', 'changed_classifications_or_ignored_text',
                      'improved_cards', 'newly_full_template_matches')}, indent=2))
    print('Status regressions:', len(regressions))


if __name__ == '__main__':
    main()
