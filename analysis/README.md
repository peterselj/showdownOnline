# Showdown card analysis

Which MLB Showdown cards give the most for their points? This folder holds the math to answer
that, separate from the tabletop app in the rest of the repo.

## What's here

| Path | What it does |
|---|---|
| `showdown/cards.py` | Loads the original 2000 Wizards of the Coast set (612 cards) from two fan datasets and cross-checks them card by card. |
| `showdown/sbcards.py` | Loads Showdown Bot's 2004/2005 cards (what the tabletop app builds) for one MLB season into the same format. |
| `showdown/engine.py` | The game engine. Treats a half-inning as a Markov chain over the 24 base/out states and solves it exactly, so there's no dice noise. Base-running choices are made optimally. |
| `showdown/value.py` | Turns cards into runs. Batters: runs added per game vs an average hitter (linear weights). Pitchers: runs saved per 9 innings. Plus "surplus": runs above what a typical card at the same points produces. |
| `scripts/value_report.py` | Values every card in each pool, prints bargains/overpays, saves full tables to `results/`. |
| `tests/` | Includes an independent dice simulator that must agree with the exact engine. |
| `docs/showdown2000fun-notes.md` | How showdown2000.fun differs from the 2000 rules (caps, rosters, fatigue, base running). |

## Run it

```bash
cd analysis
pip install -r requirements.txt
python scripts/fetch_data.py         # 2000 set (pinned versions)
python scripts/fetch_showdownbot.py  # Showdown Bot 2004/2005 cards, 2025 + 2026 seasons
python -m showdown.cards             # builds + cross-checks the 2000 set
python -m pytest -q
python scripts/value_report.py       # ~2.5 minutes
```

## Status

- 2000 set: points track value closely (correlation 0.95); the bargains are On-Base 9-10
  hitters with few out faces at mid prices.
- Showdown Bot 2004/2005 cards (what this app uses): points track chart value just as closely.
  The league is every card with real playing time that season (≥ 250 PA or ≥ 30 IP, ~720 cards).
- Not valued yet: individual fielding, stolen bases, icons. That makes glove-first and very
  fast hitters look overpriced. See HANDOFF.md for the full list.

### Season check (Showdown Bot)

The same numbers a season apart, to see whether the conclusions hold:

| Pool | League runs / 9 | Hitters r | Runs / game per 100 pts | +1 On-Base (runs/game) | +1 Control (runs / 9) |
|---|---|---|---|---|---|
| 2004 set, 2025 season | 4.39 | 0.95 | 0.090 | +0.103 | +0.88 |
| 2004 set, 2026 season | 4.20 | 0.95 | 0.086 | +0.096 | +0.83 |
| 2005 set, 2025 season | 4.46 | 0.96 | 0.093 | +0.102 | +0.87 |
| 2005 set, 2026 season | 4.22 | 0.96 | 0.085 | +0.096 | +0.83 |

Each season's players differ, so the bargain names change. The patterns don't: the price of
a run, and what each attribute is worth, move by under 10% between seasons and sets.

Next: value fielding and steals, then use these values to find the best 20-player /
5,000-point roster. showdown2000.fun usage and win-rate stats need its owners' game data.

## Data sources

- [birdman093/showdown](https://github.com/birdman093/showdown): 2000 set as die ranges, plus positions and fielding.
- [digitgopher/showdown-app](https://github.com/digitgopher/showdown-app) (GPL-2.0): 2000 set as slot counts.

Both agree on points, On-Base/Control, Speed and IP for all 612 cards. Six charts differ; in
each case the birdman chart doesn't cover exactly 20 faces, so the digitgopher chart is used.

- [Showdown Bot](https://www.showdownbot.com) ([source](https://github.com/mgula57/mlb_showdown_card_bot),
  public domain): its card database holds a pre-built card for every player-season. We read it
  through the same public search endpoint its "Cards" page uses, one request per set and season.
  It's a live database, so each saved file records the Showdown Bot version and download date
  (2025 cards were v4.0, 2026 cards v4.4 when downloaded on 2026-11-07).
