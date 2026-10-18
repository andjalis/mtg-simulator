import copy
import json
import unittest

from mtgsim.rules_compare import EXPECTED, compare


class RulesCompareTests(unittest.TestCase):
    def fixtures(self):
        rows = [{"id": key, **value} for key, value in EXPECTED.items()]
        builtin = {"observations": copy.deepcopy(rows) + [{"id": "forge-import-exile"}]}
        log = "\n".join("RULES_PROBE " + json.dumps(row) for row in rows)
        return builtin, log

    def test_agreement_is_separate_from_conformance(self):
        builtin, log = self.fixtures()
        self.assertEqual(compare(builtin, log)["both_conform"], 3)
        builtin["observations"][0]["observed_remaining"] = 2
        result = compare(builtin, log)
        self.assertEqual((result["agree"], result["both_conform"]), (2, 2))
        log = log.replace('"observed_remaining": 1', '"observed_remaining": 2')
        result = compare(builtin, log)
        self.assertEqual((result["agree"], result["both_conform"]), (3, 2))

    def test_missing_duplicate_or_malformed_observations_rejected(self):
        builtin, log = self.fixtures()
        for bad in ("", log + "\n" + log.splitlines()[0], log.replace('"observed_remaining": 1', '"observed_remaining": true')):
            with self.assertRaises(ValueError):
                compare(builtin, bad)
