"""The game engine: exact expected runs for MLB Showdown 2000 half-innings.

Instead of rolling dice millions of times, we treat a half-inning as a Markov chain over the
24 baseball "states" (0/1/2 outs x 8 combinations of runners on base) and solve it exactly.
That gives noise-free answers, so small differences between cards are real, not dice luck.

Rules implemented (2000 rulebook, advanced game, no strategy cards):

  Pitch      Pitcher rolls d20 + Control. If the total is GREATER than the batter's On-Base,
             the result comes from the pitcher's chart; otherwise (ties too) the batter's chart.
  Swing      Batter rolls d20 on that chart.
  PU / SO    Batter out, runners hold.
  FB         Batter out. With fewer than 2 outs the lead runner may tag up (see "extra base").
  GB         Batter out, runners advance one base. Runner on 1st with < 2 outs: that runner is
             forced out, and the defense rolls d20 + infield fielding; if that beats the
             batter's Speed it's a double play.
  BB         Batter to 1st, forced runners advance.
  1B         Everyone advances one base.  1B+: then the batter takes 2nd if it is open.
  2B / 3B    Everyone advances two / three bases.
  HR         Everyone scores.
  Extra base After a 1B or 2B (or tag on a FB) the lead runner may try for one more base.
             Defense rolls d20 + outfield fielding; if that beats runner Speed (+5 going home,
             +5 with two outs) he's out, otherwise safe. The offense only tries when it raises
             expected runs (we solve for the best choice).

Not modelled (yet): stolen bases, strategy cards, pitcher fatigue past his IP, platoon/handedness
(the 2000 set has no platoon effect on the cards), and individual fielders.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .cards import EVENTS

N_STATES = 24  # outs * 8 + bases bitmask (1 = runner on 1st, 2 = 2nd, 4 = 3rd)
E = {e: i for i, e in enumerate(EVENTS)}


def p_pitcher_chart(onbase: float, control: float) -> float:
    """Chance the pitcher's chart is used: P(d20 + control > on-base)."""
    faces = 20 - (onbase - control)
    return float(np.clip(faces, 0, 20)) / 20


def p_defense_wins(runner_speed: float, bonus: float, fielding: float) -> float:
    """P(d20 + fielding > speed + bonus): the throw / double-play roll succeeds."""
    faces = 20 - (runner_speed + bonus - fielding)
    return float(np.clip(faces, 0, 20)) / 20


def matchup(batter_chart: np.ndarray, onbase: float,
            pitcher_chart: np.ndarray, control: float) -> np.ndarray:
    """Probability of each result (EVENTS order) for one batter vs one pitcher."""
    pp = p_pitcher_chart(onbase, control)
    return pp * pitcher_chart / 20 + (1 - pp) * batter_chart / 20


@dataclass(frozen=True)
class Env:
    """Everything the inning needs: result probabilities and who's running / fielding."""
    probs: tuple                 # probability of each EVENTS result per plate appearance
    batter_speed: float = 15.0   # used for double plays
    runner_speed: float = 15.0   # used for extra-base attempts
    infield: float = 4.0         # summed infield fielding (1B+2B+3B+SS)
    outfield: float = 3.0        # summed outfield fielding (LF+CF+RF)
    bonus_home: float = 5.0
    bonus_two_outs: float = 5.0
    allow_extra_bases: bool = True


def _state(outs: int, b1: int, b2: int, b3: int) -> int:
    return outs * 8 + b1 + 2 * b2 + 4 * b3


def _unpack(s: int):
    return s // 8, s & 1, (s >> 1) & 1, (s >> 2) & 1


END = -1  # three outs


def _go(outs, b1, b2, b3):
    return END if outs >= 3 else _state(outs, b1, b2, b3)


