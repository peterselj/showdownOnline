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


def load_hitters() -> pd.DataFrame:
    """Hitter cards with their pooled batting stats (flagged teams already left out)."""
    df = _read("hitters", HITTER_COLS)
    sp = df["speed"].astype(str).str.upper()
    df["speed"] = pd.to_numeric(sp, errors="coerce").fillna(sp.map(SPEED_LETTER))
    df["positions"] = [", ".join(f"{p}+{f}" for p, f in parse_positions(pos)) or "DH" for pos in df["positions"]]
    df["is_pitcher"] = False
    df["SF"] = df["SH"] = 0      # always 0 in the Leaders tables
    df["PA"] = df["AB"] + df["BB"] + df["SF"] + df["SH"]
    df["1B"] = df["H"] - df["2B"] - df["3B"] - df["HR"]
    return df


def load_pitchers() -> pd.DataFrame:
    """Pitcher cards (role Starter / Reliever / Closer) with their pooled pitching stats."""
    df = _read("pitchers", PITCHER_COLS)
    df["is_pitcher"] = True
    df["G"] = df["GS"]          # the Leaders table's G column is always 0 for pitchers; GS is real
    return df


# ---------------------------------------------------------------------------------------------
# Batting
# ---------------------------------------------------------------------------------------------
def league_env(bat: pd.DataFrame) -> Env:
    """A league built from the pooled game totals."""
    t = bat[["PA", "AB", "H", "1B", "2B", "3B", "HR", "BB", "SO", "SF", "SH"]].sum()
    other_outs = t["AB"] - t["H"] - t["SO"] + t["SF"] + t["SH"]
    probs = dict.fromkeys(EVENTS, 0.0)
    probs.update({"SO": t["SO"], "GB": other_outs / 2, "FB": other_outs / 2, "BB": t["BB"],
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


def run_values(env: Env) -> dict:
    sol = solve(env)
    rv = dict(zip(EVENTS, event_run_values(env, sol)))
    rv.update(running_run_values(env, sol))
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


def fielding_marginals(env: Env, speeds: pd.Series, weights: pd.Series) -> dict:
    """Runs per game one more point of team fielding saves, at each kind of spot.

    Fast runners steal and take extra bases; slow ones don't. So we average over lineups of
    every Speed in the league, weighted by how much each Speed actually plays.
    """
    from dataclasses import replace
    w = _speed_shares(speeds, weights)
    out = {"infield": 0.0, "outfield": 0.0, "catcher": 0.0}
    for spd, share in w.items():
        e = replace(env, batter_speed=float(spd), runner_speed=float(spd))
        for name, field in (("infield", "infield"), ("outfield", "outfield"), ("catcher", "catcher_arm")):
            lo = solve(replace(e, **{field: getattr(e, field) - 1})).runs_per_9
            hi = solve(replace(e, **{field: getattr(e, field) + 1})).runs_per_9
            out[name] += share * (lo - hi) / 2
    return out


def _speed_shares(speeds: pd.Series, weights: pd.Series) -> pd.Series:
    w = weights.groupby(speeds.round()).sum()
    return w / w.sum()


def catcher_arm_table(env: Env, speeds: pd.Series, weights: pd.Series, arms=range(0, 17)) -> dict:
    """Runs per game a catcher with each arm saves compared with the league-average arm.

    Not a straight line: against a +10 arm only the very fastest runners steal, so one more point
    barely matters; drop to +5 and Speed-20 runners start running freely. So each arm is priced
    directly, averaging over lineups of every Speed weighted by how much that Speed plays.
    """
    from dataclasses import replace
    shares = _speed_shares(speeds, weights)
    def runs_allowed(arm: float) -> float:
        return sum(share * solve(replace(env, batter_speed=float(spd), runner_speed=float(spd),
                                         catcher_arm=float(arm))).runs_per_9
                   for spd, share in shares.items())
    base = runs_allowed(env.catcher_arm)
    return {int(a): base - runs_allowed(a) for a in arms}


def glove_runs(positions: str, spot_avg: dict, marg: dict, arm_table: dict | None = None) -> dict:
    """Runs per game this card's glove saves at each spot it plays, vs the average glove there.

    Infield and outfield count toward team totals (sum of 4 or 3 players), so a point is a point;
    a catcher's arm uses `arm_table` (see catcher_arm_table) when given.
    """
    kind = {"C": "catcher", "1B": "infield", "2B": "infield", "3B": "infield", "SS": "infield",
            "LF/RF": "outfield", "CF": "outfield"}
    out = {}
    for p, f in _pos_list(positions):
        if p not in kind:
            continue
        if p == "C" and arm_table:
            v = arm_table.get(int(f), arm_table[max(arm_table)] if f > max(arm_table) else arm_table[min(arm_table)])
        else:
            v = (f - spot_avg[p]) * marg[kind[p]]
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
