// Browser-local storage for the card library and saved rosters, plus the
// roster rules and validation used by the Rosters tab and the Play lobby.
// Everything here lives in this browser's localStorage only.

// Team-building rules (later-era Showdown: bench players cost full points).
// Edit these to play house rules.
const RULES = {
  pointCap: 5000,
  rosterSize: 20,   // exact number of players a legal roster needs
  lineupSize: 9,
  minStarters: 4,
  maxStarters: 5,
  maxRosters: 5,
};

const LINEUP_POSITIONS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"];

// Printed positions that cover more than one lineup spot.
const POSITION_GROUPS = { "LF/RF": ["LF", "RF"], "OF": ["LF", "CF", "RF"], "IF": ["1B", "2B", "3B", "SS"] };

const normName = (name) => String(name || "")
  .normalize("NFD").replace(/[̀-ͯ]/g, "")
  .toLowerCase().replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ").trim();

// Library id for a card: same player + season + set = same card.
const cardKey = (name, year, set) => `${normName(name)}|${String(year).trim()}|${set}`;

function eligiblePositions(card) {
  if (!card || card.isPitcher) return [];
  const out = new Set(["DH"]);
  for (const p of Object.keys(card.positions || {})) (POSITION_GROUPS[p] || [p]).forEach((x) => out.add(x));
  return [...out];
}

// "SS+2, 2B+1" for hitters, "SP · IP 7" for pitchers.
function positionLabel(card) {
  if (card.isPitcher) return `${card.role || "P"}${card.ip != null ? " · IP " + card.ip : ""}`;
  return Object.entries(card.positions || {})
    .map(([p, v]) => (p === "DH" ? "DH" : `${p}+${v}`)).join(", ") || "DH";
}

function lsGet(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function lsSet(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); return true; }
  catch (err) { console.error("localStorage write failed", err); return false; }
}

// ---------------------------------------------------------------------------
// Card library: id -> card (as returned by buildPlayerCard)
// ---------------------------------------------------------------------------
const LS_LIBRARY = "showdown-library-v1";

const Library = {
  all() { return lsGet(LS_LIBRARY, {}); },
  get(id) { return this.all()[id] || null; },
  find(name, year, set) { return this.get(cardKey(name, year, set)); },
  put(card) { const lib = this.all(); lib[card.id] = card; lsSet(LS_LIBRARY, lib); },
  remove(id) {
    const lib = this.all(); delete lib[id]; lsSet(LS_LIBRARY, lib);
    for (const r of Rosters.all()) if (rosterDetach(r, id)) Rosters.save(r);
  },
};

// ---------------------------------------------------------------------------
// Rosters: ordered list of
//   {id, name, lineup: [{cardId, pos}] x9, bench: [cardId], rotation: [cardId],
//    bullpen: [cardId], updated}
// ---------------------------------------------------------------------------
const LS_ROSTERS = "showdown-rosters-v1";

const newRoster = (name) => ({
  id: "r" + Date.now().toString(36),
  name,
  lineup: Array.from({ length: RULES.lineupSize }, () => ({ cardId: null, pos: "" })),
  bench: [], rotation: [], bullpen: [],
  updated: Date.now(),
});

const Rosters = {
  all() { return lsGet(LS_ROSTERS, []); },
  get(id) { return this.all().find((r) => r.id === id) || null; },
  save(roster) {
    roster.updated = Date.now();
    const list = this.all();
    const i = list.findIndex((r) => r.id === roster.id);
    if (i >= 0) list[i] = roster; else list.push(roster);
    lsSet(LS_ROSTERS, list);
  },
  remove(id) { lsSet(LS_ROSTERS, this.all().filter((r) => r.id !== id)); },
};

// ---------------------------------------------------------------------------
// Roster editing primitives (mutate the roster object; caller saves)
// ---------------------------------------------------------------------------
const ROSTER_LISTS = ["bench", "rotation", "bullpen"];

