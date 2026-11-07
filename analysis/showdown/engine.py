"""The game engine: exact expected runs for MLB Showdown half-innings.

Instead of rolling dice millions of times, we treat a half-inning as a Markov chain over the
baseball "states" (0/1/2 outs x who is on which base) and solve it exactly. That gives
noise-free answers, so small differences between cards are real, not dice luck.

Rules implemented (2000 rulebook advanced game, which 2004/05 and showdown2000.fun share;
no strategy cards):

  Steal      Before the pitch, a runner on 1st may steal an open 2nd, or a runner on 2nd an
             open 3rd (one attempt per batter, never home). Catcher rolls d20 + arm; if that
             beats the runner's Speed he's out (stealing 3rd: runner -5, as showdown2000.fun
             plays it). The offense only tries when it raises expected runs.
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

Runners come in two kinds: league-average ones, and optionally one "tagged" runner with his own
Speed. The tagged runner is the batter being valued, so his Speed counts for every steal, extra
base and double play he's part of after he reaches base, not just while he's batting.

Not modelled (yet): strategy cards, icons, pitcher fatigue past his IP, platoon/handedness,
double steals, and the 1B+ counting as that batter's steal.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache

import numpy as np

from .cards import EVENTS

E = {e: i for i, e in enumerate(EVENTS)}
EMPTY, AVG, TAG = 0, 1, 2      # what's on a base: nobody, an average runner, the tagged runner
END = -1                       # three outs


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
    batter_speed: float = 15.0   # average batter's Speed (double plays)
    runner_speed: float = 15.0   # average runner's Speed (extra bases, steals)
    infield: float = 4.0         # summed infield fielding (1B+2B+3B+SS)
    outfield: float = 3.0        # summed outfield fielding (LF+CF+RF)
    catcher_arm: float = 6.0     # catcher's fielding: throws out base stealers
    bonus_home: float = 5.0
    bonus_two_outs: float = 5.0
    steal_third_penalty: float = 5.0
    allow_extra_bases: bool = True
    allow_steals: bool = False
    tag_speed: float | None = None   # Speed of the tagged runner; None = no tagged runner


# ---------------------------------------------------------------------------------------------
# States: (outs, 1st, 2nd, 3rd) with each base EMPTY / AVG / TAG.
# ---------------------------------------------------------------------------------------------
def _state(outs: int, b1: int, b2: int, b3: int) -> int:
    return outs * 27 + b1 + 3 * b2 + 9 * b3


def _unpack(s: int):
    return s // 27, s % 3, (s // 3) % 3, (s // 9) % 3


def _go(outs, b1, b2, b3):
    return END if outs >= 3 else _state(outs, b1, b2, b3)


@lru_cache(maxsize=None)
def states(tagged: bool) -> tuple:
    """Every state that can occur: no tagged runner, or (if tagged) at most one."""
    out = []
    for o in range(3):
        for b3 in range(3):
            for b2 in range(3):
                for b1 in range(3):
                    n_tag = (b1, b2, b3).count(TAG)
                    if n_tag == 0 or (tagged and n_tag == 1):
                        out.append(_state(o, b1, b2, b3))
    return tuple(out)


START = _state(0, EMPTY, EMPTY, EMPTY)
NORMAL_STATES = states(False)        # the 24 classic states


def _speed(kind: int, env: Env) -> float:
    if kind == TAG:
        return env.runner_speed if env.tag_speed is None else env.tag_speed
    return env.runner_speed


def outcomes(s: int, event: str, env: Env, batter: int = AVG):
    """List of choices for the offense; each choice is a list of (prob, runs, next_state).

    `batter` is who bats: AVG, or TAG for the batter being valued (he becomes the tagged runner).
    """
    o, b1, b2, b3 = _unpack(s)
    two_out = env.bonus_two_outs if o == 2 else 0.0
    bat = batter
    bat_speed = _speed(TAG, env) if batter == TAG else env.batter_speed
    on = lambda b: int(b != EMPTY)  # noqa: E731
    opts = []

    if event in ("PU", "SO"):
        opts.append([(1.0, 0, _go(o + 1, b1, b2, b3))])

    elif event == "FB":
        opts.append([(1.0, 0, _go(o + 1, b1, b2, b3))])
        if o + 1 < 3 and env.allow_extra_bases:
            if b3:   # tag from third
                p_out = p_defense_wins(_speed(b3, env), env.bonus_home, env.outfield)
                opts.append([(1 - p_out, 1, _go(o + 1, b1, b2, EMPTY)),
                             (p_out, 0, _go(o + 2, b1, b2, EMPTY))])
            elif b2:  # tag from second
                p_out = p_defense_wins(_speed(b2, env), 0, env.outfield)
                opts.append([(1 - p_out, 0, _go(o + 1, b1, EMPTY, b2)),
                             (p_out, 0, _go(o + 2, b1, EMPTY, EMPTY))])

    elif event == "GB":
        if o == 2:
            opts.append([(1.0, 0, END)])
        elif b1:
            p_dp = p_defense_wins(bat_speed, 0, env.infield)
            dp = (p_dp, 0, END) if o == 1 else (p_dp, on(b3), _go(2, EMPTY, EMPTY, b2))
            fc = (1 - p_dp, on(b3), _go(o + 1, bat, EMPTY, b2))  # runner from 1st out, batter safe
            opts.append([dp, fc])
        else:
            opts.append([(1.0, on(b3), _go(o + 1, EMPTY, EMPTY, b2))])

    elif event == "BB":
        if b1 and b2 and b3:
            opts.append([(1.0, 1, _state(o, bat, b1, b2))])
        elif b1 and b2:
            opts.append([(1.0, 0, _state(o, bat, b1, b2))])
        elif b1:
            opts.append([(1.0, 0, _state(o, bat, b1, b3))])
        else:
            opts.append([(1.0, 0, _state(o, bat, b2, b3))])

    elif event in ("1B", "1B+"):
        runs = on(b3)
        opts.append([(1.0, runs, _state(o, bat, b1, b2))])
        if env.allow_extra_bases:
            if b2:   # runner who reached 3rd tries for home
                p_out = p_defense_wins(_speed(b2, env), env.bonus_home + two_out, env.outfield)
                opts.append([(1 - p_out, runs + 1, _state(o, bat, b1, EMPTY)),
                             (p_out, runs, _go(o + 1, bat, b1, EMPTY))])
            elif b1:  # runner who reached 2nd tries for 3rd
                p_out = p_defense_wins(_speed(b1, env), two_out, env.outfield)
                opts.append([(1 - p_out, runs, _state(o, bat, EMPTY, b1)),
                             (p_out, runs, _go(o + 1, bat, EMPTY, EMPTY))])
        if event == "1B+":
            opts = [[(p, r, _batter_takes_second(n)) for p, r, n in opt] for opt in opts]

    elif event == "2B":
        runs = on(b2) + on(b3)
        opts.append([(1.0, runs, _state(o, EMPTY, bat, b1))])
        if b1 and env.allow_extra_bases:  # runner from 1st (now on 3rd) tries for home
            p_out = p_defense_wins(_speed(b1, env), env.bonus_home + two_out, env.outfield)
            opts.append([(1 - p_out, runs + 1, _state(o, EMPTY, bat, EMPTY)),
                         (p_out, runs, _go(o + 1, EMPTY, bat, EMPTY))])

    elif event == "3B":
        opts.append([(1.0, on(b1) + on(b2) + on(b3), _state(o, EMPTY, EMPTY, bat))])

    elif event == "HR":
        opts.append([(1.0, on(b1) + on(b2) + on(b3) + 1, START + 27 * o)])

    else:
        raise ValueError(event)
    return opts


def _batter_takes_second(n: int) -> int:
    if n == END:
        return END
    o, b1, b2, b3 = _unpack(n)
    if b1 and not b2:
        return _state(o, EMPTY, b1, b3)
    return n


def steal_options(s: int, env: Env):
    """Before the pitch: each choice is a list of (prob, next_state). The first is 'no steal'."""
    opts = [[(1.0, s)]]
    if not env.allow_steals:
        return opts
    o, b1, b2, b3 = _unpack(s)
    if b1 and not b2:
        p_out = p_defense_wins(_speed(b1, env), 0, env.catcher_arm)
        opts.append([(1 - p_out, _state(o, EMPTY, b1, b3)), (p_out, _go(o + 1, EMPTY, EMPTY, b3))])
    if b2 and not b3:
        p_out = p_defense_wins(_speed(b2, env), -env.steal_third_penalty, env.catcher_arm)
        opts.append([(1 - p_out, _state(o, b1, EMPTY, b2)), (p_out, _go(o + 1, b1, EMPTY, EMPTY))])
    return opts


# ---------------------------------------------------------------------------------------------
# Solving
# ---------------------------------------------------------------------------------------------
@dataclass
class Solution:
    V: dict                  # state -> expected runs to end of inning, before any steal attempt
    W: dict                  # state -> expected runs once the pitch is about to be thrown
    visits: dict             # state -> expected plate appearances there per inning (from START)
    runs_per_9: float
    pa_per_inning: float
    choice: dict             # (state, event) -> index of chosen option
    steal: dict              # state -> index of chosen steal option (0 = no steal)


def _choice_value(opt, V):
    return sum(p * (r + (0.0 if n == END else V[n])) for p, r, n in opt)


def _steal_value(opt, W):
    return sum(p * (0.0 if n == END else W[n]) for p, n in opt)


def solve(env: Env, tol: float = 1e-12, max_iter: int = 10_000) -> Solution:
    probs = np.asarray(env.probs, dtype=float)
    if abs(probs.sum() - 1) > 1e-9:
        raise ValueError(f"probabilities sum to {probs.sum()}")
    S = states(env.tag_speed is not None)
    table = {(s, e): outcomes(s, e, env) for s in S for e in EVENTS if probs[E[e]] > 0}
    steals = {s: steal_options(s, env) for s in S}

    V = dict.fromkeys(S, 0.0)
    for _ in range(max_iter):
        W = dict.fromkeys(S, 0.0)
        for (s, e), opts in table.items():
            W[s] += probs[E[e]] * max(_choice_value(o, V) for o in opts)
        new = {s: max(_steal_value(o, W) for o in steals[s]) for s in S}
        diff = max(abs(new[s] - V[s]) for s in S)
        V = new
        if diff < tol:
            break
    else:
        raise RuntimeError("did not converge")
    W = dict.fromkeys(S, 0.0)
    for (s, e), opts in table.items():
        W[s] += probs[E[e]] * max(_choice_value(o, V) for o in opts)

    # Expected visits: pre-pitch states -> (steal) -> pitch states -> (plate appearance) -> ...
    idx = {s: i for i, s in enumerate(S)}
    n = len(S)
    A, B = np.zeros((n, n)), np.zeros((n, n))
    choice, steal = {}, {}
    for s in S:
        k = int(np.argmax([_steal_value(o, W) for o in steals[s]]))
        steal[s] = k
        for p, nx in steals[s][k]:
            if nx != END:
                A[idx[s], idx[nx]] += p
    for (s, e), opts in table.items():
        k = int(np.argmax([_choice_value(o, V) for o in opts]))
        choice[(s, e)] = k
        for p, _, nx in opts[k]:
            if nx != END:
                B[idx[s], idx[nx]] += probs[E[e]] * p
    start = np.zeros(n)
    start[idx[START]] = 1.0
    pre = np.linalg.solve((np.eye(n) - A @ B).T, start)
    at_bat = pre @ A
    visits = {s: float(at_bat[idx[s]]) for s in S}
    return Solution(V=V, W=W, visits=visits, runs_per_9=9 * V[START],
                    pa_per_inning=float(at_bat.sum()), choice=choice, steal=steal)


def event_run_values(env: Env, sol: Solution, batter_speed: float | None = None) -> np.ndarray:
    """Linear weights: average runs each result is worth in this environment.

    For each result, average over the situations batters actually bat in of
    (runs scored + run expectancy after) - run expectancy as the pitch is thrown.

    Pass batter_speed to value a batter of that Speed: he's followed as the tagged runner, so
    his Speed counts for double plays, steals and extra bases for as long as he's on base.
    """
    V, batter = sol.V, AVG
    if batter_speed is not None:
        V = solve(replace(env, tag_speed=float(batter_speed))).V
        batter = TAG
    total = sum(sol.visits.values())
    rv = np.zeros(len(EVENTS))
    for i, e in enumerate(EVENTS):
        acc = 0.0
        for s in NORMAL_STATES:
            w = sol.visits.get(s, 0.0) / total
            if w == 0:
                continue
            best = max(_choice_value(o, V) for o in outcomes(s, e, env, batter))
            acc += w * (best - sol.W[s])
        rv[i] = acc
    return rv


def running_run_values(env: Env, sol: Solution) -> dict:
    """Run value of plays that aren't chart results, averaged over the situations they happen in.

      SB / CS    a steal of 2nd from a normal steal situation (runner on 1st, 2nd open):
                 runs gained if safe, lost if caught.
      DP         how much worse a double play is than the force out alone (runner on 1st, < 2 outs).
    """
    total_w = {"SB": 0.0, "CS": 0.0, "DP": 0.0}
    acc = {"SB": 0.0, "CS": 0.0, "DP": 0.0}
    for s in NORMAL_STATES:
        w = sol.visits.get(s, 0.0)
        if not w:
            continue
        o, b1, b2, b3 = _unpack(s)
        if b1 and not b2:
            safe = _state(o, EMPTY, b1, b3)
            out = _go(o + 1, EMPTY, EMPTY, b3)
            acc["SB"] += w * (sol.W[safe] - sol.W[s]); total_w["SB"] += w
            acc["CS"] += w * ((0.0 if out == END else sol.W[out]) - sol.W[s]); total_w["CS"] += w
        if b1 and o < 2:
            fc_runs, fc_next = int(b3 != EMPTY), _go(o + 1, AVG, EMPTY, b2)
            dp_runs, dp_next = (0, END) if o == 1 else (int(b3 != EMPTY), _go(2, EMPTY, EMPTY, b2))
            fc = fc_runs + (0.0 if fc_next == END else sol.V[fc_next])
            dp = dp_runs + (0.0 if dp_next == END else sol.V[dp_next])
            acc["DP"] += w * (dp - fc); total_w["DP"] += w
    return {k: acc[k] / total_w[k] if total_w[k] else 0.0 for k in acc}


def steal_rate(env: Env, sol: Solution, speed: float) -> dict:
    """How often a runner of this Speed steals: attempts and successes per time he's on 1st/2nd."""
    tagged = solve(replace(env, tag_speed=float(speed), allow_steals=True))
    out = {}
    for base, label in ((1, "2nd"), (2, "3rd")):
        w = att = safe = 0.0
        for s in NORMAL_STATES:
            o, b1, b2, b3 = _unpack(s)
            bases = [b1, b2, b3]
            if not bases[base - 1] or (bases[base] if base < 3 else 1):
                continue
            bases[base - 1] = TAG
            t = _state(o, *bases)
            weight = sol.visits.get(s, 0.0)
            w += weight
            k = tagged.steal[t]
            if k:
                att += weight
                safe += weight * tagged_steal_safe(t, k, replace(env, tag_speed=float(speed), allow_steals=True))
        out[label] = {"attempt": att / w if w else 0.0, "success": safe / att if att else 0.0}
    return out


def tagged_steal_safe(s: int, k: int, env: Env) -> float:
    return steal_options(s, env)[k][0][0]
