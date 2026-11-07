# sim-gzones plan: zone-change verbs for the effect grammar

Work list: lists/zones.csv (3,794 units, 1,483 sole cards). Verb-led units with sole > 0 total ~800 cards; the
shapes below cover ~466 sole by regex bucket (upper bound; real yield lower after noun-phrase and rejection rules).

## Shapes ranked by sole cards (estimate)

| # | Shape | Sole | Engine kind |
|---|---|---|---|
| D | back-refs: "exile that creature", "put it on top of its owner's library", "return that card to its owner's hand" | ~91 (most need context; maybe 30 safe) | new `cx_zone` on target "prev" (stack.py gives trigger context / previous target) |
| A1+A2 | destroy target / N target / up to N target / all / each <np> | ~135 | `destroy` (target) / new `cx_zone` inside `cx_group` for all/each |
| C1 | "<player> sacrifices N <np>" (each player, each opponent, target player/opponent, that player) | ~68 | new `cx_edict` (count, noun filter, player set); existing edict kinds are fixed-filter |
| B1+B2 | return [target] <card np> from <gy> to hand / battlefield [tapped] | ~44 | new `cx_card_move` (card target in graveyard, exact zone of origin, destination) |
| E | blink: exile <np>, then return it/that card to the battlefield under its owner's/your control [tapped] | ~29 | `flicker` generalised (controller, tapped) |
| A3+A4 | exile target / all <np> (battlefield) | ~28 | `exile_permanent` / `cx_zone` |
| A7+A8 | put target / all <np> on top / bottom of owner's library, into graveyard | ~25 | new `cx_zone` (`to` = library_top / library_bottom / graveyard) |
| A5+A6 | return target / all <np> to owner's hand | ~18 | `bounce` / `cx_zone` |
| C3 | you sacrifice <np> (no cost) | ~15 | `cx_edict` with player = you |
| C2 | "<player> returns / exiles a <np> they control" | ~9 | `cx_edict` with `to` = hand / exile |

## One kind, one data shape
`cx_zone` data: {"to": destroy|exile|hand|library_top|library_bottom|graveyard|battlefield, "tapped", "under": owner|you}.
Used directly on a target / "prev", and as the inner effect of `cx_group` for all/each. Tokens leaving to non-battlefield
zones just cease (existing `leave_battlefield`). Destroy goes through `game.destroy` (regeneration, indestructible).
`cx_edict`: player set from the subject, count, noun spec, chooser = that player (least valuable first, AI policy).

## New noun-phrase pieces needed (in my module, or ask sim-grammar for the core reader)
- lists: "artifacts, creatures, and lands", "creatures and planeswalkers", "artifacts and/or enchantments"
- "that's COLOR or COLOR", "with mana value N", "<np> that player controls" (player = trigger context)
- card nouns with zone of origin: "creature card from your graveyard", "from a graveyard", "from an opponent's graveyard"

## Tricky rules (reject otherwise)
- "you may <hostile verb>" -> may_hostile only for verbs hitting the opponent; "you may" on own permanents needs a decline policy.
- "up to N" / "any number of" -> optional_target / distinct copies; "X target" rejected until X counts exist.
- "that card" after exile/dies is a card in a zone, not a permanent: only accept where the referent is provably the
  previous effect's moved card; else reject.
- "until ~ leaves the battlefield" only via existing linked_exile; "unless ..." / "if ..." -> gcond lane, reject.
- Zones of origin must be exact; "their owners' control" vs "your control" honoured; AI side: destroy/exile/bounce/tuck = theirs.

## PR order
1. `cx_zone` on targets + groups (A1-A8): destroy / exile / bounce / top / bottom (~100 est).
2. `cx_edict` player-subject sacrifice / return / exile (C1-C3) (~60).
3. graveyard card moves (B) + blink (E) (~50).
4. back-refs (D) where the referent is provable.

## Status 2026-11-06
- PR #228 claude/gzones-1b (+116): destroy/exile/bounce objects, player edicts (cx_edict), @ai_value. Stacked on grammar-7 (#222).
- PR #232 claude/gzones-3 (on #228): core.json removal wordings narrowed (8 false-full -> honest partial).
- PR #241 claude/gzones-2 (on #228): Game.put_in_library + library_top/bottom, old tuck kinds fixed, cx_tuck (+26).
- Next (claude/gzones-4 from gzones-1b): graveyard card returns. engine.state.card_matches returns False on unknown
  qualifiers (no error), which would give false-full cards with no legal targets: use an own whitelist card-noun
  reader (colour / non-X / types joined by "or" / "card(s)" / "with mana value|power N or less|greater") that returns
  None on anything else. graveyard_card targets (advanced_templates.grave_targets) need a one-line hook for a cx spec
  with an exact zone (your graveyard / a graveyard / an opponent's graveyard); destination hand (owner's) /
  battlefield [tapped] under your | its owner's control.
