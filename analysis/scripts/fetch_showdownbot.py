"""Download Showdown Bot cards (the cards the tabletop app builds) for whole MLB seasons.

Showdown Bot (showdownbot.com, public domain: github.com/mgula57/mlb_showdown_card_bot) keeps a
database of a pre-built card for every player-season. Its own "Cards" page reads that
database through a public search endpoint; we use the same endpoint, one request per set and
season (about 1,500 cards, ~3 MB each).

The database is live, so results can shift slightly when Showdown Bot updates its formulas.
Each saved file records the Showdown Bot version and the download date.

Usage:  python scripts/fetch_showdownbot.py                    # 2004 + 2005 sets, 2025-2026 seasons
        python scripts/fetch_showdownbot.py --seasons 2019 2026 --sets 2005
"""
import argparse
import json
import time
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
URL = "https://www.showdownbot.com/api/cards/search"
PAGE = 5000  # the endpoint's maximum page size
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "showdown-online card analysis (github.com/peterselj/showdownOnline)",
}


def fetch(showdown_set: str, season: int) -> list[dict]:
    cards, page = [], 1
    while True:
        body = {"showdown_set": [showdown_set], "year": [str(season)], "limit": PAGE, "page": page,
                "sort_by": "points", "sort_direction": "desc"}
        req = Request(URL, data=json.dumps(body).encode(), headers=HEADERS, method="POST")
        with urlopen(req, timeout=180) as resp:
            rows = json.load(resp)
        if isinstance(rows, dict) and "error" in rows:
            raise RuntimeError(f"Showdown Bot: {rows['error']}")
        cards += rows
        if len(rows) < PAGE:
            return cards
        page += 1
        time.sleep(2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", default=["2004", "2005"])
    ap.add_argument("--seasons", nargs="+", type=int, default=[2025, 2026])
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    for s in args.sets:
        for y in args.seasons:
            cards = fetch(s, y)
            versions = sorted({str(c.get("showdown_bot_version")) for c in cards})
            out = {"set": s, "season": y, "downloaded": date.today().isoformat(),
                   "showdown_bot_versions": versions, "cards": cards}
            path = RAW / f"showdownbot_{s}_{y}.json"
            path.write_text(json.dumps(out), encoding="utf-8")
            print(f"saved {path.name}: {len(cards):,} cards (Showdown Bot v{', '.join(versions)})")
            time.sleep(2)


if __name__ == "__main__":
    main()
