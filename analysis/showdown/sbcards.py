"""Load Showdown Bot cards (2004 / 2005 designs) into the same table format as the 2000 set.

These are the cards the tabletop app builds. Download them first with
`python scripts/fetch_showdownbot.py`; each file is one Showdown set for one MLB season.

How the 2004/05 cards fit the engine:
  * Charts print ranges that run past 20 (e.g. "HR 23+"). Results above 20 only come into play
    with strategy-card or icon bonuses, which the engine doesn't model, so we keep faces 1-20.
  * Same results as 2000 (PU, SO, GB, FB, BB, 1B, 1B+, 2B, 3B, HR) and the same pitch roll
    (d20 + Control > On-Base -> pitcher's chart), so the engine needs no changes.
  * Speed is a number (about 8-25) instead of the 2000 letters A/B/C (20/15/10).
  * Ignored for now: icons (R, G, K, HR, SB, RP...) and stolen bases, just as for 2000.

The "league" is every card with real playing time in that season: Showdown Bot's own
`is_small_sample_size` flag, which means under 250 plate appearances or 30 innings.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from .cards import EVENTS, RAW

ROLE = {"STARTER": "Starter", "RELIEVER": "Reliever", "CLOSER": "Closer"}
# Showdown Bot position names -> the 2000 names value.py uses.
POS_NAME = {"LF/RF": "LF-RF"}
_DASHES = "–—-"


def range_to_faces(cell: str) -> list[int]:
    """Showdown Bot range -> d20 faces: '1–10' -> 1..10, '23+' -> [], '19+' -> [19, 20], '—' -> []."""
    cell = str(cell).strip()
    if cell in ("", "nan") or all(c in _DASHES for c in cell):
        return []
    m = re.fullmatch(r"(\d+)\+", cell)
    if m:
        return list(range(int(m.group(1)), 21))
    m = re.fullmatch(rf"(\d+)(?:[{_DASHES}](\d+))?", cell)
    if not m:
        raise ValueError(f"unrecognised chart range {cell!r}")
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    return [f for f in range(lo, hi + 1) if f <= 20]


def chart_counts(ranges: dict) -> dict:
    """Die faces 1-20 per result. Raises if a face is missing or listed twice."""
    seen: dict[int, str] = {}
    for ev, cell in ranges.items():
        if ev not in EVENTS:
            raise ValueError(f"unknown chart result {ev!r}")
        for f in range_to_faces(cell):
            if f in seen:
                raise ValueError(f"face {f} is both {seen[f]} and {ev}")
            seen[f] = ev
    missing = sorted(set(range(1, 21)) - set(seen))
    if missing:
        raise ValueError(f"faces {missing} have no result")
    return {e: sum(1 for v in seen.values() if v == e) for e in EVENTS}


def _positions(pd_: dict) -> list[tuple[str, int]]:
    """{'CF': 2, 'LF/RF': 3} -> [('CF', 2), ('LF-RF', 3)], best fielding first."""
    out = [(POS_NAME.get(p, p), int(v or 0)) for p, v in pd_.items()]
    return sorted(out, key=lambda pv: -pv[1]) or [("DH", 0)]


def load_set(showdown_set: str, season: int, include_small_samples: bool = False) -> pd.DataFrame:
    path = RAW / f"showdownbot_{showdown_set}_{season}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path.name} missing: run python scripts/fetch_showdownbot.py")
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for c in raw["cards"]:
        if c["is_small_sample_size"] and not include_small_samples:
            continue
        chart = chart_counts(c["chart_ranges"])
        rec = {
            "set": f"SB{showdown_set}", "season": season, "card_id": c["id"], "name": c["name"],
            "team": c.get("team"), "points": int(c["points"]), "is_pitcher": bool(c["is_pitcher"]),
            "hand": c.get("hand"), "icons": " ".join(c.get("icons_list") or []),
            "real_pa": c.get("real_pa"), "real_ip": c.get("real_ip"),
            **{f"c_{e}": chart[e] for e in EVENTS},
        }
        pdef = c.get("positions_and_defense") or {}
        if rec["is_pitcher"]:
            role = next((ROLE[k] for k in pdef if k in ROLE), "Reliever")
            rec.update(role=role, control=int(c["command"]), ip=int(c["ip"]))
        else:
            pos = _positions(pdef)
            rec.update(role="Batter", onbase=int(c["command"]), speed=int(c["speed"]),
                       positions=", ".join(f"{p}+{f}" for p, f in pos),
                       primary_pos=pos[0][0], primary_fielding=pos[0][1])
        rows.append(rec)
    df = pd.DataFrame(rows)
    df.attrs.update(downloaded=raw.get("downloaded"), versions=raw.get("showdown_bot_versions"))
    return df


if __name__ == "__main__":
    for s in ("2004", "2005"):
        for y in (2025, 2026):
            try:
                df = load_set(s, y)
            except FileNotFoundError as e:
                print(e)
                continue
            print(f"{s} set, {y} season: {len(df)} cards "
                  f"({(~df['is_pitcher']).sum()} hitters, {df['is_pitcher'].sum()} pitchers), "
                  f"Showdown Bot v{', '.join(df.attrs['versions'])}")
