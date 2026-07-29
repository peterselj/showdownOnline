// MLB Showdown virtual tabletop — main UI logic.
// "Dumb tabletop" model: the app syncs cards, zones, dice, and counters;
// the players apply the game rules themselves.

let sync = null;
let mySide = null;   // "home" | "away"
let oppSide = null;
let myName = "";

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------------------
// Lobby
// ---------------------------------------------------------------------------
function initLobby() {
  const params = new URLSearchParams(location.hash.slice(1));
  if (params.get("room")) $("room-input").value = params.get("room");
  if (localStorage.getItem("showdown-name")) $("name-input").value = localStorage.getItem("showdown-name");

  $("join-home").onclick = () => join("home");
  $("join-away").onclick = () => join("away");

  if (params.get("room") && params.get("side")) {
    $("name-input").value = params.get("name") || $("name-input").value;
    join(params.get("side"));
  }
}

function join(side) {
  const room = $("room-input").value.trim().toUpperCase();
  myName = $("name-input").value.trim() || (side === "home" ? "Home" : "Away");
  if (!room) { $("lobby-status").textContent = "Enter a room code first."; return; }

  mySide = side;
  oppSide = side === "home" ? "away" : "home";
  localStorage.setItem("showdown-name", myName);
  location.hash = `room=${room}&side=${side}`;

  sync = createSync(room);
  sync.onChange(render);
  sync.update({ [`players/${side}`]: myName });

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
// Zone ids: "<side>-lineup-1..9", "<side>-bench", "<side>-bullpen",
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
    $(`${who}-bullpen`).dataset.zone = `${side}-bullpen`;
  }
  document.querySelectorAll(".zone").forEach(wireDropZone);
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
  document.querySelectorAll(".zone").forEach((z) => { z.querySelectorAll(".card").forEach((el) => el.remove()); });
  const cards = Object.values(state.cards || {}).sort((a, b) => (a.ord || 0) - (b.ord || 0));
  for (const card of cards) {
    const zoneEl = document.querySelector(`.zone[data-zone="${card.zone}"]`);
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
  el.innerHTML = `<span class="card-name">${card.name}</span>`;
  el.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/plain", card.id);
    el.classList.add("dragging");
    hidePeek();
  });
  el.addEventListener("dragend", () => el.classList.remove("dragging"));
  el.addEventListener("dblclick", () => {
    $("zoom-img").src = card.imgUrl;
    $("zoom").classList.remove("hidden");
  });
  // hover / press-and-hold magnifier
  el.addEventListener("mouseenter", () => showPeek(el, card.imgUrl));
  el.addEventListener("mouseleave", hidePeek);
  el.addEventListener("pointerdown", () => showPeek(el, card.imgUrl));
  el.addEventListener("pointerup", hidePeek);
  return el;
}

// ---------------------------------------------------------------------------
// Hover magnifier
// ---------------------------------------------------------------------------
function showPeek(cardEl, imgUrl) {
  const peek = $("peek");
  $("peek-img").src = imgUrl;
  peek.classList.remove("hidden");
  const r = cardEl.getBoundingClientRect();
  const pw = Math.min(340, window.innerWidth * 0.38);
  const ph = pw * 1.4;
  // prefer to the right of the card; flip left if it would overflow
  let x = r.right + 12;
  if (x + pw > window.innerWidth - 8) x = r.left - pw - 12;
  let y = Math.min(Math.max(8, r.top + r.height / 2 - ph / 2), window.innerHeight - ph - 8);
  peek.style.left = Math.max(8, x) + "px";
  peek.style.top = y + "px";
}

function hidePeek() { $("peek").classList.add("hidden"); }

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
    const card = await buildPlayerCard(name, year, set, (msg) => { $("ap-status").textContent = msg; });
    const id = "c" + Date.now();
    sync.update({
      [`cards/${id}`]: Object.assign(card, {
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

initLobby();
