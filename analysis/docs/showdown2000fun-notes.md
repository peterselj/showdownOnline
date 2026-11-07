# What showdown2000.fun looks like under the hood

Read from the site's public JavaScript bundle (`/static/js/main.*.js`) on 2026-11-07.
Nothing here required logging in.

## Architecture
- React single-page app; card images served from `img.showdown2000.fun`.
- Cards, games and stats come from a socket.io server at `https://supermega.app/showdown2000`
  (not in the page code). Most calls send `{userId, token}`, so they expect a signed-in user.
- Relevant socket events: `searchCards`, `getCardFilterOptions`, `getLeaders`, `getStandings`,
  `getPublicGames`, `getAllCompletedGames`, `getGameDetails`, `getCompleteTeams`.
- Contact: Discord https://discord.gg/qjVfgyuass, X https://x.com/showdown2000fun

## Cards are custom, not the 2000 WotC set
- Modern and legend players (e.g. Jace Jung, Mike Trout, Roberto Clemente), sold in packs:
  Juiced, Legends, ThatDudeRocked, World Series; parallels (Lumber, Refractor, Holofoil, Golden).
- Fields: `command` (On-Base for hitters, Control for pitchers), `speed`, `ip`, `points`,
  `positions_defense`, chart with results incl. `20+`. Card-filter sliders suggest On-Base ranges
  wider than 2000's 4-10 (defaults hint at up to ~13).
- Point scale differs from 2000: patch notes call one reliever's fair value "~1,000 pts".

## Rules that differ from (or pin down) the 2000 rulebook
- Salary caps: Tiny 2000, Small 3000, Mid 4000, Standard 5000, Plus 6000, Large (higher).
- Roster 25-27: lineup, bench (bench players cost 20% of points), rotation, 6-8 bullpen.
- Extra bases: +5 speed going home (sends and tag-ups); +5 with 2 outs on 1B/2B (not tag-ups);
  bonuses stack. No -5 penalty for going to 3rd. (Our engine already uses exactly this.)
- 1B+: batter takes 2nd automatically even if a runner was sent to 3rd.
- Stolen bases exist (catcher arm penalty when stealing 3rd).
- Extra innings: runner starts on 2nd from the 10th.
- Starters can't be pulled before the 4th unless fatigued (by innings or runs allowed);
  starters lose 1 Control per inning past IP.
- Reliever fatigue: 1st tired inning halves Control, 2nd -> 0, then -1 per inning; multi-day
  recovery tiers; relievers can use a 2x IP bank on first appearance after full rest.
- Off-bench defense: a player out of position gets -2 fielding.

## In-app stats that already exist (useful for "which cards win")
- Per-card batting and pitching stats (All / Tournament / Exhibition), leaderboards,
  team ELO-style ratings, roll stats, head-to-head. The owners clearly have the game logs.
