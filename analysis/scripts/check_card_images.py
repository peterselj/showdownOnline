"""Check which card image links resolve on img.showdown2000.fun.

The explorer links each card to its picture. The site's file names follow a pattern
('{year}_2000_{Name}_{ROLE}_{tag_}{TEAM}.png'); this asks for one byte of each guessed file and
saves the ones that exist to data/raw/sd2000_card_images.txt, which build_sd2000.py uses so that
it never shows a broken link.

Usage:  python scripts/check_card_images.py        # ~2,000 tiny requests, about 10 minutes
"""
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_sd2000  # noqa: E402
from build_sd2000 import IMG_BASE, card_images  # noqa: E402
from showdown import sd2000  # noqa: E402

build_sd2000._KNOWN = None      # guess every name, ignoring any earlier check

OUT = ROOT / "data" / "raw" / "sd2000_card_images.txt"


def exists(name: str) -> bool:
    req = Request(f"{IMG_BASE}{name}?v=5", headers={"Range": "bytes=0-0", "User-Agent": "showdown card analysis"})
    try:
        with urlopen(req, timeout=30) as r:
            return r.status in (200, 206)
    except HTTPError:
        return False
    except URLError:
        return False


def main() -> None:
    names = set()
    for df, role in ((sd2000.load_hitters(), "HITTER"), (sd2000.load_pitchers(), "PITCHER")):
        for _, x in df.iterrows():
            names.update(card_images(x, role))
    ok = []
    for i, n in enumerate(sorted(names), 1):
        if exists(n):
            ok.append(n)
        time.sleep(0.25)
        if i % 200 == 0:
            print(f"{i}/{len(names)} checked, {len(ok)} found")
    OUT.write_text("\n".join(ok) + "\n", encoding="utf-8")
    print(f"{len(ok)} of {len(names)} card images found -> {OUT}")


if __name__ == "__main__":
    main()
