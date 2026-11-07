import random

import numpy as np
import pytest

from showdown.cards import EVENTS
from showdown.engine import Env, matchup, p_defense_wins, p_pitcher_chart, solve


def test_pitcher_chart_probability():
    # d20 + 3 > 7  <=>  d20 >= 5  -> 16 faces
    assert p_pitcher_chart(onbase=7, control=3) == 16 / 20
    assert p_pitcher_chart(onbase=10, control=0) == 10 / 20   # d20 > 10
    assert p_pitcher_chart(onbase=3, control=6) == 1.0
    assert p_pitcher_chart(onbase=26, control=0) == 0.0


def test_defense_roll():
    # d20 + 4 > 15 <=> d20 >= 12 -> 9 faces
    assert p_defense_wins(15, 0, 4) == 9 / 20
    assert p_defense_wins(20, 10, 0) == 0.0


def test_matchup_sums_to_one():
    b = np.array([0, 3, 2, 2, 3, 6, 1, 1, 0, 2])
    p = np.array([2, 5, 6, 4, 1, 1, 0, 1, 0, 0])
    assert matchup(b, 8, p, 4).sum() == pytest.approx(1)


def test_all_outs_scores_nothing():
    probs = np.zeros(len(EVENTS)); probs[EVENTS.index("SO")] = 1
    assert solve(Env(probs=tuple(probs))).runs_per_9 == 0


def test_all_homers_never_ends():
    # 50% HR, 50% SO -> each inning is a negative binomial: E[HR before 3 outs] = 3
    probs = np.zeros(len(EVENTS)); probs[EVENTS.index("SO")] = .5; probs[EVENTS.index("HR")] = .5
    assert solve(Env(probs=tuple(probs))).runs_per_9 == pytest.approx(27)


# --- an independent dice simulator (no extra-base attempts) to check the exact solver ----------

def _simulate(probs, batter_speed, infield, innings, rng):
    runs = 0
    cum = np.cumsum(probs)
    for _ in range(innings):
        outs, bases = 0, [0, 0, 0]
        while outs < 3:
            ev = EVENTS[int(np.searchsorted(cum, rng.random(), side="right"))]
            r1, r2, r3 = bases
            if ev in ("PU", "SO", "FB"):
                outs += 1
            elif ev == "GB":
                if outs == 2:
                    outs = 3
                elif r1:
                    if rng.randint(1, 20) + infield > batter_speed:   # double play
                        outs += 2
                        if outs < 3:
                            runs += r3; bases = [0, 0, r2]
                    else:
                        outs += 1; runs += r3; bases = [1, 0, r2]
                else:
                    outs += 1; runs += r3; bases = [0, 0, r2]
            elif ev == "BB":
                if r1 and r2 and r3: runs += 1
                bases = [1, 1 if r1 else r2, 1 if (r1 and r2) else r3]
            elif ev in ("1B", "1B+"):
                runs += r3; bases = [1, r1, r2]
                if ev == "1B+" and not bases[1]:
                    bases = [0, 1, bases[2]]
            elif ev == "2B":
                runs += r2 + r3; bases = [0, 1, r1]
            elif ev == "3B":
                runs += r1 + r2 + r3; bases = [0, 0, 1]
            elif ev == "HR":
                runs += r1 + r2 + r3 + 1; bases = [0, 0, 0]
    return 9 * runs / innings


def test_solver_matches_dice_simulation():
    probs = np.array([.03, .17, .17, .14, .09, .22, .03, .09, .01, .05])
    env = Env(probs=tuple(probs), batter_speed=15, infield=4, allow_extra_bases=False)
    exact = solve(env).runs_per_9
    rng = random.Random(7)
    np_rng_state = np.random.default_rng(7)
    rng.random = np_rng_state.random  # fast uniform draws
    sim = _simulate(probs, 15, 4, innings=200_000, rng=rng)
    # standard error of runs/9 with 200k innings is ~0.03
    assert sim == pytest.approx(exact, abs=0.12)


def test_extra_bases_only_help_offense():
    probs = np.array([.03, .17, .17, .14, .09, .22, .03, .09, .01, .05])
    base = solve(Env(probs=tuple(probs), allow_extra_bases=False)).runs_per_9
    smart = solve(Env(probs=tuple(probs), runner_speed=20)).runs_per_9
    assert smart >= base


def test_speed_reduces_double_plays():
    probs = np.array([0, .2, .3, .1, .1, .2, 0, .07, 0, .03])
    slow = solve(Env(probs=tuple(probs), batter_speed=10, runner_speed=10)).runs_per_9
    fast = solve(Env(probs=tuple(probs), batter_speed=20, runner_speed=20)).runs_per_9
    assert fast > slow
