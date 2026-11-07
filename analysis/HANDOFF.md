# Handoff: where the card analysis stands

For a new Claude session picking this up. Explain things in plain language: the owner is a
novice developer and data analyst; their cofounder is a staff-level engineer.

## Goal
A data deep dive on which cards perform best:
- (A) value per point from card mechanics (On-Base/Control, chart outs, points);
- (B) real usage and win rates across all players, like marvelsnapzone.com. Example: Alex Call's OBP
  pooled across every copy of the card, and how often the card is used. showdown2000.fun only shows stats per roster.

## Done (see README.md in this folder)
- `showdown/cards.py`: original 2000 WotC set (612 cards) from two fan datasets, cross-checked. They agree
  on points/OB/control/speed/IP; the 6 charts that differ are fixed using the source whose chart covers 20 faces.
- `showdown/engine.py`: exact Markov-chain half-inning solver with optimal base running. Tests include an
  independent dice simulator that agrees with it.
- `showdown/value.py`: batter runs added per game (linear weights), pitcher runs saved per 9, surplus vs points.
  Handles any numeric Speed (2004/05 cards print 8-25, not A/B/C).
- `showdown/sbcards.py` + `scripts/fetch_showdownbot.py`: Showdown Bot cards (the app's own cards, 2004 and 2005
  designs) for whole MLB seasons, from Showdown Bot's public card-search endpoint (the one its Cards page uses;
  Showdown Bot is public domain on GitHub: mgula57/mlb_showdown_card_bot). League = cards with >= 250 PA or
  >= 30 IP (Showdown Bot's own small-sample flag): ~720 cards per season. Every chart covers faces 1-20 exactly once.
- `scripts/value_report.py`: values every pool, prints bargains/overpays, writes `results/*.csv` (gitignored).
- `docs/showdown2000fun-notes.md`: showdown2000.fun's rule differences, from the patch notes in its public JS.
  It uses its own custom cards (e.g. Jace Jung), not the 2000 set.

## Results so far
- 2000 set: points track value closely (r = 0.95); bargains are On-Base 9-10 hitters with few out faces at mid
  prices (Hammonds, Edgar Martinez, Olerud).
- Showdown Bot 2004 and 2005, 2026 season: points track value just as closely (hitters r = 0.95-0.96, starters
  0.97-0.98, relievers 0.91-0.93). Showdown Bot's point formula is well calibrated for chart value.
  - +1 On-Base is worth ~0.10 runs/game; +1 Control ~0.83 runs per 9; 1B -> HR face ~0.07 runs/game.
  - Starters: the straight-line fit makes the very top (Yamamoto 610-630 pts) look like bargains; pitcher value
    rises faster than linearly with points, so treat top-end starter "surplus" with care.
  - Glove-first and speed-first hitters look overpriced (Arraez 2B+4, Nicky Lopez, Chandler Simpson Speed 23)
    because the engine doesn't value individual fielding or stolen bases yet; Showdown Bot's points do.
- 2025 season check (README "Season check"): same picture. Hitters r 0.95-0.96; runs per 100 points and the
  +1 On-Base / +1 Control values move under 10% between seasons and sets.

## Known gaps in the model (biggest first)
1. Individual fielding isn't valued (only the league-average defense is used). Showdown Bot prices it.
2. Stolen bases aren't modelled (for any set), so Speed is undervalued: the engine only credits it for
   beating double plays and taking extra bases.
3. Icons (R, G, K, HR, SB, RP, S, V, CY, 20) and strategy cards are ignored.
4. Surplus is a straight line of value vs points; a curve would suit pitchers better.
5. Showdown Bot's own simulator docks runners 5 Speed going to 3rd; our engine follows the 2000 rule (no penalty),
   which showdown2000.fun also uses.

## Blockers and decisions
- showdown2000.fun's cards and games come from a socket.io server at supermega.app/showdown2000. A direct
  test request got no reply; faking the site's Origin header was blocked as getting around an access control,
  and we agreed NOT to keep trying. Usage and win-rate data must come from the owners
  (Discord https://discord.gg/qjVfgyuass). A message asking for an anonymized game export and the card list
  has been drafted.

## Possible next steps
1. Value individual fielding and stolen bases (gaps 1-2), then re-run: this changes which hitters look like bargains.
2. Best 20-player / 5,000-point roster from a season's cards (an optimizer on top of these values).
3. Build the aggregation and meta-page pipeline so it's ready when showdown2000.fun's owners share data.
4. Open a PR from `claude/sharp-bardeen-a1efym` to `main`.
5. Turn the results into a readable report or charts.
