# MLB Showdown — shared virtual tabletop

A static web page where two people (e.g. Toronto + New York) see the same live
MLB Showdown table: batting lineups, bench, bullpen, bases, mound, a d20 with
animation, and outs/runs/inning counters. "Dumb tabletop" style — you apply
the game rules, the page keeps the shared state.

Player cards are generated from [Showdown Bot](https://www.showdownbot.com)
in the 2004/2005 design (through our [card server](#card-server)): type a name +
season year and the card is built into your library.

## Setup (one time, ~5 minutes)

The page is static, so realtime sync uses Firebase's free tier:

1. Go to <https://console.firebase.google.com> → **Add project** (name it anything, e.g. `showdown-bros`; Analytics off is fine).
2. **Build → Realtime Database → Create Database** → pick a US region → start in **test mode**.
3. **Project settings (gear) → Your apps → Web (`</>`)** → register the app (no hosting needed).
4. Copy the `firebaseConfig` object it shows into [`js/config.js`](js/config.js), replacing the placeholder. Make sure it includes `databaseURL` (shown on the Realtime Database page, like `https://showdown-bros-default-rtdb.firebaseio.com`).
5. Commit + push; GitHub Pages serves the rest.

Without Firebase config the app runs in **local mode** (syncs between two tabs
on the same machine only — handy for testing).

6. **Realtime Database → Rules** → replace the test-mode rules with the contents
   of [`database.rules.json`](database.rules.json) → **Publish**. Test-mode rules
   expire 30 days after you create the database and everything stops syncing, so
   do this before then.

### Security model

The game has no login, so **the room code is the password**. The rules in
[`database.rules.json`](database.rules.json) accept reads and writes only under
`/rooms/<code>`, any length. That means:

- Nobody can read or write the database root, so rooms can't be listed — a code
  has to be guessed exactly.
- Every field is shape- and size-checked (runs ≤ 200, outs ≤ 3, a d20 roll is
  1–20, names ≤ 20 chars, image URLs ≤ 500 chars), so the database can't be
  turned into someone's free file host.
- Anyone who has your code can change your game, and short codes like `BROS` are
  guessable by brute force. Deliberate trade-off for a two-person game — if it
  ever matters, use a longer code.

### Card server

Showdown Bot's API can't be called straight from a browser, and it deletes the
card images it generates after a few minutes. So cards are built through a
small Cloudflare Worker in [`worker/`](worker/) (free tier, deployed at
`https://showdown.mlbshowdown.workers.dev`; `window.CARD_SERVER` in
[`js/config.js`](js/config.js) points at it). It:

- calls Showdown Bot on the page's behalf, with retries;
- stores a shrunken (~100 KB) copy of every card image permanently and serves it
  at `/img/<card>`;
- caches every finished card, so a card built once comes back instantly for
  either player;
- only accepts requests from `https://peterselj.github.io` and localhost, and
  only stores images for cards it built itself (signed tokens).

To change it: edit `worker/src/index.js`, then `cd worker && npx wrangler deploy`
(signed in to the Cloudflare account that owns `mlbshowdown.workers.dev`). To
test locally, run `npx wrangler dev` in `worker/` and open the page with
`?cardserver=http://127.0.0.1:8787`.

## Building rosters

The **Rosters** tab is your personal deck-building area:

- **Card library:** type a name + season year (e.g. `Pedro Martinez` / `1999`) and
  press **Build**. The card is built on Showdown Bot (~10s, instant if already built) and
  saved in your library, so you only build each card once. Builds queue up and
  run in the background.
- **Rosters:** up to 5 saved rosters. Drag cards (or press **+**) into the batting
  order, bench, rotation, and bullpen; pick each hitter's position.
- **Roster check:** the live checklist enforces the team rules: exactly 20
  players, all 9 positions covered, 4–5 starting pitchers, no player twice. The
  budget bar tracks points against 5,000 (bench players count at full value);
  going over or under, and out-of-position players, are warnings only. The rules live in `RULES` in
  [`js/store.js`](js/store.js) if you play house rules.

Library and rosters are saved in **this browser only** (localStorage). Clearing
site data or switching computers starts you fresh.

## Running locally

Don't open `index.html` by double-clicking it: a page opened as a file can't
build cards (the card server only accepts the live site and `localhost`).
Instead, on Windows double-click **`serve.bat`**, which serves the folder at
<http://localhost:8000> and opens it. Anywhere else:

```bash
python -m http.server 8000
```

then open <http://localhost:8000>.

## Playing

1. Both visit the page, enter the **same room code** (e.g. `LINDOR`), pick a
   roster to bring, and one joins as HOME, the other as AWAY. Your roster is dealt
   onto the table: lineup #1–9 with positions, bench, rotation, bullpen.
   **Load roster** swaps in a different one mid-session; **+ Add player** still
   works for one-off additions.
2. Drag cards to adjust between games: lineup slots #1–9, bench, rotation, bullpen, and on the field: AT BAT, 1B, 2B, 3B, MOUND.
3. Your cards show right-side up; your opponent's cards on the field are upside down (mirrored table, like sitting across from each other).
4. **Roll d20** — both players see the same animated roll.
5. Click the out dots to add outs; +/− buttons for runs and half-innings.
6. Double-click any card to zoom it.

Team state lives in the Firebase room, so it persists between sessions as long
as you reuse the same room code.

## Later ideas

- Strategy card decks (draw/hand/discard)
- Persistent named rosters ("load my 2004 Red Sox")
- Automated at-bat resolution (compare roll to control/on-base, highlight chart row)
