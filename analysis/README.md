# Showdown card analysis

Which MLB Showdown cards give the most for their points? This folder holds the math to answer
that, separate from the tabletop app in the rest of the repo.

## What's here

| Path | What it does |
|---|---|
| `showdown/cards.py` | Loads the original 2000 Wizards of the Coast set (612 cards) from two fan datasets and cross-checks them card by card. |
| `showdown/engine.py` | The game engine. Treats a half-inning as a Markov chain over the 24 base/out states and solves it exactly, so there's no dice noise. Base-running choices are made optimally. |
| `showdown/value.py` | Turns cards into runs. Batters: runs added per game vs an average hitter (linear weights). Pitchers: runs saved per 9 innings. Plus "surplus": runs above what a typical card at the same points produces. |
| `tests/` | Includes an independent dice simulator that must agree with the exact engine. |
| `docs/showdown2000fun-notes.md` | How showdown2000.fun differs from the 2000 rules (caps, rosters, fatigue, base running). |

## Run it

```bash
cd analysis
pip install -r requirements.txt
python scripts/fetch_data.py      # downloads the card data (pinned versions)
python -m showdown.cards          # builds + cross-checks the card set
python -m pytest -q
```

## Status

- Done: the card data pipeline, the engine and the valuation for the 2000 set. Points track
  value closely (correlation 0.95); the bargains are On-Base 9-10 hitters with few out faces
  at mid prices.
- Next: run the same engine on Showdown Bot cards (what this app uses) and on showdown2000.fun's
  cards if the owners share them; usage and win-rate stats need their game data.

## Data sources

- [birdman093/showdown](https://github.com/birdman093/showdown): 2000 set as die ranges, plus positions and fielding.
- [digitgopher/showdown-app](https://github.com/digitgopher/showdown-app) (GPL-2.0): 2000 set as slot counts.

Both agree on points, On-Base/Control, Speed and IP for all 612 cards. Six charts differ; in
each case the birdman chart doesn't cover exactly 20 faces, so the digitgopher chart is used.
