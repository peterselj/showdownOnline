# Showdown card analysis

Which MLB Showdown cards give the most for their points? This folder holds the math to answer
that, separate from the tabletop app in the rest of the repo.

The main result is for **showdown2000.fun**, valued from real games played there:
[card explorer](https://claude.ai/artifact/EfvbFLfN1pzo8ZsrhbqawU) (private until shared).
The same engine also values the original 2000 set and Showdown Bot's 2004/05 cards from their charts.

## What's here

| Path | What it does |
|---|---|
| `showdown/engine.py` | The game engine. Treats a half-inning as a Markov chain over the base/out states and solves it exactly, so there's no dice noise. Steals, extra bases and double plays use runner Speed vs catcher arm / outfield / infield, with the best choice made for the offense. One "tagged" runner can have his own Speed, so a batter's Speed counts for as long as he's on base. |
| `showdown/sd2000.py` | showdown2000.fun: loads its cards with their pooled game stats, builds a league from those games, and turns results into runs (batting, running, pitching), plus a modeled glove and a catcher-arm curve. |
| `scripts/build_sd2000.py` | Values every showdown2000.fun card and builds the explorer page (`explorer/sd2000.html` -> `results/showdown2000-explorer.html`). Prints the headline findings. |
| `showdown/cards.py` | Loads the original 2000 Wizards of the Coast set (612 cards) from two fan datasets and cross-checks them card by card. |
| `showdown/sbcards.py` | Loads Showdown Bot's 2004/2005 cards (what the tabletop app builds) for one MLB season into the same format. |
| `showdown/value.py` | Chart-based valuation (2000 set, Showdown Bot): runs added per game vs an average hitter, runs saved per 9, and "surplus" vs a typical card at the same points. |
| `scripts/value_report.py`, `scripts/build_explorer.py` | Chart-based report and card grid for the 2000 set and Showdown Bot cards. |
| `tests/` | Includes independent dice simulators (with and without steals) that must agree with the exact engine. |
| `docs/showdown2000fun-notes.md` | How showdown2000.fun differs from the 2000 rules (caps, rosters, fatigue, base running). |

## Run it

```bash
cd analysis
pip install -r requirements.txt
python -m pytest -q
python scripts/build_sd2000.py       # showdown2000.fun results + page (~1 minute); needs the data below
python scripts/fetch_data.py         # 2000 set (pinned versions)
python scripts/fetch_showdownbot.py  # Showdown Bot 2004/2005 cards, 2025 + 2026 seasons
python scripts/value_report.py       # chart-based values (~2.5 minutes)
python scripts/build_explorer.py     # chart-based card grid -> results/card-explorer.html
```

## showdown2000.fun: what the games say

Read on 2026-11-07: 1,134 hitter cards and 831 pitcher cards with real playing time, from
1,261 teams (48 farm/test teams left out). A card's line is pooled from every team that used it
for at least 80 at-bats or 23 innings, and only cards with 150+ plate appearances (or batters
faced) are kept. Small samples are pulled toward average.

- **Prices are mostly fair.** Points vs value from real games: correlation 0.83 for hitters
  (500+ PA), 0.74 for starters, 0.64 for relievers. Pitcher prices are the looser ones.
- **Very fast runners are the clearest hitter bargain.** Speed 24+ cards beat their price by
  about +0.12 runs a game and steal about 0.9 bases a game. In this league a steal is worth
  +0.18 runs and caught stealing −0.48, so stealing pays only at about 72%+ success.
- **Catcher arm: below +8 hurts, above +10 barely helps.** Runners pick their spots against
  weak arms (this reproduces the real steal numbers by Speed). Compared with the average +10
  arm, a +5 arm gives up 0.09 runs a game, a +3 arm 0.28, while +12 saves only 0.01.
  Weak-armed catchers average −0.13 vs price; +12s are fairly priced.
- **The most-used cards are cheap filler.** Austin Hedges 2025 (C+12, 80 pts) is on 81
  teams; Patrick Bailey, Luis Torrens (+12 catchers) and 40-point Josh Rojas follow, and
  40-point starter Jordan Montgomery is on 85 teams. Their bats are well below average; teams
  use them to free points for stars while still stopping the running game.
- **Double plays are a small effect.** They happen on 2.3% of plate appearances and cost 0.55
  runs beyond the out. A +0 shortstop gives up about 0.16 runs a game to a +3 one: real, but
  small next to the bat. (Glove values are modeled; the Leaders tables have no fielding stats.)
- **Control 5–6 relievers are bargains** (+0.30 runs per 9 vs price; Control 4 or less −0.56).

`python scripts/build_sd2000.py` recomputes these lines from the data and puts them on the page.

### How the showdown2000.fun data was collected

showdown2000.fun's cards and stats are only visible inside its app after signing in, and its
card charts appear only on card images. With the owner's account signed in, the app's own
screens were read in the browser: **Leaders** (every card on every team: G, AB, H, ... SB, CS,
DP; pitching IP, H, BB, SO, HR, ER) and **My Collection → All Cards** (all 5,949 cards: points,
On-Base/Control, Speed, IP, positions with fielding). Rows were pooled per card in the page and
saved to `data/raw/` (git-ignored; do not commit):

- `sd2000_hitters.psv`, `sd2000_pitchers.psv`: one row per card, catalog attributes + pooled stats
- `sd2000_meta.json`: date, cutoffs, team counts, and which teams were left out and why

The farm/test filter is crude: a few real teams with "farm" or "test" in the name are caught too.

## Chart-based results (2000 set, Showdown Bot 2004/05)

- 2000 set: points track value closely (correlation 0.95); the bargains are On-Base 9-10
  hitters with few out faces at mid prices.
- Showdown Bot 2004/2005 cards: points track chart value just as closely, and the price of a run
  and the worth of each attribute move by under 10% between seasons and sets:

| Pool | League runs / 9 | Hitters r | Runs / game per 100 pts | +1 On-Base (runs/game) | +1 Control (runs / 9) |
|---|---|---|---|---|---|
| 2004 set, 2025 season | 4.39 | 0.95 | 0.090 | +0.103 | +0.88 |
| 2004 set, 2026 season | 4.20 | 0.95 | 0.086 | +0.096 | +0.83 |
| 2005 set, 2025 season | 4.46 | 0.96 | 0.093 | +0.102 | +0.87 |
| 2005 set, 2026 season | 4.22 | 0.96 | 0.085 | +0.096 | +0.83 |

These chart-based values don't include each player's own glove or steals.

## Data sources

- showdown2000.fun (see above); rules from the site's public patch notes and in-app rules.
- [birdman093/showdown](https://github.com/birdman093/showdown): 2000 set as die ranges, plus positions and fielding.
- [digitgopher/showdown-app](https://github.com/digitgopher/showdown-app) (GPL-2.0): 2000 set as slot counts.
  Both agree on points, On-Base/Control, Speed and IP for all 612 cards; six charts differ, and
  in each case the digitgopher chart (the one covering exactly 20 faces) is used.
- [Showdown Bot](https://www.showdownbot.com) ([source](https://github.com/mgula57/mlb_showdown_card_bot),
  public domain): its public card-search endpoint, one request per set and season
  (2025 cards v4.0, 2026 cards v4.4, downloaded 2026-11-07).