def outcomes(s: int, event: str, env: Env):
    """List of choices for the offense; each choice is a list of (prob, runs, next_state)."""
    o, r1, r2, r3 = _unpack(s)
    two_out = env.bonus_two_outs if o == 2 else 0.0
    opts = []

    if event in ("PU", "SO"):
        opts.append([(1.0, 0, _go(o + 1, r1, r2, r3))])

    elif event == "FB":
        opts.append([(1.0, 0, _go(o + 1, r1, r2, r3))])
        if o + 1 < 3 and env.allow_extra_bases:
            if r3:   # tag from third
                p_out = p_defense_wins(env.runner_speed, env.bonus_home, env.outfield)
                opts.append([(1 - p_out, 1, _go(o + 1, r1, r2, 0)),
                             (p_out, 0, _go(o + 2, r1, r2, 0))])
            elif r2:  # tag from second
                p_out = p_defense_wins(env.runner_speed, 0, env.outfield)
                opts.append([(1 - p_out, 0, _go(o + 1, r1, 0, 1)),
                             (p_out, 0, _go(o + 2, r1, 0, 0))])

    elif event == "GB":
        if o == 2:
            opts.append([(1.0, 0, END)])
        elif r1:
            p_dp = p_defense_wins(env.batter_speed, 0, env.infield)
            dp = (p_dp, 0, END) if o == 1 else (p_dp, r3, _go(2, 0, 0, r2))
            fc = (1 - p_dp, r3, _go(o + 1, 1, 0, r2))  # runner from 1st out, batter safe
            opts.append([dp, fc])
        else:
            opts.append([(1.0, r3, _go(o + 1, 0, 0, r2))])

    elif event == "BB":
        if r1 and r2 and r3:
            opts.append([(1.0, 1, _state(o, 1, 1, 1))])
        elif r1 and r2:
            opts.append([(1.0, 0, _state(o, 1, 1, 1))])
        elif r1:
            opts.append([(1.0, 0, _state(o, 1, 1, r3))])
        else:
            opts.append([(1.0, 0, _state(o, 1, r2, r3))])

    elif event in ("1B", "1B+"):
        runs = r3
        hold = [(1.0, runs, _state(o, 1, r1, r2))]
        opts.append(hold)
        if env.allow_extra_bases:
            if r2:   # runner who reached 3rd tries for home
                p_out = p_defense_wins(env.runner_speed, env.bonus_home + two_out, env.outfield)
                opts.append([(1 - p_out, runs + 1, _state(o, 1, r1, 0)),
                             (p_out, runs, _go(o + 1, 1, r1, 0))])
            elif r1:  # runner who reached 2nd tries for 3rd
                p_out = p_defense_wins(env.runner_speed, two_out, env.outfield)
                opts.append([(1 - p_out, runs, _state(o, 1, 0, 1)),
                             (p_out, runs, _go(o + 1, 1, 0, 0))])
        if event == "1B+":
            opts = [[(p, r, _batter_takes_second(n)) for p, r, n in opt] for opt in opts]

    elif event == "2B":
        runs = r2 + r3
        opts.append([(1.0, runs, _state(o, 0, 1, r1))])
        if r1 and env.allow_extra_bases:  # runner from 1st (now on 3rd) tries for home
            p_out = p_defense_wins(env.runner_speed, env.bonus_home + two_out, env.outfield)
            opts.append([(1 - p_out, runs + 1, _state(o, 0, 1, 0)),
                         (p_out, runs, _go(o + 1, 0, 1, 0))])

    elif event == "3B":
        opts.append([(1.0, r1 + r2 + r3, _state(o, 0, 0, 1))])

    elif event == "HR":
        opts.append([(1.0, r1 + r2 + r3 + 1, _state(o, 0, 0, 0))])

    else:
        raise ValueError(event)
    return opts


def _batter_takes_second(n: int) -> int:
    if n == END:
        return END
    o, b1, b2, b3 = _unpack(n)
    if b1 and not b2:
        return _state(o, 0, 1, b3)
    return n


@dataclass
class Solution:
    V: np.ndarray            # expected runs from each state to end of inning
    visits: np.ndarray       # expected visits to each state per inning (from 0 outs, empty)
    runs_per_9: float
    pa_per_inning: float
    choice: dict             # (state, event) -> index of chosen option


def _choice_value(opt, V):
    return sum(p * (r + (0.0 if n == END else V[n])) for p, r, n in opt)


def solve(env: Env, tol: float = 1e-12, max_iter: int = 10_000) -> Solution:
    probs = np.asarray(env.probs, dtype=float)
    if abs(probs.sum() - 1) > 1e-9:
        raise ValueError(f"probabilities sum to {probs.sum()}")
    table = {(s, e): outcomes(s, e, env) for s in range(N_STATES) for e in EVENTS if probs[E[e]] > 0}

    V = np.zeros(N_STATES)
    for _ in range(max_iter):
        new = np.zeros(N_STATES)
        for (s, e), opts in table.items():
            new[s] += probs[E[e]] * max(_choice_value(o, V) for o in opts)
        if np.max(np.abs(new - V)) < tol:
            V = new
            break
        V = new
    else:
        raise RuntimeError("did not converge")

    choice, T = {}, np.zeros((N_STATES, N_STATES))
    for (s, e), opts in table.items():
        k = int(np.argmax([_choice_value(o, V) for o in opts]))
        choice[(s, e)] = k
        for p, _, n in opts[k]:
            if n != END:
                T[s, n] += probs[E[e]] * p
    start = np.zeros(N_STATES)
    start[0] = 1.0
    visits = np.linalg.solve((np.eye(N_STATES) - T).T, start)
    return Solution(V=V, visits=visits, runs_per_9=9 * V[0],
                    pa_per_inning=float(visits.sum()), choice=choice)


def event_run_values(env: Env, sol: Solution, batter_speed: float | None = None) -> np.ndarray:
    """Linear weights: average runs each result is worth in this environment.

    For each result, average over the states batters actually bat in of
    (runs scored + run expectancy after) - run expectancy before.
    Pass batter_speed to see how a faster or slower batter changes the GB value (double plays).
    """
    if batter_speed is not None:
        env = replace(env, batter_speed=batter_speed)
    w = sol.visits / sol.visits.sum()
    rv = np.zeros(len(EVENTS))
    for i, e in enumerate(EVENTS):
        total = 0.0
        for s in range(N_STATES):
            if w[s] == 0:
                continue
            best = max(_choice_value(o, sol.V) for o in outcomes(s, e, env))
            total += w[s] * (best - sol.V[s])
        rv[i] = total
    return rv
