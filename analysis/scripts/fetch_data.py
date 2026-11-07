"""Download the two fan-compiled MLB Showdown card datasets we build on.

Both are pinned to an exact commit so results are reproducible.

  * birdman093/showdown      - one spreadsheet row per card, charts written as die ranges ("6-12").
  * digitgopher/showdown-app - one row per card, charts written as slot counts. GPL-2.0.

We cross-check the two against each other in showdown/cards.py.

Usage:  python scripts/fetch_data.py
"""
from pathlib import Path
from urllib.request import urlopen

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

SOURCES = {
    "birdman_2000.csv": (
        "https://raw.githubusercontent.com/birdman093/showdown/"
        "fbe888fc483f0febf3d4f11d214d012805e7db1c/showdown/showdown/Data/MLB_Showdown.xls%20-%202000.csv"
    ),
    "digitgopher_batters.csv": (
        "https://raw.githubusercontent.com/digitgopher/showdown-app/"
        "b940a9d4ec62354154d7aff9ba1b44e2af05090c/data/batters.csv"
    ),
    "digitgopher_pitchers.csv": (
        "https://raw.githubusercontent.com/digitgopher/showdown-app/"
        "b940a9d4ec62354154d7aff9ba1b44e2af05090c/data/pitchers.csv"
    ),
}


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        with urlopen(url, timeout=60) as resp:
            data = resp.read()
        (RAW / name).write_bytes(data)
        print(f"saved {name} ({len(data):,} bytes)")


if __name__ == "__main__":
    main()
