"""showdown2000.fun: its card catalog and real game results, turned into runs.

The site's cards are custom (modern players and legends) and their charts are only printed on the
card images, so we can't run the dice math on them. Instead we value them from what actually
happened in games: every player's Leaders stats for that card, pooled across all teams.

Data (read through the app while signed in; see analysis/README.md), one row per card that had
real playing time, with the card's catalog attributes and its Leaders stats pooled over every team:
  data/raw/sd2000_hitters.psv    name|year|team|tag|points|on-base|speed|positions|teams|G|AB|H|
                                 2B|3B|HR|SB|CS|BB|SO|DP
  data/raw/sd2000_pitchers.psv   name|year|team|tag|points|control|ip|role|teams|GS|IP|W|L|SV|
                                 H|R|ER|BB|SO|HR
  data/raw/sd2000_meta.json      when it was read, the cutoffs, and the teams left out
"tag" is the card's set or parallel ("pr" = Pennant Run, "career", "lumber", "asg"...; empty for
base cards). Different tags of one player-season are different cards with their own points.

How a result becomes runs: we build a league from the pooled game totals (how often each result
happens), solve it with the exact engine (steals and extra bases on, showdown2000.fun's rules),
and read off what each result is worth in runs in that league - singles, walks, home runs,
stolen bases, caught stealing, double plays. A card's runs above average is then its own
results times those values, compared with an average card over the same plate appearances.

Small samples are noisy, so each card's rate is shrunk toward average: a card with PA plate
appearances keeps PA / (PA + SHRINK_PA) of its difference from average.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from .cards import EVENTS, RAW
from .engine import Env, event_run_values, running_run_values, solve

SHRINK_PA = 200          # plate appearances at which a card's own rate gets half the weight
SHRINK_BF = 250          # batters faced, same idea for pitchers
SPEED_LETTER = {"A": 20, "B": 15, "C": 10}
EXPAND = {"LF/RF": ["LF/RF"], "OF": ["LF/RF", "CF"], "IF": ["1B", "2B", "3B", "SS"]}


HITTER_COLS = ["name", "year", "team", "tag", "points", "command", "speed", "positions", "teams",
               "G", "AB", "H", "2B", "3B", "HR", "SB", "CS", "BB", "SO", "DP"]
PITCHER_COLS = ["name", "year", "team", "tag", "points", "command", "ip", "role", "teams",
                "GS", "IP", "W", "L", "SV", "H", "R", "ER", "BB", "SO", "HR"]


def _read(name: str, cols: list[str]) -> pd.DataFrame:
    path = RAW / f"sd2000_{name}.psv"
    if not path.exists():
        raise FileNotFoundError(f"{path.name} missing (see analysis/README.md: showdown2000.fun data)")
    df = pd.read_csv(path, sep="|", names=cols, header=None, keep_default_na=False,
                     na_values=[""], dtype={"tag": str, "speed": str, "positions": str})
    df["tag"] = df["tag"].fillna("")
    df["key"] = df["name"] + "|" + df["year"].astype(str) + "|" + df["team"] + "|" + df["tag"]
    return df


def read_meta() -> dict:
    """When and how the data was collected, which teams were left out and why."""
    path = RAW / "sd2000_meta.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def parse_positions(text: str) -> list[tuple[str, int]]:
    """'CF +2 LF/RF +1' -> [('CF', 2), ('LF/RF', 1)];  'SS +0 2B/3B +2' -> [('SS',0),('2B',2),('3B',2)]."""
    out = []
    for pos, f in re.findall(r"([A-Z0-9/]+)\s*\+(\d+)", str(text or "")):
        parts = EXPAND.get(pos) or (pos.split("/") if pos != "LF/RF" else [pos])
        for p in parts:
            out.append((p, int(f)))
    if not out and "DH" in str(text):
        out.append(("DH", 0))
    return out


def pool_versions(df: pd.DataFrame, same: list[str], stats: list[str], size: str) -> pd.DataFrame:
    """Merge versions of one player-season (base, career, lumber, refractor...) that print the same
    card numbers (`same`), adding up their game stats. Versions with different printed numbers
    (e.g. an All-Star version with more Speed) stay separate cards.

    The merged card keeps the points, tag and team count of its most-played version; `versions`
    lists every version and `points_range` the spread of their prices (usually none). Team counts
    are added up, so a team that used two versions counts twice.
    """
    df = df.copy()
    df["_tag"] = df["tag"].replace("", "base")
    keys = ["name", "year", "team"] + same
    rows = []
    for _, g in df.groupby(keys, sort=False, dropna=False):
        g = g.sort_values(size, ascending=False)
        top = g.iloc[0].copy()
        for c in stats:
            top[c] = g[c].sum()
        top["versions"] = ", ".join(g["_tag"])
        top["version_tags"] = "|".join(g["tag"])
        top["n_versions"] = len(g)
        lo, hi = int(g["points"].min()), int(g["points"].max())
        top["points_range"] = "" if lo == hi else f"{lo}-{hi}"
        rows.append(top)
    out = pd.DataFrame(rows).drop(columns="_tag").reset_index(drop=True)
    out["key"] = out["name"] + "|" + out["year"].astype(str) + "|" + out["team"] + "|" + out["tag"]
    return out


def load_hitters(pool: bool = True) -> pd.DataFrame:
    """Hitter cards with their pooled batting stats (flagged teams already left out)."""
    df = _read("hitters", HITTER_COLS)
    sp = df["speed"].astype(str).str.upper()
    df["speed"] = pd.to_numeric(sp, errors="coerce").fillna(sp.map(SPEED_LETTER))
    df["positions"] = [", ".join(f"{p}+{f}" for p, f in parse_positions(pos)) or "DH" for pos in df["positions"]]
    df["is_pitcher"] = False
    df["SF"] = df["SH"] = 0      # always 0 in the Leaders tables
    df["PA"] = df["AB"] + df["BB"] + df["SF"] + df["SH"]
    df["1B"] = df["H"] - df["2B"] - df["3B"] - df["HR"]
    if pool:
        df = pool_versions(df, ["command", "speed", "positions"],
                           ["teams", "G", "AB", "H", "2B", "3B", "HR", "SB", "CS", "BB", "SO", "DP",
                            "SF", "SH", "PA", "1B"], size="PA")
    return df


def load_pitchers(pool: bool = True) -> pd.DataFrame:
    """Pitcher cards (role Starter / Reliever / Closer) with their pooled pitching stats."""
    df = _read("pitchers", PITCHER_COLS)
    df["is_pitcher"] = True
    df["G"] = df["GS"]          # the Leaders table's G column is always 0 for pitchers; GS is real
    if pool:
        df = pool_versions(df, ["command", "ip", "role"],
                           ["teams", "G", "GS", "IP", "W", "L", "SV", "H", "R", "ER", "BB", "SO", "HR"],
                           size="IP")
    return df


# ---------------------------------------------------------------------------------------------
# Batting
# ---------------------------------------------------------------------------------------------
def league_env(bat: pd.DataFrame, gb_share: float = 0.5) -> Env:
    """A league built from the pooled game totals.

    The Leaders tables don't split outs into grounders and fly balls; `gb_share` is the share of
    non-strikeout outs that are grounders (calibrate_gb_share picks it to match real double plays).
    """
    t = bat[["PA", "AB", "H", "1B", "2B", "3B", "HR", "BB", "SO", "SF", "SH"]].sum()
    other_outs = t["AB"] - t["H"] - t["SO"] + t["SF"] + t["SH"]
    probs = dict.fromkeys(EVENTS, 0.0)
    probs.update({"SO": t["SO"], "GB": other_outs * gb_share, "FB": other_outs * (1 - gb_share), "BB": t["BB"],
                  "1B": t["1B"], "2B": t["2B"], "3B": t["3B"], "HR": t["HR"]})
    p = np.array([probs[e] for e in EVENTS], float)
    p /= p.sum()

    used = bat                                                   # weight by playing time
    w = used["PA"].to_numpy(float)
    speed = float(np.average(used["speed"].fillna(15), weights=w)) if len(used) else 15.0
    fielding = {}
    for spot in ("C", "1B", "2B", "3B", "SS", "LF/RF", "CF"):
        vals, wts = [], []
        for (posstr, pa) in zip(used["positions"], w):
            best = max((f for p, f in _pos_list(posstr) if p == spot), default=None)
            if best is not None:
                vals.append(best); wts.append(pa)
        fielding[spot] = float(np.average(vals, weights=wts)) if vals else 0.0
    infield = fielding["1B"] + fielding["2B"] + fielding["3B"] + fielding["SS"]
    outfield = 2 * fielding["LF/RF"] + fielding["CF"]
    env = Env(probs=tuple(p), batter_speed=speed, runner_speed=speed, infield=infield,
              outfield=outfield, catcher_arm=fielding["C"], allow_steals=True)
    return env


def _pos_list(posstr: str) -> list[tuple[str, int]]:
    out = []
    for part in str(posstr or "").split(","):
        part = part.strip()
        if "+" in part:
            p, f = part.split("+")
            out.append((p, int(f)))
        elif part:
            out.append((part, 0))
    return out


def calibrate_gb_share(bat: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    """Find the grounder share at which the engine's double-play rate matches the real one.

    Returns the share and a table of real vs modelled double plays per plate appearance by Speed.
    """
    from .engine import dp_per_pa
    real = bat["DP"].sum() / bat["PA"].sum()
    shares = _speed_shares(bat["speed"].fillna(15), bat["PA"])

    def model(g):
        env = league_env(bat, g)
        sol = solve(env)
        return sum(w * dp_per_pa(env, sol, sp) for sp, w in shares.items()), env, sol

    lo, hi = 0.1, 0.9
    for _ in range(25):
        mid = (lo + hi) / 2
        if model(mid)[0] > real:
            hi = mid
        else:
            lo = mid
    g = (lo + hi) / 2
    _, env, sol = model(g)
    buckets = pd.cut(bat["speed"], [0, 11, 13, 15, 17, 19, 21, 30])
    tab = bat.groupby(buckets, observed=True).agg(speed=("speed", "mean"), DP=("DP", "sum"), PA=("PA", "sum"))
    tab["real_dp_per_pa"] = tab["DP"] / tab["PA"]
    tab["model_dp_per_pa"] = [dp_per_pa(env, sol, sp) for sp in tab["speed"]]
    return g, tab


def run_values(env: Env) -> dict:
    from .engine import steal_third_run_values
    sol = solve(env)
    rv = dict(zip(EVENTS, event_run_values(env, sol)))
    rv.update(running_run_values(env, sol))
    rv.update(steal_third_run_values(env, sol))
    rv["OUT"] = (rv["GB"] + rv["FB"]) / 2
    rv["runs_per_9"] = sol.runs_per_9
    rv["pa_per_inning"] = sol.pa_per_inning
    return rv


def value_batting(bat: pd.DataFrame, rv: dict) -> pd.DataFrame:
    """Runs above average from real results, per plate appearance and per game."""
    df = bat.copy()
    outs = df["AB"] - df["H"] - df["SO"] + df["SF"] + df["SH"]
    runs = (df["1B"] * rv["1B"] + df["2B"] * rv["2B"] + df["3B"] * rv["3B"] + df["HR"] * rv["HR"]
            + df["BB"] * rv["BB"] + df["SO"] * rv["SO"] + outs * rv["OUT"]
            + df["SB"] * rv["SB"] + df["CS"] * rv["CS"] + df["DP"] * rv["DP"])
    lg_per_pa = runs.sum() / df["PA"].sum()          # average card, same plate appearances
    df["game_runs"] = runs - lg_per_pa * df["PA"]
    df["raa_pa"] = df["game_runs"] / df["PA"]
    df["raa_pa_shrunk"] = df["raa_pa"] * df["PA"] / (df["PA"] + SHRINK_PA)
    df["raa_per_game"] = df["raa_pa_shrunk"] * rv["pa_per_inning"]   # one lineup slot, 9 innings
    df["running_runs"] = df["SB"] * rv["SB"] + df["CS"] * rv["CS"]
    df["obp"] = (df["H"] + df["BB"]) / (df["AB"] + df["BB"] + df["SF"]).replace(0, np.nan)
    df["slg"] = (df["1B"] + 2 * df["2B"] + 3 * df["3B"] + 4 * df["HR"]) / df["AB"].replace(0, np.nan)
    df["sb_per_game"] = df["SB"] / df["G"]
    df["dp_per_pa"] = df["DP"] / df["PA"]
    return df


def _speed_shares(speeds: pd.Series, weights: pd.Series) -> pd.Series:
    w = weights.groupby(speeds.round()).sum()
    return w / w.sum()


SPOTS = ("C", "1B", "2B", "3B", "SS", "LF/RF", "CF")
INFIELD = ("1B", "2B", "3B", "SS")
OUTFIELD = ("LF/RF", "CF")


def spot_averages(bat: pd.DataFrame) -> dict:
    """Average glove of the players who actually play each spot (weighted by plate appearances)."""
    out = {}
    for spot in SPOTS:
        vals, wts = [], []
        for pos, pa in zip(bat["positions"], bat["PA"]):
            f = max((f for p, f in _pos_list(pos) if p == spot), default=None)
            if f is not None:
                vals.append(f)
                wts.append(pa)
        out[spot] = float(np.average(vals, weights=wts)) if vals else 0.0
    return out


def team_glove_tables(env: Env, bat: pd.DataFrame, spot_avg: dict, values=range(0, 9)) -> dict:
    """Runs per game an infielder or outfielder with each glove saves vs the average glove there.

    A fielder's number is never rolled alone: double plays roll d20 + the four infielders' total
    against the batter's Speed, and throws on sends and tag-ups roll d20 + the three outfielders'
    total against the runner's Speed (+5 going home, +5 with two outs). So a player's glove is
    worth what it does to that team total, with the other spots average. Each glove is priced by
    solving the whole league at that total (the offense only sends a runner when it pays), averaged
    over lineups of every Speed weighted by how much that Speed plays. It is not a fixed amount
    per point: once the total beats a runner's Speed on every roll, more glove does nothing.
    """
    from dataclasses import replace
    shares = _speed_shares(bat["speed"].fillna(15), bat["PA"])
    cache = {}

    def runs(field, total):
        k = (field, round(total, 4))
        if k not in cache:
            cache[k] = sum(w * solve(replace(env, batter_speed=float(sp), runner_speed=float(sp),
                                             **{field: total})).runs_per_9 for sp, w in shares.items())
        return cache[k]

    out = {}
    for spot in INFIELD + OUTFIELD:
        field = "infield" if spot in INFIELD else "outfield"
        base_total = getattr(env, field)
        base = runs(field, base_total)
        out[spot] = {int(f): base - runs(field, base_total + f - spot_avg[spot]) for f in values}
    return out


def steal_model(bat: pd.DataFrame, rv: dict, pa_per_game: float, q_third: float = 0.15,
                arms=range(0, 17), max_boost: float = 4.0) -> dict:
    """What a catcher's arm is worth, from the steal attempts runners actually made.

    Rule (showdown2000.fun): the catcher rolls d20 + arm; the runner is out if that beats his
    Speed; stealing 3rd is 5 harder. The Leaders table doesn't split steals of 2nd and 3rd, so
    `q_third` of attempts are assumed to be steals of 3rd.

    Two answers, both in runs per team-game compared with the league's real mix of catcher arms:
      fixed  every real attempt still happens against this catcher; only the success rate
             changes. Simple, but ignores that runners stop running against a strong arm.
      deter  runners only go when the steal pays: when they are at least T likely to make it
             against that catcher, T being the break-even success rate (about 75% here). Real
             runners succeed 75-85% of the time, so they behave close to this. Each runner keeps
             his real eagerness: against a catcher he can run on he goes as often as he did when
             the steal was on, at most `max_boost` times his real rate. Attempts by runners who
             should never go against any catcher in use (slow runners) are kept as they were.
    """
    df = bat.copy()
    df["opp"] = df["1B"] + df["BB"]                      # times on first (singles + walks)
    df["att"] = df["SB"] + df["CS"]
    cat = df[df["positions"].str.match(r"^C\+")].copy()
    cat["arm"] = cat["positions"].str.extract(r"^C\+(\d+)")[0].astype(int)
    mix = cat.groupby("arm")["PA"].sum()
    mix = mix / mix.sum()
    arms_in_use = mix.index.to_numpy(float)
    w_mix = mix.to_numpy(float)

    def p_safe(sp, a):
        p2 = np.clip((sp - a) / 20, 0, 1)
        p3 = np.clip((sp - 5 - a) / 20, 0, 1)
        return (1 - q_third) * p2 + q_third * p3

    def ev(sp, a):                                        # runs per attempt
        p2 = np.clip((sp - a) / 20, 0, 1)
        p3 = np.clip((sp - 5 - a) / 20, 0, 1)
        return ((1 - q_third) * (p2 * rv["SB"] + (1 - p2) * rv["CS"])
                + q_third * (p3 * rv["SB3"] + (1 - p3) * rv["CS3"]))

    sp = df["speed"].fillna(15).to_numpy(float)
    att, opp = df["att"].to_numpy(float), df["opp"].to_numpy(float)
    ps = p_safe(sp[:, None], arms_in_use[None, :])       # [cards, arms]

    def fit(T):
        on = (ps >= T).astype(float)
        on_share = on @ w_mix
        pred = np.where(on_share > 0, (on * ps) @ w_mix / np.maximum(on_share, 1e-9), ps @ w_mix)
        return on_share, pred

    # break-even success rate, blending steals of 2nd and 3rd
    gain = (1 - q_third) * rv["SB"] + q_third * rv["SB3"]
    loss = -((1 - q_third) * rv["CS"] + q_third * rv["CS3"])
    T = round(float(loss / (gain + loss)), 3)
    on_share, pred = fit(T)
    boost = 1 / np.maximum(on_share, 1 / max_boost)       # how much more often he goes when it's on
    always = np.where(on_share > 0, 0.0, att)
    games = df["PA"].sum() / pa_per_game                 # team-games in this sample

    def runs_fixed(a):
        return float(np.sum(att * ev(sp, a))) / games

    def runs_deter(a):
        n = np.where(on_share > 0, att * boost * (p_safe(sp, a) >= T), always)
        return float(np.sum(n * ev(sp, a))) / games

    avg_fixed = sum(w * runs_fixed(a) for a, w in mix.items())
    avg_deter = sum(w * runs_deter(a) for a, w in mix.items())
    df["pred_succ"] = pred
    buckets = pd.cut(df["speed"], [0, 13, 16, 18, 20, 22, 24, 30])
    rows = []
    for b_, g in df.groupby(buckets, observed=True):
        rows.append({"speed": str(b_), "attempts": int(g["att"].sum()),
                     "attempts_per_time_on_1st": g["att"].sum() / g["opp"].sum(),
                     "real_success": g["SB"].sum() / max(g["att"].sum(), 1),
                     "model_success": float(np.average(g["pred_succ"], weights=np.maximum(g["att"], 1e-9)))})
    return {
        "T": T, "q_third": q_third, "arm_mix": {int(k): float(v) for k, v in mix.items()},
        "fixed": {int(a): avg_fixed - runs_fixed(a) for a in arms},
        "deter": {int(a): avg_deter - runs_deter(a) for a in arms},
        "check": pd.DataFrame(rows),
        "steal_runs_per_game": avg_fixed,
    }


def glove_runs(positions: str, tables: dict) -> dict:
    """Runs per game this card's glove saves at each spot it plays, vs the average glove there.

    `tables[spot][value]` comes from team_glove_tables (infield, outfield) and steal_model
    (catcher). Values past the end of a table use its nearest entry.
    """
    out = {}
    for p, f in _pos_list(positions):
        t = tables.get(p)
        if not t:
            continue
        v = t.get(int(f), t[max(t)] if f > max(t) else t[min(t)])
        out[p] = max(out.get(p, -99), v)
    return out


# ---------------------------------------------------------------------------------------------
# Pitching
# ---------------------------------------------------------------------------------------------
def value_pitching(pit: pd.DataFrame, rv: dict) -> pd.DataFrame:
    """Runs saved per 9 innings vs average, from what batters did against each card (FIP-style).

    Uses strikeouts, walks, home runs and hits allowed (the results the Leaders table lists),
    valued with the same run values as batting.
    """
    df = pit.copy()
    ip = df["IP"]
    outs = np.round(ip * 3)          # the site shows innings as decimals: 52.3 = 52 1/3 -> 157 outs
    hits_non_hr = df["H"] - df["HR"]
    bip_outs = (outs - df["SO"]).clip(lower=0)
    bf = outs + df["H"] + df["BB"]
    runs = (hits_non_hr * rv["1B_mix"] + df["HR"] * rv["HR"] + df["BB"] * rv["BB"]
            + df["SO"] * rv["SO"] + bip_outs * rv["OUT"])
    lg_per_bf = runs.sum() / bf.sum()
    df["BF"] = bf
    df["runs_vs_avg"] = runs - lg_per_bf * bf                  # positive = gave up more than average
    rate = -df["runs_vs_avg"] / bf * bf / (bf + SHRINK_BF)        # runs saved per batter, shrunk
    df["runs_saved_per_9"] = rate * rv["pa_per_inning"] * 9
    df["era"] = df["ER"] * 9 / ip.replace(0, np.nan) if "ER" in df else np.nan
    return df
