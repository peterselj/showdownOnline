"""Value showdown2000.fun cards from real game results and build the card explorer page.

Needs data/raw/sd2000_{cards,batting,batting_clean,pitching,pitching_clean}.tsv
(see README: showdown2000.fun data). Writes:
  results/sd2000_hitters.csv, results/sd2000_pitchers.csv
  results/showdown2000-explorer.html   (from explorer/sd2000.html)

Usage:  python scripts/build_sd2000.py            # flagged teams left out
        python scripts/build_sd2000.py --all      # every team
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from showdown import sd2000  # noqa: E402

OUT = ROOT / "results"
SPOTS = ["C", "1B", "2B", "3B", "SS", "LF/RF", "CF"]


def fit(df: pd.DataFrame, col: str) -> dict:
    slope, intercept = np.polyfit(df["points"], df[col], 1, w=np.sqrt(df["weight"]))
    return {"slope": float(slope), "intercept": float(intercept)}


def make_findings(hb: pd.DataFrame, pv: pd.DataFrame, rv: dict, marg: dict, arm_table: dict) -> list[str]:
    """Plain-language headline results, recomputed from the data on every build."""
    out = []
    big = hb[hb["PA"] >= 500]
    r = np.corrcoef(big["points"], big["value"])[0, 1]
    out.append(f"Points predict real value fairly well for hitters (correlation {r:.2f} across {len(big)} cards "
               f"with 500+ plate appearances), so the price is usually fair and the bargains are the exceptions.")

    fast, rest = big[big["speed"] >= 24], big[big["speed"] < 24]
    if len(fast):
        out.append(f"Very fast runners (Speed 24+) are the clearest hitter bargain: {len(fast)} cards average "
                   f"{fast['surplus'].mean():+.2f} runs a game above their price (everyone else {rest['surplus'].mean():+.2f}), "
                   f"stealing {fast['sb_per_game'].mean():.1f} bases a game. A steal is worth {rv['SB']:+.2f} runs, "
                   f"caught stealing {rv['CS']:+.2f}, so it pays only at about 72%+ success.")

    cat = big[big["primary_spot"] == "C"].copy()
    if len(cat):
        cat["arm"] = cat["positions"].str.extract(r"C\+(\d+)")[0].astype(float)
        weak, strong = cat[cat["arm"] <= 7], cat[cat["arm"] >= 12]
        out.append(f"Catcher arm matters a lot below about +8 and barely above +10: a +5 arm lets this league's "
                   f"runners steal {-arm_table[5]:.2f} runs a game more than an average arm, a +3 arm {-arm_table[3]:.2f}, "
                   f"while +12 saves only {arm_table[12]:.3f}. Weak-armed catchers ({len(weak)} cards) average "
                   f"{weak['surplus'].mean():+.2f} vs price; +12 and up ({len(strong)}) {strong['surplus'].mean():+.2f}.")

    top = hb[hb["points"] <= 150].nlargest(4, "teams")
    names = ", ".join(f"{n} ({p} pts, {t} teams)" for n, p, t in zip(top["name"], top["points"], top["teams"]))
    out.append(f"Several of the most-used hitters are cheap filler, mostly +12 catchers: {names}. Their bats are well "
               f"below average ({top['raa_per_game'].mean():+.2f} runs a game); teams take them to save points for "
               f"stars while still shutting down the running game.")

    dp_rate = hb["DP"].sum() / hb["PA"].sum()
    out.append(f"Double plays happen on {dp_rate:.1%} of plate appearances and cost {-rv['DP']:.2f} runs each beyond "
               f"the out. One point of team infield glove saves {marg['infield']:.3f} runs a game (outfield {marg['outfield']:.3f}), "
               f"so a +0 shortstop gives up about {3 * marg['infield']:.2f} runs a game to a +3 one: real, but small next to the bat.")

    rp = pv[(pv["staff"] == "RP") & (pv["BF"] >= 400)]
    if len(rp):
        good, other = rp[rp["command"] >= 5], rp[rp["command"] < 5]
        out.append(f"Relievers with Control 5-6 beat their price by {good['surplus'].mean():+.2f} runs per 9 on average "
                   f"(Control 4 or less: {other['surplus'].mean():+.2f}). Pitcher points track results less closely than "
                   f"hitter points, so there is more to gain from picking pitchers carefully.")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="include the flagged teams")
    args = ap.parse_args()
    clean = not args.all

    bat = sd2000.load_hitters()
    pit = sd2000.load_pitchers()

    env = sd2000.league_env(bat)
    rv = sd2000.run_values(env)
    t = bat[["1B", "2B", "3B"]].sum()
    rv["1B_mix"] = float((t["1B"] * rv["1B"] + t["2B"] * rv["2B"] + t["3B"] * rv["3B"]) / t.sum())

    # ---- hitters: game results + modelled glove ----
    hb = sd2000.value_batting(bat, rv)
    used = hb.copy()
    spot_avg = {}
    for spot in SPOTS:
        vals, wts = [], []
        for pos, pa in zip(used["positions"], used["PA"]):
            f = max((f for p, f in sd2000._pos_list(pos) if p == spot), default=None)
            if f is not None:
                vals.append(f); wts.append(pa)
        spot_avg[spot] = float(np.average(vals, weights=wts)) if vals else 0.0
    marg = sd2000.fielding_marginals(env, hb["speed"].fillna(15), hb["PA"])
    arm_table = sd2000.catcher_arm_table(env, hb["speed"].fillna(15), hb["PA"])
    hb["glove"] = [sd2000.glove_runs(pos, spot_avg, marg, arm_table) for pos in hb["positions"]]
    first_spot = lambda pos: next((p for p, _ in sd2000._pos_list(pos) if p in SPOTS), None)  # noqa: E731
    hb["primary_spot"] = hb["positions"].map(first_spot)
    hb["glove_primary"] = [g.get(s, 0.0) if s else 0.0 for g, s in zip(hb["glove"], hb["primary_spot"])]
    hb["value"] = hb["raa_per_game"] + hb["glove_primary"]
    hb["weight"] = hb["PA"] / (hb["PA"] + sd2000.SHRINK_PA)
    hfit = fit(hb, "value")
    hb["surplus"] = hb["value"] - (hfit["intercept"] + hfit["slope"] * hb["points"])

    # ---- pitchers ----
    pv = sd2000.value_pitching(pit, rv)
    pv["staff"] = np.where(pv["role"] == "Starter", "SP", "RP")
    pv["weight"] = pv["BF"] / (pv["BF"] + sd2000.SHRINK_BF)
    pfits = {}
    pv["surplus"] = np.nan
    for staff, g in pv.groupby("staff"):
        pfits[staff] = fit(g, "runs_saved_per_9")
        pv.loc[g.index, "surplus"] = g["runs_saved_per_9"] - (pfits[staff]["intercept"] + pfits[staff]["slope"] * g["points"])

    OUT.mkdir(exist_ok=True)
    hb.drop(columns=["glove"]).sort_values("surplus", ascending=False).to_csv(OUT / "sd2000_hitters.csv", index=False)
    pv.sort_values("surplus", ascending=False).to_csv(OUT / "sd2000_pitchers.csv", index=False)

    total_teams = int(sd2000.read_meta().get("teams_total", hb["teams"].max()))
    meta = sd2000.read_meta()
    r = lambda x, d=4: None if pd.isna(x) else round(float(x), d)  # noqa: E731
    hitters = [{
        "n": x["name"], "y": int(x["year"]), "t": x["team"], "p": int(x["points"]), "ob": int(x["command"]),
        "sp": None if pd.isna(x["speed"]) else int(x["speed"]), "pos": x["positions"],
        "tm": int(x["teams"]), "g": int(x["G"]), "pa": int(x["PA"]), "hr": int(x["HR"]), "sb": int(x["SB"]),
        "cs": int(x["CS"]), "dp": int(x["DP"]), "bb": int(x["BB"]), "so": int(x["SO"]),
        "obp": r(x["obp"], 3), "slg": r(x["slg"], 3), "bat": r(x["raa_per_game"]), "run": r(x["running_runs"] / max(x["G"], 1)),
        "gl": {k: r(v) for k, v in x["glove"].items()}, "v": r(x["value"]), "s": r(x["surplus"]),
    } for _, x in hb.iterrows()]
    pitchers = [{
        "n": x["name"], "y": int(x["year"]), "t": x["team"], "p": int(x["points"]), "ctl": int(x["command"]),
        "ip": None if pd.isna(x["ip"]) else int(x["ip"]), "role": x["role"], "tm": int(x["teams"]),
        "g": int(x["G"]), "gs": int(x["GS"]), "ipt": r(x["IP"], 1), "era": r(x["era"], 2),
        "whip": r((x["H"] + x["BB"]) / x["IP"] if x["IP"] else np.nan, 3), "k9": r(x["SO"] * 9 / x["IP"] if x["IP"] else np.nan, 2),
        "bf": int(x["BF"]), "v": r(x["runs_saved_per_9"]), "s": r(x["surplus"]),
    } for _, x in pv.iterrows()]
    findings = make_findings(hb, pv, rv, marg, arm_table)
    for f in findings:
        print("-", f)
    data = {
        "meta": {**meta, "clean": clean, "teams_total": total_teams,
                 "league_runs_per_9": round(rv["runs_per_9"], 2),
                 "rv": {k: round(v, 3) for k, v in rv.items() if k in ("1B", "2B", "3B", "HR", "BB", "SO", "OUT", "SB", "CS", "DP")},
                 "glove_marginal": {k: round(v, 4) for k, v in marg.items()},
                 "arm_table": {str(k): round(v, 3) for k, v in arm_table.items()},
                 "findings": findings,
                 "spot_avg": {k: round(v, 2) for k, v in spot_avg.items()},
                 "catalog_cards": int(sd2000.read_meta().get("catalog_cards", 0))},
        "fit": {"hitters": hfit, **pfits}, "hitters": hitters, "pitchers": pitchers,
    }
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = (ROOT / "explorer" / "sd2000.html").read_text(encoding="utf-8").replace("__DATA__", blob)
    out = OUT / "showdown2000-explorer.html"
    out.write_text(html, encoding="utf-8")

    print(f"League: {rv['runs_per_9']:.2f} runs/9; run values " + ", ".join(f"{k} {rv[k]:+.3f}" for k in ("1B", "2B", "HR", "BB", "OUT", "SB", "CS", "DP")))
    print(f"One more point of team fielding saves (runs/game): " + ", ".join(f"{k} {v:.3f}" for k, v in marg.items()))
    print(f"Average fielding by spot: {spot_avg}")
    print("Catcher arm vs average (runs/game): " + ", ".join(f"+{k} {v:+.3f}" for k, v in arm_table.items()))
    print(f"{len(hb)} hitters, {len(pv)} pitchers valued; wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
