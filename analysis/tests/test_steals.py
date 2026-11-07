import random

import numpy as np
import pytest

from showdown.cards import EVENTS
from showdown.engine import (AVG, EMPTY, Env, _state, event_run_values, running_run_values, solve,
                             steal_rate)

PROBS = np.array([.03, .17, .17, .14, .09, .22, .03, .09, .01, .05])


def _simulate_with_steals(env, sol, innings, rng):
    """Dice simulation (no extra bases) that steals exactly when the exact solution says to."""
    cum = np.cumsum(env.probs)
    runs = 0
    for _ in range(innings):
        outs, b = 0, [0, 0, 0]
        while outs < 3:
            s = _state(outs, *(AVG if x else EMPTY for x in b))
            k = sol.steal[s]
            if k:                                      # 1 = the first legal steal option
                if b[0] and not b[1]:
                    caught = rng.randint(1, 20) + env.catcher_arm > env.runner_speed
                    b = [0, 0 if caught else 1, b[2]]
                else:
                    caught = rng.randint(1, 20) + env.catcher_arm > env.runner_speed - env.steal_third_penalty
                    b = [b[0], 0, 0 if caught else 1]
                if caught:
                    outs += 1
                    if outs == 3:
                        break
            ev = EVENTS[int(np.searchsorted(cum, rng.random(), side="right"))]
            r1, r2, r3 = b
            if ev in ("PU", "SO", "FB"):
                outs += 1
            elif ev == "GB":
                if outs == 2:
                    outs = 3
                elif r1:
                    if rng.randint(1, 20) + env.infield > env.batter_speed:
                        outs += 2
                        if outs < 3:
                            runs += r3; b = [0, 0, r2]
                    else:
                        outs += 1; runs += r3; b = [1, 0, r2]
                else:
                    outs += 1; runs += r3; b = [0, 0, r2]
            elif ev == "BB":
                if r1 and r2 and r3: runs += 1
                b = [1, 1 if r1 else r2, 1 if (r1 and r2) else r3]
            elif ev in ("1B", "1B+"):
                runs += r3; b = [1, r1, r2]
                if ev == "1B+" and not b[1]:
                    b = [0, 1, b[2]]
            elif ev == "2B":
                runs += r2 + r3; b = [0, 1, r1]
            elif ev == "3B":
                runs += r1 + r2 + r3; b = [0, 0, 1]
            elif ev == "HR":
                runs += r1 + r2 + r3 + 1; b = [0, 0, 0]
    return 9 * runs / innings


def test_steal_solver_matches_dice_simulation():
    env = Env(probs=tuple(PROBS), batter_speed=22, runner_speed=22, infield=4, catcher_arm=4,
              allow_extra_bases=False, allow_steals=True)
    sol = solve(env)
    assert any(sol.steal.values())                     # fast runners vs a weak arm do steal
    rng = random.Random(11)
    rng.random = np.random.default_rng(11).random
    sim = _simulate_with_steals(env, sol, innings=200_000, rng=rng)
    assert sim == pytest.approx(sol.runs_per_9, abs=0.12)


def test_steals_only_help_and_need_speed():
    base = solve(Env(probs=tuple(PROBS), runner_speed=22, catcher_arm=4))
    steal = solve(Env(probs=tuple(PROBS), runner_speed=22, catcher_arm=4, allow_steals=True))
    assert steal.runs_per_9 > base.runs_per_9
    slow_steals = solve(Env(probs=tuple(PROBS), runner_speed=10, catcher_arm=6, allow_steals=True))
    slow_no_steals = solve(Env(probs=tuple(PROBS), runner_speed=10, catcher_arm=6))
    assert slow_steals.runs_per_9 == pytest.approx(slow_no_steals.runs_per_9)   # slow runners never go


def test_fast_batter_worth_more_and_steals_more():
    env = Env(probs=tuple(PROBS), allow_steals=True, catcher_arm=6)
    sol = solve(env)
    slow, fast = event_run_values(env, sol, batter_speed=10), event_run_values(env, sol, batter_speed=25)
    one_b = EVENTS.index("1B")
    assert fast[one_b] > slow[one_b] + 0.05             # a fast runner's single is worth more
    assert steal_rate(env, sol, 25)["2nd"]["attempt"] > 0.9
    assert steal_rate(env, sol, 12)["2nd"]["attempt"] == 0


def test_running_values_signs():
    env = Env(probs=tuple(PROBS), allow_steals=True)
    rv = running_run_values(env, solve(env))
    assert rv["SB"] > 0 > rv["CS"]
    assert rv["DP"] < 0
    assert abs(rv["CS"]) > rv["SB"]                     # caught stealing costs more than a steal gains
