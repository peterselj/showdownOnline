"""Build the card explorer page (a sortable grid of every card's value) from results/*.csv.

Run scripts/value_report.py first (it writes the CSVs), then:

    python scripts/build_explorer.py        # -> results/card-explorer.html

The page itself lives in explorer/template.html; this script only injects the data.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
EVENTS = ["PU", "SO", "GB", "FB", "BB", "1B", "1B+", "2B", "3B", "HR"]

POOLS = [  # (id, label, csv prefix)
    ("sb2005-2026", "Showdown Bot 2005 set · 2026 season", "showdown_bot_2005_set_2026_season"),
    ("sb2004-2026", "Showdown Bot 2004 set · 2026 season", "showdown_bot_2004_set_2026_season"),
    ("sb2005-2025", "Showdown Bot 2005 set · 2025 season", "showdown_bot_2005_set_2025_season"),
    ("sb2004-2025", "Showdown Bot 2004 set · 2025 season", "showdown_bot_2004_set_2025_season"),
    ("wotc2000", "WotC 2000 set (original cards)", "wotc_2000_set"),
]


def _chart(r) -> list[int]:
    return [int(r[f"c_{e}"]) for e in EVENTS]


def _fit(df: pd.DataFrame) -> dict:
    slope, intercept = np.polyfit(df["points"], df["expected_at_price"], 1)
    return {"slope": round(float(slope), 7), "intercept": round(float(intercept), 5)}


def _icons(v) -> str:
    return "" if pd.isna(v) else str(v)


def pool(pid: str, label: str, prefix: str) -> dict | None:
    bf, pf = RES / f"{prefix}_batters.csv", RES / f"{prefix}_pitchers.csv"
    if not bf.exists() or not pf.exists():
        print(f"skipping {label}: run scripts/value_report.py first")
        return None
    bat, pit = pd.read_csv(bf), pd.read_csv(pf)
    year = lambda r: int(r["season"]) if "season" in r and not pd.isna(r.get("season")) else 2000  # noqa: E731
    hitters = [{
        "n": r["name"], "t": "" if pd.isna(r["team"]) else r["team"], "y": year(r), "p": int(r["points"]),
        "ob": int(r["onbase"]), "sp": int(r["speed"]), "pos": r["positions"], "c": _chart(r),
        "v": round(float(r["raa_per_game"]), 4), "s": round(float(r["surplus"]), 4),
        "ic": _icons(r.get("icons")),
    } for _, r in bat.iterrows()]
    pitchers = [{
        "n": r["name"], "t": "" if pd.isna(r["team"]) else r["team"], "y": year(r), "p": int(r["points"]),
        "ctl": int(r["control"]), "ip": int(r["ip"]), "role": r["role"], "c": _chart(r),
        "v": round(float(r["runs_saved_per_outing"]), 4), "ra9": round(float(r["ra9"]), 2),
        "s": round(float(r["surplus"]), 4), "ic": _icons(r.get("icons")),
    } for _, r in pit.iterrows()]
    return {
        "id": pid, "label": label, "hitters": hitters, "pitchers": pitchers,
        "fit": {"hitters": _fit(bat),
                "SP": _fit(pit[pit["staff"] == "Starters"]),
                "RP": _fit(pit[pit["staff"] == "Relievers"])},
    }


def main() -> None:
    pools = [p for p in (pool(*args) for args in POOLS) if p]
    data = json.dumps({"events": EVENTS, "pools": pools}, separators=(",", ":")).replace("</", "<\\/")
    html = (ROOT / "explorer" / "template.html").read_text(encoding="utf-8").replace("__DATA__", data)
    out = RES / "card-explorer.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size / 1e6:.2f} MB, {len(pools)} card pools)")


if __name__ == "__main__":
    main()
