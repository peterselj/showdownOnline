"""Import every MLB Showdown strategy card from showdowncards.com.

Writes data/strategy-cards.json. Run from the repo root:

    python scripts/import_strategy_cards.py            # list + store pages
    python scripts/import_strategy_cards.py --images   # also fetch card images

Politeness: the site's robots.txt asks for a 10-second crawl delay, so every
request waits 10s. Responses are cached in scripts/.cache/, so re-running only
fetches what's new. A full first run takes ~2 hours (555 store pages).

Effect text: the site's list omits the effect for many 2000-2002 cards. Those
are transcribed by hand from the card images into
data/strategy-text-transcribed.json ({card id: text}), which this script merges
in and marks with "textSource": "transcribed".

Images: every card gets one in data/strategy-img/<card id>.jpg. Clean scans
of the 2004-2005 cards come from Mark0552/ShowdownSim (matched by
scripts/import_strategy_images.py into data/strategy-images.json, used with
his permission). With --images, every other card uses showdowncards.com's
product image (200x272, watermarked). "imgSource" records which.
"""

import hashlib, html, json, re, subprocess, sys, time, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "scripts" / ".cache"
OUT = ROOT / "data" / "strategy-cards.json"
TRANSCRIBED = ROOT / "data" / "strategy-text-transcribed.json"
IMAGES = ROOT / "data" / "strategy-images.json"   # from import_strategy_images.py
IMG_DIR = ROOT / "data" / "strategy-img"
SITE = "https://showdowncards.com"
LIST = SITE + "/mlb/mlbsearch.php?a=strategy&limit={offset}&orderby={orderby}&sort={sort}"
DELAY = 10
EXPECTED = 555

_last = 0.0


