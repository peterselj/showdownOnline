// MLB Showdown virtual tabletop — tab router and the Play tab.
// "Dumb tabletop" model: the app syncs cards, zones, dice, and counters;
// the players apply the game rules themselves.

let sync = null;
let mySide = null;   // "home" | "away"
let oppSide = null;
let myName = "";

// ---------------------------------------------------------------------------
// Tabs: #/play[?room=X&side=home], #/rosters, #/strategy.
// Old links of the form #room=X&side=home still open the Play tab.
// ---------------------------------------------------------------------------
function currentTab() {
  const h = location.hash;
  if (h.startsWith("#/rosters")) return "rosters";
  if (h.startsWith("#/strategy")) return "strategy";
  return "play";
}

function playParams() {
  return new URLSearchParams(location.hash.replace(/^#\/?(play)?\??/, ""));
}

function route() {
  const tab = currentTab();
  for (const t of ["play", "rosters", "strategy"]) $(`page-${t}`).classList.toggle("hidden", t !== tab);
  document.querySelectorAll("#tabs .tab").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  hidePeek();
  if (tab === "rosters") RosterBuilder.show();
  if (tab === "strategy") StrategyBuilder.show();
  if (tab === "play" && !sync) refreshRosterSelect();
}

// ---------------------------------------------------------------------------
// Lobby
// ---------------------------------------------------------------------------
const LS_LAST_ROSTER = "showdown-last-roster";

function initLobby() {
  const params = playParams();
  if (params.get("room")) $("room-input").value = params.get("room");
  if (localStorage.getItem("showdown-name")) $("name-input").value = localStorage.getItem("showdown-name");

  $("join-home").onclick = () => join("home", $("roster-select").value);
  $("join-away").onclick = () => join("away", $("roster-select").value);
  $("roster-select").onchange = updateRosterHint;

  // Rejoining from a link keeps whatever is already on the table.
  if (params.get("room") && params.get("side")) {
    $("name-input").value = params.get("name") || $("name-input").value;
    join(params.get("side"), "");
  }
}

function rosterOptionsHTML() {
  const lib = Library.all();
  return Rosters.all().map((r) => {
    const pts = rosterPoints(r, lib).total.toLocaleString();
    const mark = rosterIsLegal(r, lib) ? "✓" : "⚠";
    return `<option value="${esc(r.id)}">${mark} ${esc(r.name)} — ${pts} pts</option>`;
  }).join("");
}

function refreshRosterSelect() {
  const sel = $("roster-select");
  sel.innerHTML = `<option value="">— Empty table (add players at the table) —</option>` + rosterOptionsHTML();
  const last = localStorage.getItem(LS_LAST_ROSTER);
  if (last && Rosters.get(last)) sel.value = last;
  updateRosterHint();
}

function updateRosterHint() {
  const r = Rosters.get($("roster-select").value);
  const hint = $("roster-hint");
  if (!Rosters.all().length) { hint.innerHTML = `No saved rosters yet — <a href="#/rosters">build one</a>.`; return; }
  if (!r) { hint.textContent = ""; return; }
  const errors = validateRoster(r).filter((c) => c.level === "error");
  hint.innerHTML = errors.length
    ? `⚠ Not a legal roster yet: ${esc(errors[0].msg)}${errors.length > 1 ? ` (+${errors.length - 1} more)` : ""}. You can still bring it.`
    : "✓ Legal roster";
}

function join(side, rosterId) {
  const room = $("room-input").value.trim().toUpperCase();
  myName = $("name-input").value.trim() || (side === "home" ? "Home" : "Away");
  if (!room) { $("lobby-status").textContent = "Enter a room code first."; return; }

  mySide = side;
  oppSide = side === "home" ? "away" : "home";
  localStorage.setItem("showdown-name", myName);
  location.hash = `#/play?room=${encodeURIComponent(room)}&side=${side}`;
  document.querySelector('#tabs .tab[data-tab="play"]').href = location.hash;

  sync = createSync(room);
  sync.onChange(render);
  sync.update({ [`players/${side}`]: myName });

  const roster = rosterId && Rosters.get(rosterId);
  if (roster) {
    localStorage.setItem(LS_LAST_ROSTER, roster.id);
    sync.loaded.then(() => {
      const mine = Object.values(sync.state.cards).filter((c) => c.side === mySide);
      if (!mine.length || confirm(`You already have ${mine.length} cards on this table. Replace them with "${roster.name}"?`)) {
        loadRosterToTable(roster);
      }
    });
  }

  $("lobby").classList.add("hidden");
  $("game").classList.remove("hidden");
  buildLineupSlots();
  wireGlobalUI();
  if (!(window.FIREBASE_CONFIG || {}).databaseURL) {
    $("roll-info").textContent = "LOCAL MODE — see README to enable Firebase sync";
  }
}

// ---------------------------------------------------------------------------
// Zones
// ---------------------------------------------------------------------------
// Zone ids: "<side>-lineup-1..9", "<side>-bench", "<side>-rotation", "<side>-bullpen",
// "field-1B" | "field-2B" | "field-3B" | "field-mound" | "field-batter"

function buildLineupSlots() {
  for (const who of ["my", "opp"]) {
    const side = who === "my" ? mySide : oppSide;
    const row = $(`${who}-lineup`);
    row.innerHTML = "";
    for (let i = 1; i <= 9; i++) {
      const slot = document.createElement("div");
      slot.className = "lineup-slot";
      slot.innerHTML = `<span class="zone-label">#${i}</span>`;
      const z = document.createElement("div");
      z.className = "zone";
      z.dataset.zone = `${side}-lineup-${i}`;
      slot.appendChild(z);
      row.appendChild(slot);
    }
    $(`${who}-bench`).dataset.zone = `${side}-bench`;
    $(`${who}-rotation`).dataset.zone = `${side}-rotation`;
    $(`${who}-bullpen`).dataset.zone = `${side}-bullpen`;
  }
  document.querySelectorAll("#game .zone").forEach(wireDropZone);
}

function wireDropZone(zoneEl) {
  zoneEl.addEventListener("dragover", (e) => { e.preventDefault(); zoneEl.classList.add("drag-over"); });
  zoneEl.addEventListener("dragleave", () => zoneEl.classList.remove("drag-over"));
  zoneEl.addEventListener("drop", (e) => {
    e.preventDefault();
    zoneEl.classList.remove("drag-over");
    const cardId = e.dataTransfer.getData("text/plain");
    if (cardId) sync.update({ [`cards/${cardId}/zone`]: zoneEl.dataset.zone, [`cards/${cardId}/ord`]: Date.now() });
  });
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------
function render(state) {
  // titles / scoreboard names
  $("my-title").textContent = `${state.players[mySide] || "…"} (${mySide.toUpperCase()})`;
  $("opp-title").textContent = `${state.players[oppSide] || "waiting for opponent…"} (${oppSide.toUpperCase()})`;
  $("sb-home-name").textContent = (state.players.home || "HOME").toUpperCase().slice(0, 10);
  $("sb-away-name").textContent = (state.players.away || "AWAY").toUpperCase().slice(0, 10);

  // counters
  const c = state.counters;
  $("sb-home-runs").textContent = c.homeRuns;
  $("sb-away-runs").textContent = c.awayRuns;
  $("sb-inning").textContent = `${c.half === "top" ? "▲" : "▼"} ${c.inning}`;
  document.querySelectorAll("#sb-outs .out-dot").forEach((d, i) => d.classList.toggle("lit", i < c.outs));

  // cards
  document.querySelectorAll("#game .zone").forEach((z) => { z.querySelectorAll(".card").forEach((el) => el.remove()); });
  const cards = Object.values(state.cards || {}).sort((a, b) => (a.ord || 0) - (b.ord || 0));
  for (const card of cards) {
    const zoneEl = document.querySelector(`#game .zone[data-zone="${card.zone}"]`);
    if (!zoneEl) continue;
    zoneEl.appendChild(makeCardEl(card));
  }

  renderDice(state.dice);
}

function makeCardEl(card) {
  const el = document.createElement("div");
  el.className = "card " + (card.side === mySide ? "my-card" : "opp-card");
  // On the shared field, flip the opponent's base runners to face them —
  // but the pitcher and batter always face the viewer for legibility.
  const alwaysUpright = card.zone === "field-mound" || card.zone === "field-batter";
  if (card.zone.startsWith("field-") && card.side !== mySide && !alwaysUpright) el.classList.add("flipped");
  el.style.backgroundImage = `url("${card.imgUrl}")`;
  el.draggable = true;
  el.dataset.id = card.id;
  el.innerHTML = `<span class="card-name">${esc(card.name)}</span>`
    + (card.pos && card.zone.includes("-lineup-") ? `<span class="card-pos">${esc(card.pos)}</span>` : "");
  el.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/plain", card.id);
    el.classList.add("dragging");
    hidePeek();
  });
  el.addEventListener("dragend", () => el.classList.remove("dragging"));
  el.addEventListener("dblclick", () => showZoom(card.imgUrl));
  // hover / press-and-hold magnifier
  el.addEventListener("mouseenter", () => showPeek(el, card.imgUrl));
  el.addEventListener("mouseleave", hidePeek);
  el.addEventListener("pointerdown", () => showPeek(el, card.imgUrl));
  el.addEventListener("pointerup", hidePeek);
  return el;
}

// ---------------------------------------------------------------------------
// Dice
// ---------------------------------------------------------------------------
let lastRollId = 0;

function renderDice(dice) {
  if (!dice || !dice.rollId || dice.rollId === lastRollId) return;
  lastRollId = dice.rollId;
  const die = $("die");
  die.className = "rolling";
  let ticks = 0;
  const spin = setInterval(() => {
    die.textContent = 1 + Math.floor(Math.random() * 20);
    if (++ticks >= 12) {
      clearInterval(spin);
      die.textContent = dice.value;
      die.className = "settled";
      $("roll-info").textContent = `${dice.roller} rolled ${dice.value}`;
    }
  }, 80);
}

// ---------------------------------------------------------------------------
// Global UI wiring
// ---------------------------------------------------------------------------
function wireGlobalUI() {
  $("roll-btn").onclick = () => {
    sync.update({ dice: { value: 1 + Math.floor(Math.random() * 20), roller: myName, rollId: Date.now() } });
  };

  document.querySelectorAll(".ctr-btn").forEach((btn) => {
    btn.onclick = () => {
      const d = parseInt(btn.dataset.d, 10);
      const c = sync.state.counters;
      switch (btn.dataset.ctr) {
        case "home-runs": sync.update({ "counters/homeRuns": Math.max(0, c.homeRuns + d) }); break;
        case "away-runs": sync.update({ "counters/awayRuns": Math.max(0, c.awayRuns + d) }); break;
        case "inning": {
          // step through half-innings
          let { inning, half } = c;
          if (d > 0) { if (half === "top") half = "bottom"; else { half = "top"; inning++; } }
          else { if (half === "bottom") half = "top"; else if (inning > 1) { half = "bottom"; inning--; } }
          sync.update({ "counters/inning": inning, "counters/half": half, "counters/outs": 0 });
          break;
        }
      }
    };
  });

  $("sb-outs").onclick = () => {
    sync.update({ "counters/outs": (sync.state.counters.outs + 1) % 4 });
  };

  $("zoom").onclick = () => $("zoom").classList.add("hidden");

  // load-roster modal
  $("load-roster-btn").onclick = () => {
    const opts = rosterOptionsHTML();
    if (!opts) { if (confirm("You have no saved rosters yet. Go to the Rosters tab?")) location.hash = "#/rosters"; return; }
    $("lr-select").innerHTML = opts;
    const last = localStorage.getItem(LS_LAST_ROSTER);
    if (last && Rosters.get(last)) $("lr-select").value = last;
    $("load-modal").classList.remove("hidden");
  };
  $("lr-cancel").onclick = () => $("load-modal").classList.add("hidden");
  $("lr-go").onclick = () => {
    const r = Rosters.get($("lr-select").value);
    $("load-modal").classList.add("hidden");
    if (r) { localStorage.setItem(LS_LAST_ROSTER, r.id); loadRosterToTable(r); }
  };

  // add-player modal
  $("add-player-btn").onclick = () => { $("ap-status").textContent = ""; $("add-modal").classList.remove("hidden"); };
  $("ap-cancel").onclick = () => $("add-modal").classList.add("hidden");
  $("ap-go").onclick = addPlayer;
}

async function addPlayer() {
  const name = $("ap-name").value.trim();
  const year = $("ap-year").value.trim();
  const set = $("ap-set").value;
  if (!name || !year) { $("ap-status").textContent = "Name and year required."; return; }
  $("ap-go").disabled = true;
  try {
    const card = Library.find(name, year, set)
      || await buildPlayerCard(name, year, set, (msg) => { $("ap-status").textContent = msg; });
    Library.put(card);
    const id = "c" + Date.now();
    sync.update({
      [`cards/${id}`]: tableCard(card, {
        id, side: mySide, ord: Date.now(),
        zone: card.isPitcher ? `${mySide}-bullpen` : `${mySide}-bench`,
      }),
    });
    $("ap-status").textContent = `Added ${card.name} (${card.points} pts) ✓`;
    $("ap-name").value = "";
  } catch (err) {
    $("ap-status").textContent = "Failed: " + err.message;
  } finally {
    $("ap-go").disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Rosters -> table
// ---------------------------------------------------------------------------
// The room only accepts flat fields per card (see database.rules.json), so
// copy the scalars shown at the table and flatten the positions object.
function tableCard(card, extra) {
  const out = { libId: card.id, pos: "", positions: positionLabel(card) };
  for (const k of ["name", "year", "set", "points", "command", "outs", "isPitcher", "imgUrl", "role", "ip", "speed", "hand", "team"]) {
    if (card[k] !== undefined && card[k] !== null) out[k] = card[k];
  }
  return Object.assign(out, extra);
}

// Replace all of my cards on the table with a saved roster's cards.
function loadRosterToTable(roster) {
  const lib = Library.all();
  const patch = {};
  for (const c of Object.values(sync.state.cards)) if (c.side === mySide) patch[`cards/${c.id}`] = null;

  const base = Date.now();
  let n = 0;
  const put = (cardId, zone, extra = {}) => {
    const card = lib[cardId];
    if (!card) return;
    const id = `c${base}${n}`;
    patch[`cards/${id}`] = tableCard(card, Object.assign({ id, side: mySide, zone, ord: base + n }, extra));
    n++;
  };
  roster.lineup.forEach((s, i) => s.cardId && put(s.cardId, `${mySide}-lineup-${i + 1}`, { pos: s.pos || "" }));
  roster.bench.forEach((id) => put(id, `${mySide}-bench`));
  roster.rotation.forEach((id) => put(id, `${mySide}-rotation`));
  roster.bullpen.forEach((id) => put(id, `${mySide}-bullpen`));
  sync.update(patch);
  $("roll-info").textContent = `${myName} brought "${roster.name}"`;
}

window.addEventListener("hashchange", route);
initLobby();
route();