function rosterLocate(r, cardId) {
  const li = r.lineup.findIndex((s) => s.cardId === cardId);
  if (li >= 0) return { list: "lineup", i: li };
  for (const list of ROSTER_LISTS) {
    const i = r[list].indexOf(cardId);
    if (i >= 0) return { list, i };
  }
  return null;
}

function rosterDetach(r, cardId) {
  const loc = rosterLocate(r, cardId);
  if (!loc) return null;
  if (loc.list === "lineup") r.lineup[loc.i] = { cardId: null, pos: "" };
  else r[loc.list].splice(loc.i, 1);
  return loc;
}

// Best free lineup position for a hitter: a printed position nobody holds,
// then DH, else blank for the player to choose.
function autoPosition(r, card, slotIndex) {
  const taken = new Set(r.lineup.filter((s, i) => i !== slotIndex && s.cardId).map((s) => s.pos));
  const elig = eligiblePositions(card);
  return elig.find((p) => p !== "DH" && !taken.has(p)) || (!taken.has("DH") && elig.includes("DH") ? "DH" : "");
}

// Move a card to {list: "lineup", i} or {list: "bench"|"rotation"|"bullpen", i?}.
// Dropping onto an occupied lineup spot swaps with whoever is there.
function rosterPlace(r, cardId, target, lib = Library.all()) {
  const src = rosterLocate(r, cardId);
  if (target.list === "lineup") {
    const t = target.i;
    if (src && src.list === "lineup") {
      [r.lineup[src.i], r.lineup[t]] = [r.lineup[t], r.lineup[src.i]];
      return;
    }
    const occupant = r.lineup[t].cardId;
    rosterDetach(r, cardId);
    if (occupant) {
      if (src) r[src.list].splice(src.i, 0, occupant); else r.bench.push(occupant);
    }
    r.lineup[t] = { cardId, pos: "" };
    r.lineup[t].pos = autoPosition(r, lib[cardId], t);
    return;
  }
  rosterDetach(r, cardId);
  const arr = r[target.list];
  let i = target.i ?? arr.length;
  if (src && src.list === target.list && src.i < i) i--;   // list shrank above the target
  arr.splice(Math.min(i, arr.length), 0, cardId);
}

// Where a quick "+ Add" puts a card: hitters fill the batting order then the
// bench; starters fill the rotation then the bullpen; relievers go to the pen.
function rosterQuickAdd(r, card) {
  if (rosterLocate(r, card.id)) return false;
  if (!card.isPitcher) {
    const empty = r.lineup.findIndex((s) => !s.cardId);
    rosterPlace(r, card.id, empty >= 0 ? { list: "lineup", i: empty } : { list: "bench" });
  } else if (card.role === "SP" && r.rotation.length < RULES.maxStarters) {
    rosterPlace(r, card.id, { list: "rotation" });
  } else {
    rosterPlace(r, card.id, { list: "bullpen" });
  }
  return true;
}

// ---------------------------------------------------------------------------
// Points and validation
// ---------------------------------------------------------------------------
function rosterPoints(r, lib = Library.all()) {
  const pts = (id) => Number(lib[id]?.points) || 0;
  const lineup = r.lineup.reduce((sum, s) => sum + (s.cardId ? pts(s.cardId) : 0), 0);
  const bench = r.bench.reduce((sum, id) => sum + pts(id), 0);
  const pitching = [...r.rotation, ...r.bullpen].reduce((sum, id) => sum + pts(id), 0);
  return { lineup, bench, pitching, total: lineup + bench + pitching };
}

function rosterCount(r) {
  return r.lineup.filter((s) => s.cardId).length + r.bench.length + r.rotation.length + r.bullpen.length;
}

