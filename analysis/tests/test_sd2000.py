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


HITTERS = (
    "Austin Hedges|2025|CLE|pr|80|5|10|C+12|81|4232|13970|2577|493|0|371|35|124|1762|4173|402\n"
    "Alex Call|2024|WSN||550|10|A|LF/RF+1|10|455|1783|598|152|0|66|130|58|269|394|25\n"
    "Rickey Henderson|1982|OAK|career|480|10|28.0|CF+2,LF/RF+1|31|1643|6415|1809|287|10|189|1629|326|1396|1573|31\n"
    "Rickey Henderson|1982|OAK|lumber|480|10|28.0|CF+2,LF/RF+1|3|365|1443|482|69|0|75|985|41|396|311|3\n"
    "Aaron Judge|2025|NYY|ASG|700|11|B|LF/RF+1|9|565|2492|786|136|0|209|9|9|438|686|80\n"
    "Aaron Judge|2025|NYY|pr|660|11|13|LF/RF+1|8|428|1743|645|130|0|197|0|3|396|518|33\n")


def test_load_hitters_from_file(tmp_path, monkeypatch):
    (tmp_path / "sd2000_hitters.psv").write_text(HITTERS, encoding="utf-8")
    monkeypatch.setattr(sd2000, "RAW", tmp_path)
    h = sd2000.load_hitters(pool=False)
    assert list(h["tag"])[:2] == ["pr", ""]
    assert list(h["speed"])[:2] == [10, 20]              # letter A -> 20
    assert h.loc[1, "PA"] == 1783 + 269
    assert h.loc[1, "1B"] == 598 - 152 - 0 - 66
    assert h.loc[0, "positions"] == "C+12"


def test_versions_with_same_printed_card_are_merged(tmp_path, monkeypatch):
    (tmp_path / "sd2000_hitters.psv").write_text(HITTERS, encoding="utf-8")
    monkeypatch.setattr(sd2000, "RAW", tmp_path)
    h = sd2000.load_hitters()
    rickey = h[h["name"] == "Rickey Henderson"]
    assert len(rickey) == 1                              # career + lumber print the same card
    r = rickey.iloc[0]
    assert r["SB"] == 1629 + 985 and r["teams"] == 34
    assert r["versions"] == "career, lumber" and r["tag"] == "career"
    assert len(h[h["name"] == "Aaron Judge"]) == 2       # ASG has Speed 15 (B), pr has 13: different cards


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


def _league_cards():
    rows = []
    for i, (sp, pos, sb, cs) in enumerate([(10, "C+5", 2, 6), (12, "C+12", 1, 3), (15, "SS+3", 10, 6),
                                          (20, "CF+2", 60, 20), (20, "C+8", 5, 3), (24, "LF/RF+1", 120, 25),
                                          (28, "CF+3", 300, 40), (14, "2B+4", 5, 5), (11, "1B+0", 0, 1)]):
        rows.append(dict(name=f"p{i}", year=2025, team="X", tag="", points=300, command=9, speed=sp,
                         positions=pos, teams=5, G=150, AB=550, H=150, **{"2B": 30, "3B": 2}, HR=15,
                         SB=sb, CS=cs, BB=60, SO=110, DP=12, SF=0, SH=0))
    df = pd.DataFrame(rows)
    df["PA"] = df["AB"] + df["BB"]
    df["1B"] = df["H"] - df["2B"] - df["3B"] - df["HR"]
    return df


def test_gb_share_calibration_matches_real_double_plays():
    from showdown.engine import dp_per_pa, solve
    bat = _league_cards()
    g, tab = sd2000.calibrate_gb_share(bat)
    assert 0.1 < g < 0.9
    env = sd2000.league_env(bat, g)
    sol = solve(env)
    shares = sd2000._speed_shares(bat["speed"], bat["PA"])
    model = sum(w * dp_per_pa(env, sol, sp) for sp, w in shares.items())
    assert model == pytest.approx(bat["DP"].sum() / bat["PA"].sum(), rel=1e-3)


def test_team_glove_tables_rise_with_glove():
    bat = _league_cards()
    env = sd2000.league_env(bat, 0.4)
    t = sd2000.team_glove_tables(env, bat, sd2000.spot_averages(bat), values=range(0, 6))
    for spot in ("SS", "CF"):
        vals = [t[spot][f] for f in range(0, 6)]
        assert all(b >= a - 1e-12 for a, b in zip(vals, vals[1:]))   # more glove never hurts
        assert vals[0] < 0 < vals[-1]


def test_steal_model_tables():
    bat = _league_cards()
    env = sd2000.league_env(bat, 0.4)
    rv = sd2000.run_values(env)
    m = sd2000.steal_model(bat, rv, rv["pa_per_inning"] * 9)
    gain = 0.85 * rv["SB"] + 0.15 * rv["SB3"]
    loss = -(0.85 * rv["CS"] + 0.15 * rv["CS3"])
    assert m["T"] == pytest.approx(loss / (gain + loss), abs=1e-3)       # break-even success rate
    for key in ("fixed", "deter"):
        vals = [m[key][a] for a in range(0, 17)]
        assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:]))       # a better arm never hurts
    avg = sum(w * m["fixed"][a] for a, w in m["arm_mix"].items())
    assert avg == pytest.approx(0, abs=1e-9)                          # measured vs the real catcher mix


def test_glove_runs_reads_the_tables():
    tables = {"C": {5: -0.1, 10: 0.0}, "1B": {0: -0.02, 3: 0.09}}
    g = sd2000.glove_runs("C+5, 1B+3", tables)
    assert g == {"C": -0.1, "1B": 0.09}
    assert sd2000.glove_runs("C+14", tables)["C"] == 0.0               # past the end: nearest entry


def test_value_pitching_outs_from_decimal_innings():
    pit = pd.DataFrame([dict(IP=52.3, H=40, BB=15, SO=50, HR=5, ER=20),
                        dict(IP=52.3, H=60, BB=25, SO=30, HR=10, ER=35)])
    rv = sd2000.run_values(Env(probs=PROBS))
    rv["1B_mix"] = rv["1B"]
    out = sd2000.value_pitching(pit, rv)
    assert out.loc[0, "BF"] == 157 + 40 + 15             # 52.3 innings = 157 outs
    assert out.loc[0, "runs_saved_per_9"] > 0 > out.loc[1, "runs_saved_per_9"]


def test_shrink_to_price_trusts_more_teams_and_finds_the_spreads():
    rng = np.random.default_rng(5)
    n_cards = 4000
    points = rng.uniform(50, 600, n_cards)
    teams = rng.choice([1, 2, 5, 10, 30], n_cards)
    pa = rng.choice([300, 1000, 3000], n_cards)
    talent_sd, team_sd, noise_var = 0.017, 0.035, 0.25
    rate = (-0.08 + 0.0003 * points + rng.normal(0, talent_sd, n_cards)
            + rng.normal(0, team_sd / np.sqrt(teams)) + rng.normal(0, np.sqrt(noise_var / pa)))
    out = sd2000.shrink_to_price(rate, pa, teams, points, noise_var)
    assert out["talent_sd"] == pytest.approx(talent_sd, rel=0.2)
    assert out["team_sd"] == pytest.approx(team_sd, rel=0.2)
    w = pd.Series(out["weight"])
    one = w[(teams == 1) & (pa == 1000)].mean()
    many = w[(teams == 30) & (pa == 1000)].mean()
    assert one < 0.3 < many                              # one team's results count far less
