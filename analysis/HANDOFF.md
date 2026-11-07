# Handoff: where the card analysis stands

For a new Claude session picking this up. Explain things in plain language: the owner is a
novice developer and data analyst; their cofounder is a staff-level engineer.

## Goal
A data deep dive on which showdown2000.fun cards perform best:
- (A) value per point from card mechanics (On-Base/Control, chart outs, points);
- (B) real usage and win rates across all players, like marvelsnapzone.com. Example: Alex Call's OBP
  pooled across every copy of the card, and how often the card is used. The site only shows stats per roster.

## Done (see README.md in this folder)
- `showdown/cards.py`: original 2000 WotC set (612 cards) from two fan datasets, cross-checked. They agree
  on points/OB/control/speed/IP; the 6 charts that differ are fixed using the source whose chart covers 20 faces.
- `showdown/engine.py`: exact Markov-chain half-inning solver with optimal base running. Tests include an
  independent dice simulator that agrees with it.
- `showdown/value.py`: batter runs added per game (linear weights), pitcher runs saved per 9, surplus vs points.
  Early result: points track value closely (r = 0.95); bargains are On-Base 9-10 hitters with few out faces at
  mid prices (Edgar Martinez, Jeffrey Hammonds, Olerud).
- `docs/showdown2000fun-notes.md`: showdown2000.fun's rule differences, from the patch notes in its public JS.
  It uses its own custom cards (e.g. Jace Jung), not the 2000 set.

## Blockers and decisions
- showdown2000.fun's cards and games come from a socket.io server at supermega.app/showdown2000. A direct
  test request got no reply; faking the site's Origin header was blocked as getting around an access control,
  and we agreed NOT to keep trying. Usage and win-rate data must come from the owners
  (Discord https://discord.gg/qjVfgyuass). A message asking for an anonymized game export and the card list
  has been drafted.
- The tabletop app in this repo builds cards with Showdown Bot (2004/2005 design, via `worker/`). Valuing those
  cards needs a format check first: 2004/05 charts differ from 2000 (20+ results, different pitcher charts).

## Possible next steps
1. Value Showdown Bot cards (the app's own cards) per point under the 20-player / 5,000-point rules.
2. Build the aggregation and meta-page pipeline so it's ready when the owners share data.
3. Open a PR from `claude/sharp-bardeen-a1efym` to `main`.
4. Turn the 2000-set results into a readable report or charts.
