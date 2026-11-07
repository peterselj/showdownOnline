import numpy as np
import pandas as pd
import pytest

from showdown.cards import EVENTS
from showdown.sbcards import chart_counts, range_to_faces
from showdown.value import build_league, value_batters


def test_ranges():
    assert range_to_faces("1–10") == list(range(1, 11))   # en dash, as Showdown Bot prints it
    assert range_to_faces("3") == [3]
    assert range_to_faces("19+") == [19, 20]
    assert range_to_faces("23+") == []                         # only reachable with roll bonuses
    assert range_to_faces("16–22") == [16, 17, 18, 19, 20]
    assert range_to_faces("—") == []                      # em dash = not on this chart


def test_chart_counts_real_card():
    # Aaron Judge, 2005 set, 2025 season
    judge = {"SO": "1–2", "GB": "3", "FB": "4–6", "BB": "7–12", "1B": "13–16",
             "1B+": "—", "2B": "17–18", "3B": "—", "HR": "19+"}
    c = chart_counts(judge)
    assert sum(c.values()) == 20
    assert (c["SO"], c["GB"], c["FB"], c["BB"], c["1B"], c["2B"], c["HR"]) == (2, 1, 3, 6, 4, 2, 2)


def test_chart_counts_rejects_bad_charts():
    with pytest.raises(ValueError, match="no result"):
        chart_counts({"SO": "1–5", "HR": "7+"})
    with pytest.raises(ValueError, match="both"):
        chart_counts({"SO": "1–10", "HR": "10+"})


def _toy_cards(speeds):
    """Identical hitters except for Speed, facing one average pitcher."""
    rows = []
    for i, s in enumerate(speeds):
        chart = dict(zip(EVENTS, [0, 3, 5, 3, 3, 4, 0, 1, 0, 1]))
        rows.append({"name": f"h{i}", "points": 200, "is_pitcher": False, "onbase": 9, "speed": s,
                     "primary_pos": "SS", "primary_fielding": 2, **{f"c_{e}": chart[e] for e in EVENTS}})
    pchart = dict(zip(EVENTS, [2, 5, 6, 4, 1, 1, 0, 1, 0, 0]))
    rows.append({"name": "p", "points": 300, "is_pitcher": True, "control": 3, "ip": 6,
                 **{f"c_{e}": pchart[e] for e in EVENTS}})
    return pd.DataFrame(rows)


def test_numeric_speeds_value_faster_runners_higher():
    # 2004/05 speeds are any number, not just the 2000 letters (10/15/20).
    lg = build_league(_toy_cards([8, 13, 17, 23]))
    raa = value_batters(lg)["raa_per_game"].to_numpy()
    assert np.all(np.diff(raa) > 0)          # same chart, faster runner -> fewer double plays
