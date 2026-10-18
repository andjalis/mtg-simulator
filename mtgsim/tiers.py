"""Old name for mtgsim.ranks: the five test tiers became seven ranks (Bronze to Grandmaster)."""
from .ranks import PASS_RATE, RANKS, RANKS_DIR, Rank, list_ranks, resolve_ranks

Tier = Rank
TIERS = RANKS
TIERS_DIR = RANKS_DIR
resolve_tiers = resolve_ranks
list_tiers = list_ranks

__all__ = ["PASS_RATE", "RANKS", "RANKS_DIR", "Rank", "list_ranks", "resolve_ranks",
           "Tier", "TIERS", "TIERS_DIR", "resolve_tiers", "list_tiers"]
