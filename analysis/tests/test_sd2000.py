import numpy as np
import pandas as pd
import pytest

from showdown import sd2000
from showdown.cards import EVENTS
from showdown.engine import Env

PROBS = tuple(np.array([.0, .18, .17, .16, .09, .22, .0, .1, .01, .07]))


def test_parse_positions():
    assert sd2000.parse_positions("CF+2,LF/RF+1") == [("CF", 2), ("LF/RF", 1)]
    assert sd2000.parse_positions("SS +0 2B/3B +2") == [("SS", 0), ("2B", 2), ("3B", 2)]
    assert sd2000.parse_positions("OF+1") == [("LF/RF", 1), ("CF", 1)]
    assert sd2000.parse_positions("IF+1") == [("1B", 1), ("2B", 1), ("3B", 1), ("SS", 1)]
    assert sd2000.parse_positions("DH") == [("DH", 0)]


def test_load_hitters_from_file(tmp_path, monkeypatch):
    (tmp_path / "sd2000_hitters.psv").write_text(
        "Austin Hedges|2025|CLE|pr|80|5|10|C+12|81|4232|13970|2577|493|0|371|35|124|1762|4173|402\n"
        "Alex Call|2024|WSN||550|10|A|LF/RF+1|10|455|1783|598|152|0|66|130|58|269|394|25\n", encoding="utf-8")
    monkeypatch.setattr(sd2000, "RAW", tmp_path)
    h = sd2000.load_hitters()
    assert list(h["tag"]) == ["pr", ""]
    assert list(h["speed"]) == [10, 20]                  # letter A -> 20
    assert h.loc[1, "PA"] == 1783 + 269
    assert h.loc[1, "1B"] == 598 - 152 - 0 - 66
    assert h.loc[0, "positions"] == "C+12"


def _bat(**kw):
    row = dict(AB=400, H=100, **{"2B": 20, "3B": 2}, HR=10, BB=40, SO=80, SB=0, CS=0, DP=10, SF=0, SH=0, G=100)
    row.update(kw)
    df = pd.DataFrame([row])
    df["PA"] = df["AB"] + df["BB"]
    df["1B"] = df["H"] - df["2B"] - df["3B"] - df["HR"]
    return df


def test_value_batting_credits_steals_and_power():
    rv = sd2000.run_values(Env(probs=PROBS, allow_steals=True))
    base = _bat()
    pool = pd.concat([base, _bat(SB=40, CS=5), _bat(HR=30, H=120)], ignore_index=True)
    v = sd2000.value_batting(pool, rv)["game_runs"].to_numpy()
    assert v[1] > v[0]                                   # same hitting plus 40 steals at 89%
    assert v[2] > v[0]                                   # 20 more homers
    assert v.sum() == pytest.approx(0, abs=1e-9)         # runs above the pool's own average


def test_catcher_arm_table_is_monotonic_and_curved():
    env = Env(probs=PROBS, allow_steals=True, catcher_arm=10)
    speeds = pd.Series([10, 15, 20, 26]); weights = pd.Series([1, 2, 2, 1])
    t = sd2000.catcher_arm_table(env, speeds, weights, arms=range(2, 15))
    vals = [t[a] for a in range(2, 15)]
    assert all(b >= a - 1e-12 for a, b in zip(vals, vals[1:]))      # better arm never hurts
    assert t[10] == pytest.approx(0)
    assert (t[10] - t[5]) > 3 * (t[14] - t[10])                    # losing arm hurts more than gaining it helps


def test_glove_runs_uses_arm_table_for_catchers():
    marg = {"infield": 0.05, "outfield": 0.07, "catcher": 0.0}
    avg = dict.fromkeys(["C", "1B", "2B", "3B", "SS", "LF/RF", "CF"], 1.0)
    g = sd2000.glove_runs("C+5, 1B+3", avg, marg, arm_table={5: -0.1, 10: 0.0})
    assert g["C"] == -0.1
    assert g["1B"] == pytest.approx((3 - 1) * 0.05)


def test_value_pitching_outs_from_decimal_innings():
    pit = pd.DataFrame([dict(IP=52.3, H=40, BB=15, SO=50, HR=5, ER=20),
                        dict(IP=52.3, H=60, BB=25, SO=30, HR=10, ER=35)])
    rv = sd2000.run_values(Env(probs=PROBS))
    rv["1B_mix"] = rv["1B"]
    out = sd2000.value_pitching(pit, rv)
    assert out.loc[0, "BF"] == 157 + 40 + 15             # 52.3 innings = 157 outs
    assert out.loc[0, "runs_saved_per_9"] > 0 > out.loc[1, "runs_saved_per_9"]
