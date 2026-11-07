"""Load, clean and cross-validate the 2000 MLB Showdown card set.

Every card is turned into a "chart": how many of the 20 die faces give each result.
Results (in this fixed order everywhere in the project):

    PU  pop-up          (pitcher charts only)
    SO  strikeout
    GB  ground ball
    FB  fly ball
    BB  walk
    1B  single
    1B+ single, and the batter takes 2nd if it is open (batter charts only)
    2B  double
    3B  triple          (batter charts only)
    HR  home run
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

EVENTS = ["PU", "SO", "GB", "FB", "BB", "1B", "1B+", "2B", "3B", "HR"]
OUT_EVENTS = ["PU", "SO", "GB", "FB"]

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

SPEED_LETTER = {"A": 20, "B": 15, "C": 10}
PITCHER_ROLES = {"Starter", "Reliever", "Closer"}

# birdman column name -> our event name
_BIRDMAN_COLS = {"PU": "PU", "SO": "SO", "GB": "GB", "FB": "FB", "W": "BB",
                 "S": "1B", "SPlus": "1B+", "DB": "2B", "TR": "3B", "HR": "HR"}
_DG_BAT_COLS = {"so": "SO", "gb": "GB", "fb": "FB", "bb": "BB", "b1": "1B",
                "b1p": "1B+", "b2": "2B", "b3": "3B", "hr": "HR"}
_DG_PIT_COLS = {"pu": "PU", "so": "SO", "gb": "GB", "fb": "FB", "bb": "BB",
                "b1": "1B", "b2": "2B", "hr": "HR"}


def range_to_faces(cell: str) -> list[int]:
    """'6-12' -> [6..12], '13-' -> [13], '20+' -> [20], '-' -> []."""
    cell = str(cell).strip()
    if cell in ("", "-", "nan"):
        return []
    m = re.fullmatch(r"(\d+)\+", cell)
    if m:
        lo = int(m.group(1))
        return [lo] if lo <= 20 else []
    m = re.fullmatch(r"(\d+)-(\d*)", cell)
    if not m:
        raise ValueError(f"unrecognised chart range {cell!r}")
    lo = int(m.group(1))
    hi = int(m.group(2)) if m.group(2) else lo
    return [f for f in range(lo, hi + 1) if f <= 20]


def parse_positions(pos: str) -> list[tuple[str, int]]:
    """'CF+3, LF-RF+2' -> [('CF', 3), ('LF-RF', 2)];  'DH' -> [('DH', 0)]."""
    out = []
    for part in str(pos).split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"([A-Za-z0-9-]+?)(?:\+(\d+))?", part)
        if not m:
            raise ValueError(f"unrecognised position {pos!r}")
        out.append((m.group(1), int(m.group(2) or 0)))
    return out


def load_birdman() -> pd.DataFrame:
    df = pd.read_csv(RAW / "birdman_2000.csv", dtype=str, encoding="latin-1")
    # Promo/foil reprints (DS, FS, HRH) duplicate base cards; keep the 612 regular cards.
    df = df[df["Set"] == "1st"].copy()
    df["set"] = np.where(df["Name"].str.startswith("*"), "PR", "BS")  # * marks Pennant Run
    df["name"] = df["Name"].str.lstrip("*").str.strip()
    df["card_no"] = df["SetNumber"].astype(int)
    df["points"] = df["Pts"].astype(int)
    df["is_pitcher"] = df["Pos"].isin(PITCHER_ROLES)

    rows = []
    overlaps = []
    for _, r in df.iterrows():
        faces = {}
        chart = dict.fromkeys(EVENTS, 0)
        for col, ev in _BIRDMAN_COLS.items():
            for f in range_to_faces(r[col]):
                if f in faces:
                    overlaps.append(f"{r['set']} #{r['card_no']} {r['name']}: birdman lists face {f} twice")
                faces[f] = ev
            chart[ev] = len(range_to_faces(r[col]))
        rec = {
            "set": r["set"], "card_no": r["card_no"], "name": r["name"], "team": r["Team"],
            "points": r["points"], "is_pitcher": r["is_pitcher"], "hand": r["H"],
            **{f"c_{e}": chart[e] for e in EVENTS},
        }
        if r["is_pitcher"]:
            rec.update(role=r["Pos"], control=int(r["OB_C"]), ip=int(r["Spd_IP"]))
        else:
            pos = parse_positions(r["Pos"])
            rec.update(role="Batter", onbase=int(r["OB_C"]), speed=SPEED_LETTER[r["Spd_IP"]],
                       positions=", ".join(f"{p}+{f}" for p, f in pos),
                       primary_pos=pos[0][0], primary_fielding=pos[0][1])
        rows.append(rec)
    out = pd.DataFrame(rows)
    out.attrs["overlaps"] = overlaps
    return out


def load_digitgopher() -> pd.DataFrame:
    bat = pd.read_csv(RAW / "digitgopher_batters.csv", dtype=str)
    bat = bat[bat["year"] == "2000"]
    pit = pd.read_csv(RAW / "digitgopher_pitchers.csv", dtype=str)
    pit = pit[pit["year"] == "2000"]
    rows = []
    for _, r in bat.iterrows():
        chart = dict.fromkeys(EVENTS, 0)
        for col, ev in _DG_BAT_COLS.items():
            chart[ev] = int(r[col])
        rows.append({"set": r["set"], "card_no": int(r["cardNo"]), "dg_name": r["Name"],
                     "dg_points": int(r["pts"]), "dg_onbase": int(r["onbase"]),
                     "dg_speed": int(r["sp"]), **{f"dg_{e}": chart[e] for e in EVENTS}})
    for _, r in pit.iterrows():
        chart = dict.fromkeys(EVENTS, 0)
        for col, ev in _DG_PIT_COLS.items():
            chart[ev] = int(r[col])
        rows.append({"set": r["set"], "card_no": int(r["cardNo"]), "dg_name": r["Name"],
                     "dg_points": int(r["pts"]), "dg_control": int(r["control"]),
                     "dg_ip": int(r["ip"]), **{f"dg_{e}": chart[e] for e in EVENTS}})
    return pd.DataFrame(rows)


def build_cards(report: bool = True) -> pd.DataFrame:
    """Return one clean row per 2000 card, after checking the two sources agree."""
    b = load_birdman()
    d = load_digitgopher()
    m = b.merge(d, on=["set", "card_no"], how="outer", indicator=True)

    problems = list(b.attrs.get("overlaps", []))
    unmatched = m[m["_merge"] != "both"]
    for _, r in unmatched.iterrows():
        problems.append(f"{r['set']} #{r['card_no']}: only in {r['_merge']}")
    both = m[m["_merge"] == "both"].copy()

    def check(col_a, col_b, label):
        bad = both[(both[col_a].notna()) & (both[col_a] != both[col_b])]
        for _, r in bad.iterrows():
            problems.append(f"{r['set']} #{r['card_no']} {r['name']}: {label} {r[col_a]} vs {r[col_b]}")

    check("points", "dg_points", "points")
    check("onbase", "dg_onbase", "on-base")
    check("speed", "dg_speed", "speed")
    check("control", "dg_control", "control")
    check("ip", "dg_ip", "IP")
    for e in EVENTS:
        check(f"c_{e}", f"dg_{e}", f"chart {e}")

    cards = both[[c for c in b.columns]].copy()
    sums = cards[[f"c_{e}" for e in EVENTS]].sum(axis=1)
    for _, r in cards[sums != 20].iterrows():
        problems.append(f"{r['set']} #{r['card_no']} {r['name']}: chart covers {sums[_]} faces, not 20")

    # Resolution: every disagreement is a birdman chart that doesn't cover exactly 20 faces,
    # while the digitgopher chart does. So digitgopher's chart counts are canonical; birdman
    # supplies the things only it has (positions with fielding, handedness, team).
    dg_cols = [f"dg_{e}" for e in EVENTS]
    dg_sums = both[dg_cols].sum(axis=1)
    if (dg_sums != 20).any():
        raise ValueError("digitgopher chart that does not cover 20 faces: "
                         + ", ".join(both.loc[dg_sums != 20, "name"]))
    for e in EVENTS:
        cards[f"c_{e}"] = both[f"dg_{e}"].astype(int).values
    cards["chart_source_fixed"] = (sums != 20).values

    if report:
        print(f"{len(b)} cards in birdman, {len(d)} in digitgopher, {len(both)} matched")
        print(f"{len(problems)} disagreements")
        for p in problems:
            print("  -", p)
    cards.attrs["problems"] = problems
    return cards.reset_index(drop=True)


if __name__ == "__main__":
    build_cards()
