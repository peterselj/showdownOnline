# Handoff: where the card analysis stands

For a new Claude session picking this up. Explain things in plain language: the owner is a
novice developer and data analyst who plays on showdown2000.fun; their cofounder is a
staff-level engineer.

## Goal
Which showdown2000.fun cards perform best, from real games (usage and results pooled across all
players, like marvelsnapzone.com), plus why (Speed, catcher arm, glove, points).

## Done
- **showdown2000.fun results** (`showdown/sd2000.py`, `scripts/build_sd2000.py`, `explorer/sd2000.html`):
  1,134 hitters + 831 pitchers valued from real games across 1,261 teams; published explorer
  https://claude.ai/artifact/EfvbFLfN1pzo8ZsrhbqawU. Findings are in README.md.
- **Engine** (`showdown/engine.py`): exact Markov solver with steals (catcher arm vs Speed, 3rd +5
  harder), extra bases (+5 home, +5 with 2 outs), double plays, optimal offense choices, and a
  "tagged" runner so one batter's Speed follows him around the bases. Dice-simulator tests agree.
- **Run values from real games**: the league is built from the pooled showdown2000.fun totals; a
  card's value = its real results x those run values, shrunk toward average (200 PA / 250 BF).
- **Glove**: infield/outfield points priced by what one point of team fielding saves; catcher arm
  priced per arm (`catcher_arm_table`) because it's very non-linear: steals only happen against
  weak arms. Checked: runners stealing only when ~65%+ safe against the real catcher mix reproduces
  the real attempt and success rates by Speed.
- Chart-based valuation of the 2000 set and Showdown Bot 2004/05 cards (`value.py`, `value_report.py`).

## Data (git-ignored, never commit)
`data/raw/sd2000_hitters.psv`, `sd2000_pitchers.psv`, `sd2000_meta.json`, read on 2026-11-07
through the app while the owner was signed in (Leaders + My Collection > All Cards). The browser
pane blocks downloads and localhost, so data was pooled in-page and copied out in chunks; totals
were checked against the page. Refreshing it needs the owner to sign in again in the browser pane.

## Known gaps
1. Glove values are modeled (the Leaders tables have no fielding stats).
2. No win rates: Leaders has player stats, not game outcomes by card.
3. Cutoffs: teams with < 80 AB / < 23 IP with a card are left out, so usage = "regular use".
4. The farm/test team filter is crude (48 teams; a few real ones caught by name).
5. Pitching value uses H/BB/SO/HR allowed only; no park/defense adjustment.
6. Shrinkage is a fixed 200 PA / 250 BF, not fitted.

## Possible next steps
1. Best 5,000-point roster optimizer using these values (positions, bench at 20% cost).
2. Refresh the data periodically (needs sign-in) and show trends.
3. Ask the owners (Discord https://discord.gg/qjVfgyuass) for game outcomes to add win rates.
4. Open a PR from `claude/sharp-bardeen-a1efym` to `main`.
