"""Card lookup: bundled sample cards, a local cache, the offline database of every card
(data/cards.sqlite3, built by `python3 -m mtgsim.build_carddb`), then the Scryfall API."""
from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.request
from pathlib import Path

from .build_carddb import DEFAULT_DB, normalize
from .cards import CardDef, card_from_scryfall

BUILTIN = Path(__file__).parent / "data" / "builtin_cards.json"
CACHE = Path(os.environ.get("MTGSIM_CACHE", Path.home() / ".cache" / "mtgsim" / "cards.json"))
ALL_CARDS = Path(os.environ.get("MTGSIM_CARDDB", DEFAULT_DB))
SCRYFALL_COLLECTION = "https://api.scryfall.com/cards/collection"


class CardDB:
    def __init__(self, offline: bool = False):
        self.offline = offline
        self.raw: dict[str, dict] = {}
        for path in (BUILTIN, CACHE):
            if path.exists():
                for card in json.loads(path.read_text()):
                    self.raw[card["name"].lower()] = card
        self._defs: dict[str, CardDef] = {}
        self._all = sqlite3.connect(f"file:{ALL_CARDS}?mode=ro", uri=True,
                                    check_same_thread=False) if ALL_CARDS.exists() else None

    def _key(self, name: str) -> str:
        key = name.lower()
        if key in self.raw:
            return key
        for k in self.raw:  # allow front-face names of split / MDFC cards
            if k.split(" // ")[0] == key:
                return k
        card = self.lookup(name)
        if card:
            key = card["name"].lower()
            self.raw.setdefault(key, card)
        return key

    def lookup(self, name: str) -> dict | None:
        """Scryfall-shaped data for any card in the offline database, by full or face name
        (case and accents ignored), or None."""
        if not self._all:
            return None
        row = self._all.execute("SELECT c.data FROM names n JOIN cards c ON c.key = n.key WHERE n.alias = ?",
                                (normalize(name),)).fetchone()
        return json.loads(row[0]) if row else None

    def ensure(self, names):
        missing = sorted({n for n in names if self._key(n) not in self.raw})
        if not missing:
            return
        if self.offline:
            raise KeyError(f"Unknown cards (offline mode): {', '.join(missing)}")
        fetched, not_found = self._fetch_scryfall(missing)
        for card in fetched:
            self.raw[card["name"].lower()] = card
        self._save_cache(fetched)
        if not_found:
            raise KeyError(f"Scryfall could not find: {', '.join(not_found)}")

    def get(self, name: str) -> CardDef:
        key = self._key(name)
        if key not in self._defs:
            self.ensure([name])
            self._defs[key] = card_from_scryfall(self.raw[self._key(name)])
        return self._defs[key]

    @staticmethod
    def _fetch_scryfall(names):
        found, not_found = [], []
        for i in range(0, len(names), 75):  # API limit per request
            body = json.dumps({"identifiers": [{"name": n} for n in names[i:i + 75]]}).encode()
            req = urllib.request.Request(SCRYFALL_COLLECTION, data=body, headers={
                "Content-Type": "application/json", "Accept": "application/json",
                "User-Agent": "mtgsim/0.1"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.load(resp)
            found += payload.get("data", [])
            not_found += [nf.get("name", str(nf)) for nf in payload.get("not_found", [])]
            time.sleep(0.1)  # Scryfall asks for 50-100 ms between requests
        return found, not_found

    @staticmethod
    def _save_cache(cards):
        if not cards:
            return
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        existing = json.loads(CACHE.read_text()) if CACHE.exists() else []
        keep = ("name", "mana_cost", "cmc", "type_line", "oracle_text", "power", "toughness", "card_faces")
        existing += [{k: c[k] for k in keep if k in c} for c in cards]
        CACHE.write_text(json.dumps(existing))