def fetch(url, binary=False):
    """GET with a disk cache and the site's 10s crawl delay."""
    global _last
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / hashlib.sha1(url.encode()).hexdigest()
    if path.exists():
        data = path.read_bytes()
    else:
        wait = DELAY - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        res = subprocess.run(["curl", "-sf", "-A", "Mozilla/5.0", url], capture_output=True, timeout=90)
        _last = time.time()
        if res.returncode != 0:
            raise RuntimeError(f"fetch failed ({res.returncode}): {url}")
        data = res.stdout
        path.write_bytes(data)
    if binary:
        return data
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def clean(fragment):
    text = html.unescape(re.sub(r"<[^>]+>", " ", fragment)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def base_name(name):
    """Name used for the 4-copies rule: ignores case, stars and punctuation."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def read_list():
    """The paging is unstable for ties, so union several sort orders."""
    cards = {}
    found_before = -1
    for orderby in ["name", "cardnumber", "year", "type", "whenplay", "description"]:
        for sort in ["ASC", "DESC"]:
            for offset in range(0, EXPECTED, 25):
                page = fetch(LIST.format(offset=offset, orderby=orderby, sort=sort))
                for tr in re.findall(r"<tr>\s*<td bgcolor='#CC0033'.*?</tr>", page, re.S):
                    link = re.search(r"href='\.\./store/([^']+)'", tr)
                    tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
                    if not link or len(tds) < 7:
                        continue
                    cards[link.group(1)] = {
                        "number": clean(tds[1]), "name": clean(tds[2]), "type": clean(tds[3]),
                        "year": clean(tds[4]), "when": clean(tds[5]), "text": clean(tds[6]),
                    }
            print(f"  list by {orderby} {sort}: {len(cards)} unique", file=sys.stderr)
            # Stop when complete, or when a whole pass turned up nothing new.
            if len(cards) >= EXPECTED or len(cards) == found_before:
                return cards
            found_before = len(cards)
    return cards


def read_store_page(slug):
    page = fetch(f"{SITE}/store/{urllib.parse.quote(slug)}")   # some slugs have curly quotes/dashes
    body = clean(page)
    # The wording varies by year:
    #   "MLB Showdown 2000 Pennant Run Strategy Card #S1 Afterburners."
    #   "MLB Showdown 2004 Base Set Offense Strategy Card S1 Bad Call"
    #   "MLB Showdown 2000 Strategy #S1 Bad Call."        (no set: base set)
    #   "MLB Showdown 2002 Base Set Strategy Card."      (no number)
    #   "MLB 2003 Base Set Strategy Card"                 (no "Showdown")
    m = re.search(r"MLB (?:Showdown )?(\d{4}) ?(.*?)\s*Strategy(?: Card)?\.?\s*#?\s*(S?\d+\b)?", body)
    set_name = None
    if m:
        set_name = re.sub(r"\s*\b(Offense|Defense|Utility|Common|Rare)$", "", m.group(2).strip())
        set_name = re.sub(r"\s*\bSet$", "", set_name).strip() or "Base"
    if not m:   # fall back to the store address, e.g. "...-mlb-2003-trading-deadline-strategy"
        for key, name in [("pennant-run", "Pennant Run"), ("trading-deadline", "Trading Deadline"), ("base", "Base")]:
            if key in slug:
                set_name = name
                break
    img = re.search(r"src='\.\./(images/product/[^']+)'", page) or re.search(r'src="\.\./(images/product/[^"]+)"', page)
    return {
        "setYear": m.group(1) if m else None,
        "set": set_name,
        "cardNumber": m.group(3) if m else None,
        "image": f"{SITE}/{img.group(1)}" if img else None,
    }


def main():
    want_images = "--images" in sys.argv
    print("Reading the strategy card list…", file=sys.stderr)
    listed = read_list()
    print(f"{len(listed)} listings (site says {EXPECTED})", file=sys.stderr)

    transcribed = json.loads(TRANSCRIBED.read_text(encoding="utf-8")) if TRANSCRIBED.exists() else {}
    images = json.loads(IMAGES.read_text(encoding="utf-8")) if IMAGES.exists() else {}
    cards = []
    for i, (slug, row) in enumerate(sorted(listed.items())):
        if i % 25 == 0:
            print(f"  store pages {i}/{len(listed)}", file=sys.stderr)
        store = read_store_page(slug)
        year = store["setYear"] or ("20" + row["year"].strip("'") if row["year"] else None)
        # some effects are wrapped in stray quotes on the site
        text, source = re.sub(r'^"(.*)"$', r"\1", row["text"]), "showdowncards.com"
        if slug in transcribed:
            text, source = transcribed[slug], "transcribed"
        elif not text:
            source = "missing"
        img = images.get(slug)
        img_source = "ShowdownSim" if img else None
        if want_images and store["image"] and (not img or source == "missing"):
            data = fetch(store["image"], binary=True)
            if source == "missing":   # kept handy for transcribing the effect
                (CACHE / "images").mkdir(parents=True, exist_ok=True)
                (CACHE / "images" / f"{slug}.jpg").write_bytes(data)
            if not img:
                IMG_DIR.mkdir(parents=True, exist_ok=True)
                (IMG_DIR / f"{slug}.jpg").write_bytes(data)
                img, img_source = f"data/strategy-img/{slug}.jpg", "showdowncards.com"
        cards.append({
            "id": slug,
            "name": row["name"].lstrip("*").strip(),
            "baseName": base_name(row["name"]),
            "year": year,
            "set": store["set"],
            "number": store["cardNumber"] or row["number"],
            "type": {"Off": "Offense", "Def": "Defense", "Util": "Utility"}.get(row["type"], row["type"]),
            "when": row["when"],
            "text": text,
            "textSource": source,
            "starred": row["name"].count("*"),
            "img": img,
            "imgSource": img_source,
        })

    cards.sort(key=lambda c: (c["year"] or "", c["set"] or "", c["name"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(cards, ensure_ascii=False, indent=1), encoding="utf-8")
    missing = sum(c["textSource"] == "missing" for c in cards)
    print(f"Wrote {len(cards)} cards to {OUT.relative_to(ROOT)} ({missing} still missing effect text)", file=sys.stderr)


if __name__ == "__main__":
    main()