// Returns [{level: "error"|"warn"|"ok", msg}]. A roster is legal when there
// are no errors; warnings (out of position, over or under budget) are advisory.
function validateRoster(r, lib = Library.all()) {
  const out = [];
  const add = (level, msg) => out.push({ level, msg });
  const cards = (ids) => ids.map((id) => lib[id]).filter(Boolean);
  const filled = r.lineup.filter((s) => s.cardId && lib[s.cardId]).map((s) => ({ ...s, card: lib[s.cardId] }));
  const bench = cards(r.bench), rotation = cards(r.rotation), bullpen = cards(r.bullpen);

  // roster size
  const count = rosterCount(r);
  if (count === RULES.rosterSize) add("ok", `${count}/${RULES.rosterSize} players`);
  else if (count < RULES.rosterSize) add("error", `${count}/${RULES.rosterSize} players — add ${RULES.rosterSize - count}`);
  else add("error", `${count}/${RULES.rosterSize} players — cut ${count - RULES.rosterSize}`);

  // batting order and positions
  if (filled.length < RULES.lineupSize) add("error", `Batting order ${filled.length}/${RULES.lineupSize} filled`);
  const posCount = {};
  filled.forEach((s) => { if (s.pos) posCount[s.pos] = (posCount[s.pos] || 0) + 1; });
  const missing = LINEUP_POSITIONS.filter((p) => !posCount[p]);
  const doubled = LINEUP_POSITIONS.filter((p) => posCount[p] > 1);
  if (!missing.length && !doubled.length) add("ok", "All 9 positions covered");
  if (missing.length) add("error", `Nobody playing ${missing.join(", ")}`);
  if (doubled.length) add("error", `More than one player at ${doubled.join(", ")}`);
  for (const s of filled) {
    if (s.card.isPitcher) add("error", `${s.card.name} is a pitcher — can't be in the batting order`);
    else if (!s.pos) add("error", `${s.card.name} needs a position`);
    else if (s.pos && !eligiblePositions(s.card).includes(s.pos)) add("warn", `${s.card.name} is out of position at ${s.pos}`);
  }
  bench.filter((c) => c.isPitcher).forEach((c) => add("error", `${c.name} is a pitcher — move to rotation or bullpen`));
  [...rotation, ...bullpen].filter((c) => !c.isPitcher)
    .forEach((c) => add("error", `${c.name} is a hitter — move to the lineup or bench`));

  // pitching staff
  const n = rotation.length;
  if (n < RULES.minStarters) add("error", `Rotation has ${n} — needs at least ${RULES.minStarters} starters`);
  else if (n > RULES.maxStarters) add("error", `Rotation has ${n} — at most ${RULES.maxStarters} starters`);
  else add("ok", `${n}-man rotation`);
  rotation.filter((c) => c.role === "RP").forEach((c) => add("warn", `${c.name} is a reliever in the rotation`));
  bullpen.filter((c) => c.role === "SP").forEach((c) => add("warn", `${c.name} is a starter in the bullpen`));

  // the same player twice (even from different seasons)
  const seen = {};
  [...filled.map((s) => s.card), ...bench, ...rotation, ...bullpen].forEach((c) => {
    const k = normName(c.name); seen[k] = (seen[k] || 0) + 1;
    if (seen[k] === 2) add("error", `${c.name} is on the roster twice`);
  });

  // budget
  const { total } = rosterPoints(r, lib);
  const cap = RULES.pointCap;
  // Over budget is a warning, not an error: card values aren't known until
  // they're built, so an over-cap roster must still be playable.
  if (total > cap) add("warn", `${total.toLocaleString()} pts — ${(total - cap).toLocaleString()} over the ${cap.toLocaleString()} cap`);
  else if (total < cap) add("warn", `${(cap - total).toLocaleString()} pts unspent`);
  else add("ok", `Exactly ${cap.toLocaleString()} pts`);

  const rank = { error: 0, warn: 1, ok: 2 };
  return out.sort((a, b) => rank[a.level] - rank[b.level]);
}

const rosterIsLegal = (r, lib) => !validateRoster(r, lib).some((c) => c.level === "error");

