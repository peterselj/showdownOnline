"""Value every card per point, for the 2000 set and for Showdown Bot's 2004/2005 cards.

Prints a summary for each card pool and saves the full tables to results/<pool>_{batters,pitchers,
marginals}.csv.

Usage:  python scripts/value_report.py                  # 2000 set + Showdown Bot 2004/2005, 2026 season
        python scripts/value_report.py --seasons 2025 2026
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from showdown.cards import build_cards  # noqa: E402
from showdown.sbcards import load_set  # noqa: E402
from showdown.value import (add_surplus, batter_marginals, build_league,  # noqa: E402
                            pitcher_marginals, value_batters, value_pitchers)

OUT = ROOT / "results"
BAT_COLS = ["name", "season", "points", "onbase", "speed", "positions", "out_slots", "xbh_slots",
            "raa_per_game", "expected_at_price", "surplus"]
PIT_COLS = ["name", "season", "role", "points", "control", "ip", "out_slots",
            "ra9", "runs_saved_per_outing", "expected_at_price", "surplus"]


def report(label: str, cards: pd.DataFrame, top: int = 8) -> dict:
    lg = build_league(cards)
    bat = add_surplus(value_batters(lg), "raa_per_game")
    pit = value_pitchers(lg)
    pit["staff"] = np.where(pit["role"] == "Starter", "Starters", "Relievers")
    pit = add_surplus(pit, "runs_saved_per_outing", group_col="staff")
    marg = pd.concat([batter_marginals(lg).assign(kind="batter"),
                      pitcher_marginals(lg).assign(kind="pitcher")], ignore_index=True)

    OUT.mkdir(exist_ok=True)
    slug = label.lower().replace(" ", "_").replace(",", "")
    bat.sort_values("surplus", ascending=False).to_csv(OUT / f"{slug}_batters.csv", index=False)
    pit.sort_values("surplus", ascending=False).to_csv(OUT / f"{slug}_pitchers.csv", index=False)
    marg.to_csv(OUT / f"{slug}_marginals.csv", index=False)

    pd.set_option("display.width", 200, "display.max_columns", 20)
    cols_b = [c for c in BAT_COLS if c in bat.columns]
    cols_p = [c for c in PIT_COLS if c in pit.columns]
    print(f"\n{'=' * 100}\n{label}: {len(bat)} hitters, {len(pit)} pitchers")
    print(f"League: {lg.runs_per_9:.2f} runs per 9 innings, {lg.pa_per_inning:.2f} batters per inning")
    r_b = np.corrcoef(bat["points"], bat["raa_per_game"])[0, 1]
    print(f"Hitters: points vs runs added r = {r_b:.2f}; the market pays "
          f"{bat['runs_per_100pts_market'].iloc[0]:.3f} runs/game per 100 points")
    for staff, g in pit.groupby("staff"):
        r_p = np.corrcoef(g["points"], g["runs_saved_per_outing"])[0, 1]
        print(f"{staff}: points vs runs saved per outing r = {r_p:.2f}; "
              f"{g['runs_per_100pts_market'].iloc[0]:.3f} runs/outing per 100 points")

    fmt = {"raa_per_game": "{:+.3f}".format, "expected_at_price": "{:+.3f}".format,
           "surplus": "{:+.3f}".format, "ra9": "{:.2f}".format,
           "runs_saved_per_outing": "{:+.3f}".format}
    print(f"\nBest-value hitters (runs/game above a typical card at the same points):")
    print(bat.nlargest(top, "surplus")[cols_b].to_string(index=False, formatters=fmt))
    # A card at the minimum price can't get cheaper, so "overpriced" only means something above it.
    priced = bat[bat["points"] > bat["points"].min()]
    print(f"\nMost overpriced hitters (above the {bat['points'].min()}-point minimum):")
    print(priced.nsmallest(top // 2, "surplus")[cols_b].to_string(index=False, formatters=fmt))
    for staff, g in pit.groupby("staff"):
        print(f"\nBest-value {staff.lower()} (runs saved per outing above a typical card at the same points):")
        print(g.nlargest(top // 2 + 2, "surplus")[cols_p].to_string(index=False, formatters=fmt))
    print("\nWhat one change is worth (averaged over every card it applies to):")
    print(marg.to_string(index=False, float_format="{:+.3f}".format))
    return {"label": label, "hitters_r": r_b, "lg_runs_per_9": lg.runs_per_9,
            "hitter_runs_per_100pts": bat["runs_per_100pts_market"].iloc[0]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", type=int, default=[2026])
    ap.add_argument("--sets", nargs="+", default=["2004", "2005"])
    ap.add_argument("--skip-2000", action="store_true")
    args = ap.parse_args()

    summaries = []
    if not args.skip_2000:
        summaries.append(report("WotC 2000 set", build_cards(report=False)))
    for s in args.sets:
        for y in args.seasons:
            summaries.append(report(f"Showdown Bot {s} set, {y} season", load_set(s, y)))
    print("\n" + pd.DataFrame(summaries).to_string(index=False, float_format="{:.3f}".format))


if __name__ == "__main__":
    main()
