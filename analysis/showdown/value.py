"""Turn cards into runs, and runs into value-per-point.

The "league" is every 2000 card: each batter faces the pitcher pool weighted by innings (a
starter with 7 IP faces about 7x as many batters as a 1-IP reliever), and each pitcher faces
the batter pool with every batter weighted equally.

Batters are valued with linear weights (the sabermetric standard): how many runs per game
this hitter adds compared with an average 2000 hitter batting in the same slot of an
average lineup.  Pitchers are valued by how many runs per 9 innings they allow against an
average lineup, compared with an average 2000 pitcher.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from .cards import EVENTS, OUT_EVENTS
from .engine import Env, solve, event_run_values

CHART = [f"c_{e}" for e in EVENTS]
SPEEDS = (10, 15, 20)


@dataclass
class League:
    batters: pd.DataFrame
    pitchers: pd.DataFrame
    env: Env
    rv_by_speed: dict          # speed -> run value of each result
    pa_per_inning: float
    runs_per_9: float
    pair_probs: np.ndarray     # [batter, pitcher, event]
    pitcher_weights: np.ndarray


def _fielding_totals(batters: pd.DataFrame) -> tuple[float, float]:
    """Average fielding of a typical starter at each spot, summed for the infield/outfield."""
    pos = batters.groupby("primary_pos")["primary_fielding"].mean()
    infield = pos["1B"] + pos["2B"] + pos["3B"] + pos["SS"]
    outfield = 2 * pos["LF-RF"] + pos["CF"]
    return float(infield), float(outfield)


def build_league(cards: pd.DataFrame) -> League:
    bat = cards[~cards["is_pitcher"]].reset_index(drop=True)
    pit = cards[cards["is_pitcher"]].reset_index(drop=True)

    bchart = bat[CHART].to_numpy(float) / 20          # [nb, 10]
    pchart = pit[CHART].to_numpy(float) / 20          # [np, 10]
    ob = bat["onbase"].to_numpy(float)[:, None]
    ctl = pit["control"].to_numpy(float)[None, :]
    pp = np.clip(20 - (ob - ctl), 0, 20) / 20         # [nb, np] chance pitcher's chart is used
    pair = pp[..., None] * pchart[None, :, :] + (1 - pp[..., None]) * bchart[:, None, :]

    w = pit["ip"].to_numpy(float)
    w = w / w.sum()
    lg_probs = np.einsum("bpe,p->e", pair, w) / len(bat)

    infield, outfield = _fielding_totals(bat)
    speed = float(bat["speed"].mean())
    env = Env(probs=tuple(lg_probs), batter_speed=speed, runner_speed=speed,
              infield=infield, outfield=outfield)
    sol = solve(env)
    rv = {s: event_run_values(env, sol, batter_speed=s) for s in SPEEDS}
    rv["league"] = event_run_values(env, sol)
    return League(bat, pit, env, rv, sol.pa_per_inning, sol.runs_per_9, pair, w)


def value_batters(lg: League) -> pd.DataFrame:
    probs = np.einsum("bpe,p->be", lg.pair_probs, lg.pitcher_weights)   # vs average pitching
    lg_rv = float(np.asarray(lg.env.probs) @ lg.rv_by_speed["league"])  # ~0 by construction
    out = lg.batters.copy()
    rv_pa = np.array([probs[i] @ lg.rv_by_speed[int(s)] for i, s in enumerate(out["speed"])])
    out["runs_per_pa"] = rv_pa - lg_rv
    out["raa_per_game"] = out["runs_per_pa"] * lg.pa_per_inning   # one lineup slot, 9 innings
    out["reach_base_pct"] = 1 - probs[:, [EVENTS.index(e) for e in OUT_EVENTS]].sum(axis=1)
    out["hr_pct"] = probs[:, EVENTS.index("HR")]
    ctl = lg.pitchers["control"].to_numpy(float)
    out["own_chart_pct"] = [float(np.sum(lg.pitcher_weights * np.clip(ob - ctl, 0, 20) / 20))
                            for ob in out["onbase"]]
    out["out_slots"] = out[[f"c_{e}" for e in OUT_EVENTS]].sum(axis=1)
    out["xbh_slots"] = out[["c_2B", "c_3B", "c_HR"]].sum(axis=1)
    return out


def value_pitchers(lg: League) -> pd.DataFrame:
    probs = lg.pair_probs.mean(axis=0)              # vs average lineup: [np, 10]
    out = lg.pitchers.copy()
    ra9 = []
    for i in range(len(out)):
        ra9.append(solve(replace(lg.env, probs=tuple(probs[i]))).runs_per_9)
    out["ra9"] = ra9
    out["runs_saved_per_9"] = lg.runs_per_9 - out["ra9"]
    out["runs_saved_per_outing"] = out["runs_saved_per_9"] * out["ip"] / 9
    out["opp_reach_base_pct"] = 1 - probs[:, [EVENTS.index(e) for e in OUT_EVENTS]].sum(axis=1)
    ob = lg.batters["onbase"].to_numpy(float)
    out["own_chart_pct"] = [float(np.mean(np.clip(20 - (ob - c), 0, 20) / 20)) for c in out["control"]]
    out["out_slots"] = out[[f"c_{e}" for e in OUT_EVENTS]].sum(axis=1)
    return out


def add_surplus(df: pd.DataFrame, value_col: str, group_col: str | None = None) -> pd.DataFrame:
    """Fit value ~ points (straight line) and report how far each card beats its price.

    surplus  = runs this card produces minus what a typical card at the same points produces.
    """
    df = df.copy()
    groups = [(None, df.index)] if group_col is None else df.groupby(group_col).groups.items()
    for _, idx in groups:
        x = df.loc[idx, "points"].to_numpy(float)
        y = df.loc[idx, value_col].to_numpy(float)
        slope, intercept = np.polyfit(x, y, 1)
        df.loc[idx, "expected_at_price"] = intercept + slope * x
        df.loc[idx, "runs_per_100pts_market"] = slope * 100
    df["surplus"] = df[value_col] - df["expected_at_price"]
    return df


def batter_marginals(lg: League) -> pd.DataFrame:
    """What one more point of each attribute is worth in runs, averaged over real cards.

    Each change is applied to every batter card (where legal) and re-valued exactly.
    """
    base = value_batters(lg)
    pchart = lg.pitchers[CHART].to_numpy(float) / 20
    ctl = lg.pitchers["control"].to_numpy(float)
    w = lg.pitcher_weights

    def raa(chart, ob, speed):
        pp = np.clip(20 - (ob - ctl), 0, 20) / 20
        probs = (pp[:, None] * pchart + (1 - pp[:, None]) * chart[None, :] / 20).T @ w
        return (probs @ lg.rv_by_speed[speed]) * lg.pa_per_inning

    def swap(chart, frm, to):
        """Move one die face from result `frm` to result `to` (None if impossible)."""
        i, j = EVENTS.index(frm), EVENTS.index(to)
        if chart[i] == 0:
            return None
        c = chart.copy(); c[i] -= 1; c[j] += 1
        return c

    changes = {
        "+1 On-Base": lambda c, ob, s: (c, ob + 1, s),
        "Speed C->B / B->A (+5)": lambda c, ob, s: (c, ob, s + 5) if s < 20 else None,
        "GB face -> 1B": lambda c, ob, s: (swap(c, "GB", "1B"), ob, s),
        "SO face -> 1B": lambda c, ob, s: (swap(c, "SO", "1B"), ob, s),
        "FB face -> 1B": lambda c, ob, s: (swap(c, "FB", "1B"), ob, s),
        "Out face -> BB": lambda c, ob, s: (swap(c, "GB", "BB") if c[EVENTS.index("GB")] else swap(c, "FB", "BB"), ob, s),
        "1B face -> 2B": lambda c, ob, s: (swap(c, "1B", "2B"), ob, s),
        "1B face -> HR": lambda c, ob, s: (swap(c, "1B", "HR"), ob, s),
        "GB face -> SO": lambda c, ob, s: (swap(c, "GB", "SO"), ob, s),
    }
    rows = []
    for name, fn in changes.items():
        deltas = []
        for _, r in base.iterrows():
            chart = r[CHART].to_numpy(float)
            res = fn(chart, float(r["onbase"]), int(r["speed"]))
            if res is None or res[0] is None:
                continue
            c2, ob2, s2 = res
            deltas.append(raa(c2, ob2, s2) - raa(chart, float(r["onbase"]), int(r["speed"])))
        rows.append({"change": name, "runs_per_game": float(np.mean(deltas)), "cards": len(deltas)})
    return pd.DataFrame(rows)


def pitcher_marginals(lg: League) -> pd.DataFrame:
    base = value_pitchers(lg)
    bchart = lg.batters[CHART].to_numpy(float) / 20
    ob = lg.batters["onbase"].to_numpy(float)

    def ra9(chart, c):
        pp = np.clip(20 - (ob - c), 0, 20) / 20
        probs = (pp[:, None] * chart[None, :] / 20 + (1 - pp[:, None]) * bchart).mean(axis=0)
        return solve(replace(lg.env, probs=tuple(probs))).runs_per_9

    def swap(chart, frm, to):
        i, j = EVENTS.index(frm), EVENTS.index(to)
        if chart[i] == 0:
            return None
        c = chart.copy(); c[i] -= 1; c[j] += 1
        return c

    changes = {
        "+1 Control": lambda c, k: (c, k + 1),
        "1B face -> PU": lambda c, k: (swap(c, "1B", "PU"), k),
        "1B face -> SO": lambda c, k: (swap(c, "1B", "SO"), k),
        "1B face -> GB": lambda c, k: (swap(c, "1B", "GB"), k),
        "1B face -> FB": lambda c, k: (swap(c, "1B", "FB"), k),
        "BB face -> SO": lambda c, k: (swap(c, "BB", "SO"), k),
        "HR face -> 1B": lambda c, k: (swap(c, "HR", "1B"), k),
        "FB face -> PU": lambda c, k: (swap(c, "FB", "PU"), k),
    }
    rows = []
    sample = base  # all pitchers; each solve is fast
    for name, fn in changes.items():
        deltas = []
        for _, r in sample.iterrows():
            chart = r[CHART].to_numpy(float)
            c2, k2 = fn(chart, float(r["control"]))
            if c2 is None:
                continue
            deltas.append(r["ra9"] - ra9(c2, k2))   # positive = fewer runs allowed
        rows.append({"change": name, "runs_saved_per_9": float(np.mean(deltas)), "cards": len(deltas)})
    return pd.DataFrame(rows)