// ---------------------------------------------------------------------------
// Strategy cards and decks
// ---------------------------------------------------------------------------
// The catalog (every strategy card ever printed) is a static file imported by
// scripts/import_strategy_cards.py; decks are saved in this browser.
const DECK_RULES = {
  size: 60,        // exact number of cards in a deck
  maxCopies: 4,    // per card name, counted across every printing/year
  maxDecks: 5,
};

let _catalog = null;
const StrategyCatalog = {
  // Resolves to {id: card}. Loaded once per page.
  async load() {
    if (!_catalog) {
      const res = await fetch("data/strategy-cards.json");
      if (!res.ok) throw new Error(`Couldn't load strategy cards (${res.status})`);
      _catalog = Object.fromEntries((await res.json()).map((c) => [c.id, c]));
    }
    return _catalog;
  },
  get(id) { return _catalog?.[id] || null; },
  all() { return _catalog || {}; },
};

// Short year label, e.g. "'03".
const yearTag = (card) => "'" + String(card.year || "").slice(-2);

const LS_DECKS = "showdown-decks-v1";

// Deck: {id, name, cards: {cardId: count}, updated}
const newDeck = (name) => ({ id: "d" + Date.now().toString(36), name, cards: {}, updated: Date.now() });

const Decks = {
  all() { return lsGet(LS_DECKS, []); },
  get(id) { return this.all().find((d) => d.id === id) || null; },
  save(deck) {
    deck.updated = Date.now();
    const list = this.all();
    const i = list.findIndex((d) => d.id === deck.id);
    if (i >= 0) list[i] = deck; else list.push(deck);
    lsSet(LS_DECKS, list);
  },
  remove(id) { lsSet(LS_DECKS, this.all().filter((d) => d.id !== id)); },
};

const deckSize = (deck) => Object.values(deck.cards).reduce((a, b) => a + b, 0);

// Copies per card name across all printings: {baseName: {total, byId: {id: n}}}
function deckCopies(deck, catalog = StrategyCatalog.all()) {
  const out = {};
  for (const [id, n] of Object.entries(deck.cards)) {
    const card = catalog[id];
    if (!card || !n) continue;
    const entry = out[card.baseName] || (out[card.baseName] = { total: 0, byId: {} });
    entry.total += n;
    entry.byId[id] = n;
  }
  return out;
}

// How many more copies of this card's name the deck may take.
function copiesLeft(deck, card, catalog) {
  return DECK_RULES.maxCopies - (deckCopies(deck, catalog)[card.baseName]?.total || 0);
}

function validateDeck(deck, catalog = StrategyCatalog.all()) {
  const out = [];
  const add = (level, msg) => out.push({ level, msg });
  const size = deckSize(deck);
  if (size === DECK_RULES.size) add("ok", `${size}/${DECK_RULES.size} cards`);
  else if (size < DECK_RULES.size) add("error", `${size}/${DECK_RULES.size} cards — add ${DECK_RULES.size - size}`);
  else add("error", `${size}/${DECK_RULES.size} cards — cut ${size - DECK_RULES.size}`);

  const over = Object.values(deckCopies(deck, catalog)).filter((e) => e.total > DECK_RULES.maxCopies);
  for (const e of over) {
    const ids = Object.keys(e.byId);
    const printings = ids.map((id) => `${yearTag(catalog[id])} ×${e.byId[id]}`).join(", ");
    add("error", `${catalog[ids[0]].name}: ${e.total} copies (max ${DECK_RULES.maxCopies}) — ${printings}`);
  }
  if (!over.length) add("ok", `No card over ${DECK_RULES.maxCopies} copies`);

  const missing = Object.keys(deck.cards).filter((id) => !catalog[id]);
  if (missing.length) add("warn", `${missing.length} card(s) no longer in the catalog`);

  const rank = { error: 0, warn: 1, ok: 2 };
  return out.sort((a, b) => rank[a.level] - rank[b.level]);
}

const deckIsLegal = (deck, catalog) => !validateDeck(deck, catalog).some((c) => c.level === "error");
