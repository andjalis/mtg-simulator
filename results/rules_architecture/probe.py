"""Reproduce the architecture audit's bounded observations; this is not a conformance suite.

Run from any directory: python3 /path/to/results/rules_architecture/probe.py
Requires the offline card database. Emits observations, including known failures, as JSON.
Exit zero means the audit ran, not that Magic rules passed. Never used as a CI gate.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mtgsim.ai import BaselineAI
from mtgsim.carddb import CardDB
from mtgsim.cards import CardDef, Effect
from mtgsim.coverage import card_coverage
from mtgsim.engine import Game, Player
from mtgsim.forge import find_forge, ForgeError
from mtgsim.forge_script import parse_script, translate
from mtgsim.provenance import runtime_identity


def new_game():
    a, b = Player("a", [], BaselineAI()), Player("b", [], BaselineAI())
    game = Game(a, b, random.Random(0))
    game.turn, game.step = 2, "main1"
    return game, a, b


def main():
    db = CardDB(offline=True)
    if db._all is None:
        raise RuntimeError("Build the offline card database before running this audit")
    try:
        cards = {name: db.get(name) for name in
                 ("Isamaru, Hound of Konda", "Shuko", "Grizzly Bears", "Island")}
        coverage = {name: dataclasses.asdict(card_coverage(card)) for name, card in cards.items()}
        observations = []

        game, a, _ = new_game()
        legend = cards["Isamaru, Hound of Konda"]
        game.enter_battlefield(a, legend)
        game.enter_battlefield(a, legend)
        game.state_based_actions()
        remaining = sum(p.card.name == legend.name for p in a.battlefield)
        observations.append({"id": "legend-rule", "cards": [legend.name],
                             "expected_remaining": 1, "observed_remaining": remaining,
                             "passed": remaining == 1})

        game, a, _ = new_game()
        equipment = game.enter_battlefield(a, cards["Shuko"])
        creature = game.enter_battlefield(a, cards["Grizzly Bears"])
        # Hold priority so an ordinary queued activation cannot auto-resolve.
        game._priority_depth = 1
        activated = game.equip(a, equipment, creature)
        attached = equipment.attached_to is creature
        stack_size = len(game.stack)
        if game.stack:
            game.resolve_top()
        after = equipment.attached_to is creature
        observations.append({"id": "equip-response-window", "cards": ["Shuko", "Grizzly Bears"],
                             "activated": activated, "expected_stack_size": 1,
                             "observed_stack_size": stack_size,
                             "expected_attached_before_resolution": False,
                             "observed_attached_before_resolution": attached,
                             "observed_attached_after_resolution": after,
                             "passed": activated and stack_size == 1 and not attached and after})

        game, a, b = new_game()
        land = game.enter_battlefield(b, cards["Island"])
        effect = Effect("damage", 2, target="creature")
        enumerated = land in game.legal_targets(a, effect)
        accepted = game.legal_target(a, effect, land)
        observations.append({"id": "target-type-validation", "cards": ["Island"],
                             "effect": dataclasses.asdict(effect),
                             "enumeration_includes_land": enumerated,
                             "validation_accepts_land": accepted,
                             "expected_validation_accepts_land": False,
                             "passed": not enumerated and not accepted})

        script = ("Name:Audit Exile\nTypes:Instant\n"
                  "A:SP$ ChangeZone | ValidTgts$ Creature | Origin$ Battlefield | Destination$ Exile\n")
        kind, effects = translate(parse_script(script)[0].abilities[0])
        observations.append({"id": "forge-import-exile", "fixture": script,
                             "translation_kind": kind,
                             "translated_effects": [dataclasses.asdict(e) for e in effects],
                             "expected_effect_kind": "exile",
                             "passed": len(effects) == 1 and effects[0].kind == "exile"})

        try:
            folder, jar = find_forge()
            forge = {"configured": True, "folder": str(folder), "jar": jar.name}
        except ForgeError as exc:
            forge = {"configured": False, "reason": str(exc)}
        forge.update({"java_available": shutil.which("java") is not None,
                      "maven_available": shutil.which("mvn") is not None,
                      "live_games_run_by_probe": 0})
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                                capture_output=True, text=True).stdout.strip()
        print(json.dumps({"schema": 1, "source_commit": commit,
                          "scope": "Four bounded architecture observations; not card conformance coverage",
                          "runtime": runtime_identity(), "forge": forge,
                          "carddef_field_count": len(dataclasses.fields(CardDef)),
                          "card_template_coverage": coverage, "observations": observations}, indent=2))
    finally:
        db._all.close()


if __name__ == "__main__":
    main()
