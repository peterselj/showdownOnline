"""Match strategy card scans from Mark0552/ShowdownSim to our catalog.

Mark's repo (https://github.com/Mark0552/ShowdownSim, used with his
permission) has scans of the 2004-2005 strategy cards plus a data file giving
each scan's year, expansion, card number and name. This script:

  1. downloads that data file and the scans (cached in scripts/.cache/),
  2. matches each scan to a card in data/strategy-cards.json by
     year + set + card number, confirming the names agree,
  3. copies matched scans to data/strategy-img/<card id>.jpg and writes
     data/strategy-images.json ({card id: image path}).

Run from the repo root after scripts/import_strategy_cards.py, then re-run
that script so it merges the image paths into data/strategy-cards.json:

    python scripts/import_strategy_images.py
    python scripts/import_strategy_cards.py
"""

import hashlib, json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "scripts" / ".cache" / "showdownsim"
CATALOG = ROOT / "data" / "strategy-cards.json"
IMG_DIR = ROOT / "data" / "strategy-img"
OUT = ROOT / "data" / "strategy-images.json"
RAW = "https://raw.githubusercontent.com/Mark0552/ShowdownSim/main/"


def fetch(path):
    CACHE.mkdir(parents=True, exist_ok=True)
    local = CACHE / hashlib.sha1(path.encode()).hexdigest()
    if not local.exists():
        res = subprocess.run(["curl", "-sfL", RAW + path], capture_output=True, timeout=60)
        if res.returncode != 0:
            raise RuntimeError(f"download failed: {path}")
        local.write_bytes(res.stdout)
    return local.read_bytes()


def norm_set(name):
    """'Base Set' / 'Base' -> 'base'; 'Pennant Run' -> 'pennant run'."""
    s = re.sub(r"[^a-z ]", "", (name or "").lower())
    s = re.sub(r"\b(set|strategy|cards?)\b", "", s)
    return re.sub(r"\s+", " ", s).strip() or "base"


def norm_number(n):
    """Card numbers print as '7' or 'S7'; compare the digits."""
    m = re.search(r"\d+", str(n or ""))
    return m.group() if m else ""


def base_name(name):
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def main():
    theirs = json.loads(fetch("simulation/strategy_cards.json"))
    ours = json.loads(CATALOG.read_text(encoding="utf-8"))
    index = {}
    for c in ours:
        key = (c["year"], norm_set(c["set"]), norm_number(c["number"]))
        index.setdefault(key, []).append(c)

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    mapping, unmatched, name_mismatch = {}, [], []
    for t in theirs:
        year = "20" + t["Yr."].strip("'")
        key = (year, norm_set(t["expansion"]), norm_number(t["#"]))
        candidates = index.get(key, [])
        match = next((c for c in candidates if c["baseName"] == base_name(t["Name"])), None)
        if not match and len(candidates) == 1:
            match = candidates[0]
            name_mismatch.append(f'{t["Name"]} ({year} {t["expansion"]} #{t["#"]}) -> ours: {match["name"]}')
        if not match:
            unmatched.append(f'{t["Name"]} ({year} {t["expansion"]} #{t["#"]})')
            continue
        dest = IMG_DIR / f'{match["id"]}.jpg'
        dest.write_bytes(fetch(t["imagePath"]))
        mapping[match["id"]] = f'data/strategy-img/{match["id"]}.jpg'

    OUT.write_text(json.dumps(mapping, indent=1, sort_keys=True), encoding="utf-8")
    print(f"Matched {len(mapping)} of {len(theirs)} scans", file=sys.stderr)
    for line in name_mismatch:
        print("  name differs (matched by number):", line, file=sys.stderr)
    for line in unmatched:
        print("  UNMATCHED:", line, file=sys.stderr)


if __name__ == "__main__":
    main()
