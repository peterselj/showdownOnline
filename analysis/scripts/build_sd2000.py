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


IMG_BASE = "https://img.showdown2000.fun/"


def card_images(x, role: str) -> list[str]:
    """Image file names on img.showdown2000.fun for each version of this card (best guess at the
    site's naming: '{year}_2000_{Name}_{ROLE}_{tag_}{TEAM}.png', checked by scripts/check_card_images.py)."""
    import unicodedata
    name = unicodedata.normalize("NFKD", str(x["name"])).encode("ascii", "ignore").decode()
    name = "_".join(name.replace(".", "").replace("'", "").split())
    out = []
    for tag in str(x.get("version_tags", x["tag"]) or "").split("|") if "version_tags" in x else [x["tag"]]:
        mid = f"_{tag}" if tag else ""
        out.append(f"{int(x['year'])}_2000_{name}_{role}{mid}_{x['team']}.png")
    known = _known_images()
    return out if known is None else [n if n in known else "" for n in out]


def _known_images():
    """Image names confirmed by scripts/check_card_images.py, or None if it hasn't been run."""
    global _KNOWN
    if "_KNOWN" not in globals():
        path = ROOT / "data" / "raw" / "sd2000_card_images.txt"
        _KNOWN = set(path.read_text(encoding="utf-8").split()) if path.exists() else None
    return _KNOWN


def make_findings(hb: pd.DataFrame, pv: pd.DataFrame, rv: dict, tables: dict, steals: dict, gb_share: float) -> list[str]:
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
        d, f = steals["deter"], steals["fixed"]
        cat["arm"] = cat["positions"].str.extract(r"C\+(\d+)")[0].astype(float)
        weak, strong = cat[cat["arm"] <= 7], cat[cat["arm"] >= 12]
        out.append(f"Catcher arm, priced from every real steal attempt: compared with the league's catchers, a +5 arm "
                   f"costs {-d[5]:.2f} runs a game and a +3 {-d[3]:.2f}, while +12 gains {d[12]:+.2f} and +14 {d[14]:+.2f}. "
                   f"Runners go when they are at least {steals['T']:.0%} to make it, which matches real success rates; "
                   f"if they never adjusted, the spread would be wider (+5 {f[5]:+.2f}, +14 {f[14]:+.2f}). "
                   f"Weak-armed catchers ({len(weak)} cards) average {weak['surplus'].mean():+.2f} vs price; "
                   f"+12 and up ({len(strong)}) {strong['surplus'].mean():+.2f}.")

    top = hb[hb["points"] <= 150].nlargest(4, "teams")
    names = ", ".join(f"{n} ({p} pts, {t} teams)" for n, p, t in zip(top["name"], top["points"], top["teams"]))
    out.append(f"Several of the most-used hitters are cheap filler, mostly +12 catchers: {names}. Their bats are well "
               f"below average ({top['raa_per_game'].mean():+.2f} runs a game); teams take them to save points for "
               f"stars while still shutting down the running game.")

    dp_rate = hb["DP"].sum() / hb["PA"].sum()
    ss, cf = tables["SS"], tables["CF"]
    out.append(f"Double plays happen on {dp_rate:.1%} of plate appearances (the model matches this by Speed once "
               f"{gb_share:.0%} of non-strikeout outs are grounders) and cost {-rv['DP']:.2f} runs each beyond the out. "
               f"A shortstop's glove moves the infield total: +0 costs {-ss[0]:.2f} runs a game vs an average one, "
               f"+5 gains {ss[5]:+.2f}. Center field matters more through throws on the bases: +0 {cf[0]:+.2f}, "
               f"+4 {cf[4]:+.2f}. Real, but small next to the bat.")

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

    gb_share, dp_check = sd2000.calibrate_gb_share(bat)
    env = sd2000.league_env(bat, gb_share)
    rv = sd2000.run_values(env)
    t = bat[["1B", "2B", "3B"]].sum()
    rv["1B_mix"] = float((t["1B"] * rv["1B"] + t["2B"] * rv["2B"] + t["3B"] * rv["3B"]) / t.sum())

    # ---- hitters: game results + modelled glove ----
    hb = sd2000.value_batting(bat, rv)
    spot_avg = sd2000.spot_averages(hb)
    tables = sd2000.team_glove_tables(env, hb, spot_avg)
    steals = sd2000.steal_model(hb, rv, rv["pa_per_inning"] * 9)
    tables["C"] = steals["deter"]
    hb["glove"] = [sd2000.glove_runs(pos, tables) for pos in hb["positions"]]
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
        "ver": x["versions"], "pr": x["points_range"], "img": card_images(x, "HITTER"),
    } for _, x in hb.iterrows()]
    pitchers = [{
        "n": x["name"], "y": int(x["year"]), "t": x["team"], "p": int(x["points"]), "ctl": int(x["command"]),
        "ip": None if pd.isna(x["ip"]) else int(x["ip"]), "role": x["role"], "tm": int(x["teams"]),
        "g": int(x["G"]), "gs": int(x["GS"]), "ipt": r(x["IP"], 1), "era": r(x["era"], 2),
        "whip": r((x["H"] + x["BB"]) / x["IP"] if x["IP"] else np.nan, 3), "k9": r(x["SO"] * 9 / x["IP"] if x["IP"] else np.nan, 2),
        "bf": int(x["BF"]), "v": r(x["runs_saved_per_9"]), "s": r(x["surplus"]),
        "ver": x["versions"], "pr": x["points_range"], "img": card_images(x, "PITCHER"),
    } for _, x in pv.iterrows()]
    findings = make_findings(hb, pv, rv, tables, steals, gb_share)
    for f in findings:
        print("-", f)
    data = {
        "meta": {**meta, "clean": clean, "teams_total": total_teams,
                 "league_runs_per_9": round(rv["runs_per_9"], 2),
                 "rv": {k: round(v, 3) for k, v in rv.items() if k in ("1B", "2B", "3B", "HR", "BB", "SO", "OUT", "SB", "CS", "DP")},
                 "arm_table": {str(k): round(v, 3) for k, v in steals["deter"].items()},
                 "arm_table_fixed": {str(k): round(v, 3) for k, v in steals["fixed"].items()},
                 "steal_threshold": steals["T"], "gb_share": round(gb_share, 3),
                 "glove_tables": {sp: {str(k): round(v, 3) for k, v in t.items()} for sp, t in tables.items() if sp != "C"},
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
    print(f"Grounder share calibrated to real double plays: {gb_share:.3f}")
    print(dp_check[["speed", "real_dp_per_pa", "model_dp_per_pa"]].round(4).to_string())
    print(f"Steal threshold T = {steals['T']}; check by Speed:")
    print(steals["check"].round(3).to_string(index=False))
    print("Catcher arm, with deterrence: " + ", ".join(f"+{k} {v:+.3f}" for k, v in steals["deter"].items()))
    print("Catcher arm, fixed attempts:  " + ", ".join(f"+{k} {v:+.3f}" for k, v in steals["fixed"].items()))
    for sp in ("1B", "2B", "3B", "SS", "LF/RF", "CF"):
        print(f"{sp:>5} (avg +{spot_avg[sp]:.1f}): " + ", ".join(f"+{k} {v:+.3f}" for k, v in tables[sp].items()))
    print(f"{len(hb)} hitters, {len(pv)} pitchers valued; wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
