"""The registration files of mtgsim/cards/registry and the kind-module discovery of engine/kinds: a module joins the
parser or the engine without editing a shared line, in a fixed order."""
import pkgutil
import sys
import types
import unittest
from unittest import mock

from mtgsim.engine import resolve as _resolve  # loads engine/resolve.py, which imports the remaining kind modules
from mtgsim import cards
from mtgsim.cards import face_lines, parse, registry
from mtgsim.cards import card_from_scryfall
from mtgsim.engine import kinds


def card(text, name="Hook Test"):
    return card_from_scryfall({"name": name, "mana_cost": "{1}", "cmc": 1, "type_line": "Creature — Test",
                               "oracle_text": text, "power": "1", "toughness": "1"})


class RegistryFilesTest(unittest.TestCase):
    def test_names_and_order(self):
        names = registry.file_names()
        self.assertGreater(len(names), 100)
        self.assertEqual(names, sorted(names))
        for name in names:
            self.assertRegex(name, registry.FILE_NAME)
        self.assertEqual(names[0], "0010_first_mechanics")

    def test_every_file_registers_known_fields_that_reach_the_tables(self):
        patterns = {id(p) for p in cards._EFFECT_PATTERNS}
        subs = {id(s) for s in cards._SUBS}
        trigs = {id(t) for t in cards._TRIGGERS}
        for name in registry.file_names():
            mod = sys.modules[f"{registry.__name__}.{name}"]
            fields = [a for a in vars(mod) if a.isupper()]
            self.assertTrue(fields, name)
            self.assertTrue(set(fields) <= set(registry.FIELDS), name)
            for p in list(getattr(mod, "EFFECT_PATTERNS", ())) + list(getattr(mod, "PRIORITY_PATTERNS", ())):
                self.assertIn(id(p), patterns, name)
            for s in getattr(mod, "SUBS", ()):
                self.assertIn(id(s), subs, name)
            for t in getattr(mod, "TRIGGERS", ()):
                self.assertIn(id(t), trigs, name)
            for k in getattr(mod, "KEYWORDS", ()):
                self.assertIn(k, cards.KEYWORDS, name)
            for f in getattr(mod, "FACE_LINE_PARSERS", ()):
                self.assertIn(f, parse._FACE_LINE_PARSERS, name)

    def test_tables_stay_shared(self):
        """parse.py reads the same list objects the registry extends; the transition names still exist."""
        from mtgsim.cards import clauses, patterns
        self.assertIs(cards._EFFECT_PATTERNS, patterns._EFFECT_PATTERNS)
        self.assertIs(cards._SUBS, clauses._SUBS)
        self.assertIs(cards._TRIGGERS, clauses._TRIGGERS)
        self.assertIs(cards._parse_module, parse)

    def test_badly_named_file_is_refused(self):
        fake = [types.SimpleNamespace(name="cx_new_thing", ispkg=False)]
        with mock.patch.object(registry.pkgutil, "iter_modules", return_value=fake):
            with self.assertRaises(ImportError):
                registry.file_names()


class LoadAllTest(unittest.TestCase):
    """load_all on stand-in tables with stand-in registration files."""

    def load(self, *files):
        names = []
        for i, fields in enumerate(files):
            name = f"{9000 + i}_fake"
            mod = types.ModuleType(f"{registry.__name__}.{name}")
            vars(mod).update(fields)
            names.append(name)
            sys.modules[mod.__name__] = mod
            self.addCleanup(sys.modules.pop, mod.__name__, None)
        tables = dict(effect_patterns=["old"], subs=["s0"], triggers=["t0"], keywords={"flying"},
                      parse_module=types.SimpleNamespace(_FACE_LINE_PARSERS=("base",)),
                      line_hooks={"keyword": ["h0"]})
        with mock.patch.object(registry, "file_names", return_value=names):
            registry.load_all(**tables)
        return tables

    def test_order_and_fields(self):
        t = self.load({"EFFECT_PATTERNS": ["a1", "a2"], "SUBS": ("s1",), "FACE_LINE_PARSERS": ("f1",)},
                      {"PRIORITY_PATTERNS": ["p"], "EFFECT_PATTERNS": ["b"], "TRIGGERS": ["t1"],
                       "KEYWORDS": {"zap"}, "FACE_LINE_PARSERS": ("f2",), "LINE_HOOKS": {"keyword": ("h1",)}})
        self.assertEqual(t["effect_patterns"], ["p", "old", "a1", "a2", "b"])
        self.assertEqual(t["subs"], ["s0", "s1"])
        self.assertEqual(t["triggers"], ["t0", "t1"])
        self.assertEqual(t["keywords"], {"flying", "zap"})
        self.assertEqual(t["parse_module"]._FACE_LINE_PARSERS, ("f2", "f1", "base"))
        self.assertEqual(t["line_hooks"], {"keyword": ["h0", "h1"]})

    def test_typo_field_and_unknown_stage_are_refused(self):
        with self.assertRaises(ImportError):
            self.load({"EFFECT_PATTERN": ["a"]})
        with self.assertRaises(ImportError):
            self.load({"LINE_HOOKS": {"nowhere": ("h",)}})


class LineHookTest(unittest.TestCase):
    LINE = "Zapcycling—Tap an untapped creature you control."

    def hook(self, stage):
        seen = []

        def handle(line, st):
            seen.append(line)
            if line == self.LINE:
                st.extra["changeling"] = True       # any field the card keeps
                return True
            return False
        face_lines.LINE_HOOKS[stage].append(handle)
        self.addCleanup(face_lines.LINE_HOOKS[stage].remove, handle)
        return seen

    def test_each_stage_handles_its_line(self):
        self.assertEqual(set(face_lines.LINE_HOOKS), set(face_lines.LINE_HOOK_STAGES))
        for stage in face_lines.LINE_HOOK_STAGES:
            with self.subTest(stage=stage):
                before = card(self.LINE)
                self.assertTrue(before.unsupported)
                self.assertFalse(before.changeling)
                seen = self.hook(stage)
                after = card(self.LINE)
                self.assertIn(self.LINE, seen)
                self.assertEqual(after.unsupported, [])
                self.assertTrue(after.changeling)
                self.doCleanups()

    def test_hook_does_not_take_lines_handled_before_it(self):
        seen = self.hook("keyword")
        c = card("Flying\nCycling {2}")
        self.assertIn("flying", c.keywords)
        self.assertNotIn("Cycling {2}", seen)      # cycling is parsed before the keyword stage
        self.assertEqual(c.unsupported, [])


class KindDiscoveryTest(unittest.TestCase):
    def test_every_kind_module_is_imported(self):
        for m in pkgutil.iter_modules(kinds.__path__):
            self.assertIn(f"{kinds.__name__}.{m.name}", sys.modules, m.name)

    def test_import_rest_is_idempotent(self):
        before = dict(kinds.HANDLERS)
        kinds.import_rest()
        self.assertEqual(kinds.HANDLERS, before)
        self.assertIs(_resolve.HANDLERS, kinds.HANDLERS)


if __name__ == "__main__":
    unittest.main()
