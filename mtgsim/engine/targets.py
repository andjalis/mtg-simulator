"""Game methods for targeting: legal targets, filters, counterability and automatic targets."""
from __future__ import annotations

from .. import removal
from ..cards import Effect
from .policy import default_choose_target, perm_value
from .state import Permanent, Player, StackItem, TARGETED, is_basic_land


class TargetsMixin:
    def targetable(self, obj, by: Player) -> bool:
        """Whether ``by`` may target obj (shroud, hexproof, battlefield / stack presence)."""
        if isinstance(obj, Permanent):
            return (obj in obj.controller.battlefield and not obj.has("shroud")
                    and not (obj.has("hexproof") and obj.controller is not by))
        if isinstance(obj, StackItem):
            return obj in self.stack
        return isinstance(obj, Player)

    def passes_filter(self, eff: Effect, perm: Permanent, by: Player) -> bool:
        f = eff.filter
        if f.startswith("land:"):
            return ("nonbasic" not in f or not is_basic_land(perm.card)) and ("opp" not in f or perm.controller is not by)
        if f.startswith("x:"):
            return removal.x_passes(f, perm, by)
        r = removal.passes(f, perm)
        if r is not None:
            return r
        if f.startswith("max_cmc:"):
            limit = int(f.split(":")[1])
            return perm.card.cmc <= limit
        if f == "plains":
            return perm.card.cmc <= sum(1 for x in by.battlefield if x.card.name.endswith("Plains"))
        if f == "attacking":
            return perm in self.attackers
        if f == "tapped":
            return perm.tapped
        if f == "attacking_blocking":
            return perm in self.attackers or any(perm in bl for bl in self.blocks.values())
        if f == "nonartifact":
            return not perm.card.is_artifact
        if f == "nonflying":
            return not perm.has("flying")
        if f == "untapped":
            return not perm.tapped
        if f == "opp":
            return perm.controller is not by
        if f == "mine":
            return perm.controller is by
        if f == "opp_damaged":
            return perm.controller is not by and perm.damage > 0
        if f == "opp_artifact_creature":
            return perm.controller is not by and (perm.is_creature or perm.card.is_artifact)
        if f == "opp_tapped_creature":
            return perm.controller is not by and perm.is_creature and perm.tapped
        if f == "stunned":
            return bool(perm.counters.get("stun"))
        if f.startswith("max_power:"):
            return perm.power <= int(f[10:])
        return True

    def legal_targets(self, p: Player, eff: Effect) -> list:
        everything = [x for pl in self.players for x in pl.battlefield if self.targetable(x, p)]
        creatures = [c for c in everything if c.is_creature and self.passes_filter(eff, c, p)]
        t = eff.target
        if t == "creature":
            return creatures
        if t == "creature_pw":
            return [x for x in everything if (x.is_creature or x.is_planeswalker) and self.passes_filter(eff, x, p)]
        if t == "creature_mine":
            return [c for c in creatures if c.controller is p]
        if t == "nonland_perm":
            return [x for x in everything if not x.card.is_land and self.passes_filter(eff, x, p)]
        if t == "land":
            return [x for x in everything if x.card.is_land and self.passes_filter(eff, x, p)]
        if t == "artifact":
            return [x for x in everything if x.card.is_artifact and self.passes_filter(eff, x, p)]
        if t == "artifact_enchantment":
            return [x for x in everything if (x.card.is_artifact or "Enchantment" in x.card.types)
                    and self.passes_filter(eff, x, p)]
        if t == "any":
            return creatures + [x for x in everything if x.is_planeswalker] + list(self.players)
        if t == "player":
            return [self.opponent(p)] if eff.filter == "opp" else list(self.players)
        if t == "graveyard_creature_life":
            return [c for c in p.graveyard if c.is_creature and c.cmc <= p.life_gained_turn]
        if t == "graveyard_creature_any":
            return [c for pl in self.players for c in pl.graveyard if c.is_creature]
        if t == "spell_or_permanent":
            return everything + [i for i in self.stack if i.is_spell]
        if t == "spell":
            return [i for i in self.stack if self.can_counter(eff, i, p)]
        return []

    def legal_target(self, p: Player, eff: Effect, tgt) -> bool:
        """Use the same type, controller, filter and presence checks as enumeration."""
        return any(tgt is candidate for candidate in self.legal_targets(p, eff))

    def can_counter(self, eff: Effect, item: StackItem, by: Player | None = None) -> bool:
        if eff.kind not in ("counter", "bounce_spell") or not item.is_spell or item not in self.stack:
            return False
        if by is not None and item.controller is by:
            return False
        card = item.card
        if eff.filter == "creature" and not card.is_creature:
            return False
        if eff.filter == "noncreature" and card.is_creature:
            return False
        if eff.filter == "artifact_ench" and not (card.is_artifact or "Enchantment" in card.types):
            return False
        if eff.filter == "creature_ench" and not (card.is_creature or "Enchantment" in card.types):
            return False
        if eff.filter == "artifact_creature" and not (card.is_creature or card.is_artifact):
            return False
        if eff.filter == "instant_sorcery" and not (card.is_instant or card.is_sorcery):
            return False
        if eff.filter.startswith("cmc:") and card.cmc != int(eff.filter[4:]):
            return False
        return True

    def counterable(self, item: StackItem) -> bool:
        if not item.is_spell or item.card.uncounterable or getattr(item, "uncounterable", False):
            return False
        if item.card.is_instant or item.card.is_sorcery:
            if any(perm.card.protects_spells for perm in item.controller.battlefield):
                return False
        return True

    def auto_targets(self, p: Player, effects: list, source=None) -> list:
        """Targets for effects nobody chose targets for (triggers, modes, copies)."""
        out = []
        for e in effects:
            if e.target not in TARGETED:
                out.append(None)
                continue
            tgt = self.hook(p, "choose_target")(self, p, e)
            if tgt is None or not self.legal_target(p, e, tgt):
                tgt = default_choose_target(self, p, e)
            if tgt is not None and e.data.get("distinct") and any(
                    t is tgt for e2, t in zip(effects, out) if e2.kind == e.kind and e2.data.get("distinct")):
                taken = [t for e2, t in zip(effects, out) if e2.kind == e.kind and e2.data.get("distinct")]
                tgt = max((x for x in self.legal_targets(p, e) if all(x is not t for t in taken)
                           and (x.controller is not p) == (tgt.controller is not p)), key=perm_value, default=None) \
                    if isinstance(tgt, Permanent) else None
            if e.data.get("other") and tgt is source:
                tgt = max((x for x in self.legal_targets(p, e) if x is not source),
                          key=perm_value, default=None)
            out.append(tgt)
        return out
