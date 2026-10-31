"""Game methods for targeting: legal targets, filters, counterability and automatic targets."""
from __future__ import annotations

import contextlib

from .. import removal, counter_mechanics, permanent_templates
from ..cards import Effect
from .policy import default_choose_target, perm_value
from .state import Permanent, Player, StackItem, TARGETED, is_basic_land, protected_from


class TargetsMixin:
    target_source = None    # the spell or ability whose targets are being chosen or checked

    def targetable(self, obj, by: Player, source=None) -> bool:
        """Whether ``by`` may target obj (shroud, hexproof, protection, battlefield / stack presence).
        Protection is checked against ``source``, or else the spell or ability whose targets are
        being chosen or checked (``target_source``)."""
        if isinstance(obj, Permanent):
            return (obj in obj.controller.battlefield and not obj.has("shroud")
                    and not (obj.has("hexproof") and obj.controller is not by)
                    and not protected_from(obj, source if source is not None else self.target_source))
        if isinstance(obj, StackItem):
            return obj in self.stack
        return isinstance(obj, Player)

    def passes_filter(self, eff: Effect, perm: Permanent, by: Player) -> bool:
        spec = eff.data.get('selector')
        if spec is not None:
            source = self.target_source.source if isinstance(self.target_source, StackItem) else self.target_source
            if not permanent_templates.matches(self, perm, spec, by, source):
                return False
        f = eff.filter
        if eff.data.get('attached_aura') and (not perm.card.aura or perm.aura_host is None):
            return False
        if f.startswith("land:"):
            return ("nonbasic" not in f or not is_basic_land(perm.card)) and ("opp" not in f or perm.controller is not by)
        if f.startswith("x:"):
            return removal.x_passes(f, perm, by)
        r = removal.passes(f, perm)
        if r is not None:
            return r
        if f.startswith("max_cmc:"):
            limit = int(f.split(":")[1])
            if by.perm_left_turn and eff.kind == "destroy":
                limit = max(limit, 4)  # Fatal Push's revolt
            return perm.card.cmc <= limit
        if f == "plains":
            return perm.card.cmc <= sum(1 for x in by.battlefield if x.card.name.endswith("Plains"))
        if f == "p1":
            return perm.p1 > 0
        if f == "tapped":
            return perm.tapped
        if f == "attacking":
            return perm in self.attackers
        if f == 'attacking_nonflying':
            return perm in self.attackers and not perm.has('flying')
        if f == "attacking_blocking":
            return perm in self.attackers or any(perm in bl for bl in self.blocks.values())
        if f == "nonartifact":
            return not perm.card.is_artifact
        if f == "nonflying":
            return not perm.has("flying")
        if f == "flying":
            return perm.has("flying")
        if f.startswith("total_pt<="):
            return perm.power + perm.toughness <= int(f[10:])
        if f == "untapped":
            return not perm.tapped
        if f == "opp":
            return perm.controller is not by
        if f == "mine":
            return perm.controller is by
        if f == "damaged":
            return perm.damage > 0
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

    @contextlib.contextmanager
    def targeting(self, source):
        """Choose or check targets for source (a CardDef, Permanent or StackItem): protection applies."""
        outer, self.target_source = self.target_source, source
        try:
            yield
        finally:
            self.target_source = outer

    def legal_targets(self, p: Player, eff: Effect) -> list:
        everything = [x for pl in self.players for x in pl.battlefield if self.targetable(x, p)]
        source = self.target_source.source if isinstance(self.target_source, StackItem) else self.target_source
        if eff.data.get('other'):
            everything = [x for x in everything if x is not source]
        creatures = [c for c in everything if c.is_creature and self.passes_filter(eff, c, p)]
        from ..backlog_templates import related_targets
        everything = related_targets(self, eff, everything)
        t = eff.target
        if t == 'graveyard_card':
            from ..advanced_templates import grave_targets
            return grave_targets(self, p, eff)
        if t == 'creature_or_graveyard':
            return creatures + counter_mechanics.graveyard_targets(self)
        if t == "permanent":
            return [x for x in everything if self.passes_filter(eff, x, p)]
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
        if t == "artifact_land":
            return [x for x in everything if (x.card.is_artifact or x.card.is_land) and self.passes_filter(eff, x, p)]
        if t == "artifact_enchantment":
            return [x for x in everything if (x.card.is_artifact or "Enchantment" in x.card.types)
                    and self.passes_filter(eff, x, p)]
        from ..batch1_templates import player_targetable
        if t == "any":
            return creatures + [x for x in everything if x.is_planeswalker] + [x for x in self.players if player_targetable(self, x, p)]
        if t == "player":
            walkers = [x for x in everything if x.is_planeswalker] if eff.data.get("or_pw") else []   # "player or planeswalker"
            return [x for x in ([self.opponent(p)] if eff.filter == "opp" else list(self.players)) if player_targetable(self, x, p)] + walkers
        if t == "spell":
            return [i for i in self.stack if self.can_counter(eff, i, p)]
        if t in ("spell_or_permanent", "spell_or_creature"):
            spells = [i for i in self.stack if self.can_counter(eff, i, p)]
            return spells + [x for x in (creatures if t == "spell_or_creature" else everything)
                             if self.passes_filter(eff, x, p)]
        return []

    def legal_target(self, p: Player, eff: Effect, tgt) -> bool:
        """Use the same type, controller, filter and presence checks as enumeration."""
        if eff.target in ('creature_or_graveyard', 'graveyard_card') and 'graveyard_ref' in eff.data:
            if eff.data['graveyard_ref'].find(eff.data['graveyard_zone']) is not tgt:
                return False
        if tgt is None and eff.data.get('optional_target'):
            return True
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
        if eff.filter.startswith("types:") and not set(eff.filter[6:].split(",")) & card.types:
            return False
        if eff.filter.startswith("cmc:") and card.cmc != int(eff.filter[4:]):
            return False
        if eff.filter.startswith("min_cmc:") and card.cmc < int(eff.filter[8:]):
            return False
        if eff.filter.startswith("max_cmc:") and card.cmc > int(eff.filter[8:]):
            return False
        if eff.filter.startswith("colors:") and not card.colors & set(eff.filter[7:]):
            return False
        return True

    def counterable(self, item: StackItem) -> bool:
        if not item.is_spell or item.card.uncounterable or getattr(item, "uncounterable", False):
            return False
        if item.card.is_instant or item.card.is_sorcery:
            if any(perm.card.protects_spells for perm in item.controller.battlefield):
                return False
        if item.card.is_creature and any(perm.card.advanced_rules.get('creatures_uncounterable')
                                         for perm in item.controller.battlefield if not perm.abilities_suppressed):
            return False
        return True

    def auto_targets(self, p: Player, effects: list, source=None, *, preset=None) -> list:
        """Targets for effects nobody chose targets for (triggers, modes, copies)."""
        if source is not None and source is not self.target_source:
            with self.targeting(source):
                return self.auto_targets(p, effects, preset=preset)
        out = []
        previous = getattr(self, '_choosing_targets', [])
        self._choosing_targets = out
        try:
            for index, e in enumerate(effects):
                if preset is not None and index < len(preset) and preset[index] is not None:
                    out.append(preset[index])
                    continue
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
                out.append(tgt)
            return out
        finally:
            self._choosing_targets = previous
