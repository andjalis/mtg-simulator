"""Game.resolve: the shared amount rules, then the handler for the effect's kind (see kinds/)."""
from __future__ import annotations

import dataclasses

from .. import counting
from ..cards import Effect
from .state import Permanent, Player, StackItem
from .kinds import HANDLERS, NO_SBA


class ResolveMixin:
    def resolve(self, p: Player, eff: Effect, target, item: StackItem | None = None, prev=None):
        opp = self.opponent(p)
        if eff.target == "self" and item is not None:
            target = item.source
        if eff.target == "that_player" and item is not None:
            target = item.context
        if eff.target == "trigger_subject" and item is not None:
            target = item.context if isinstance(item.context, Permanent) and item.context in item.context.controller.battlefield \
                else None
        if eff.target == "host" and item is not None and isinstance(item.source, Permanent):
            target = item.source.aura_host or item.source.attached_to     # "enchanted creature" / "equipped creature"
        if eff.target == "that_controller":
            target = prev.controller if isinstance(prev, (Permanent, StackItem)) else prev
        k = eff.kind
        source = (item.card.name if item and item.card else
                  item.source.card.name if item and isinstance(item.source, Permanent) else "effect")
        cause = f"{source}: {k}"
        if eff.data.get("sacrificed_power"):
            eff = dataclasses.replace(eff, amount=getattr(item, "sacrificed_power", 0))
        if eff.data.get("per"):    # "for each X you control"
            src = item.source if item is not None else None
            n = counting.count(self, p, eff.data["per"], src)
            eff = dataclasses.replace(eff, amount=eff.amount * n, amount2=eff.amount2 * n if k == "pump" else eff.amount2)
        if eff.data.get("xq"):     # ", where X is the number of ..."
            n = self.x_quantity(p, eff.data["xq"], item, prev)
            if eff.data.get("xq_size"):
                eff = dataclasses.replace(eff, data=dict(eff.data, power=n, toughness=n))
            else:
                eff = dataclasses.replace(eff, amount=eff.amount * n,
                                          amount2=eff.amount2 * n if k in ("pump", "debuff", "debuff_one", "pump_all") else eff.amount2)
        if eff.data.get("x"):      # X is the X paid for the spell
            n = getattr(item, "x", 0)
            eff = dataclasses.replace(eff, amount=n, amount2=n if eff.data.get("x2") else eff.amount2)
        if k == "damage" and eff.data.get("count"):
            what = eff.data["count"]
            n = sum(x.card.token_kind == "treasure" if what == "treasures" else x.card.is_artifact
                    if what == "artifacts" else x.is_creature if what == "creatures" else x.card.is_land
                    for x in p.battlefield)
            eff = dataclasses.replace(eff, amount=n)
        handler = HANDLERS.get(k)
        if handler is not None:
            if handler(self, p=p, eff=eff, target=target, item=item, prev=prev, opp=opp, k=k, source=source,
                       cause=cause) is NO_SBA:
                return
        self.state_based_actions()
