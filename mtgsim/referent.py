"""Referent statistics for follow-up amounts on cards (last-known characteristics)."""


def remember_card(item, card):
    """Freeze characteristics before moving a card, including before it becomes a permanent."""
    if item is not None:
        item.referent_card_stats = ({"power": card.power or 0, "toughness": card.toughness or 0,
                                     "mana value": card.cmc} if card is not None else None)


def card_stat(item, stat):
    if item is None:
        return 0
    if hasattr(item, "referent_card_stats"):
        return (item.referent_card_stats or {}).get(stat, 0)
    # Older reveal/dig handlers already retain the revealed card on the stack item.
    card = getattr(item, "moved_card", None) or getattr(item, "link_card", None)
    return (card.cmc if stat == "mana value" else getattr(card, stat, 0) or 0) if card else 0
