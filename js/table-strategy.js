// Strategy cards at the table: each player's deck (draw pile), hand and
// discard pile, plus a shared "in play" area on the field.
//
// Room data: strat/<instanceId> = {cardId, side, zone, ord}
//   zone: "draw" | "hand" | "play" | "discard"; lowest ord = top of the deck.
// Card details come from the static catalog (data/strategy-cards.json), so the
// room only stores ids. Hands are hidden from the opponent by the UI — an
// honor system, like the rest of the tabletop.

const OPENING_HAND = 4;

function stratCards(side, zone) {
  return Object.entries(sync.state.strat || {})
    .filter(([, s]) => s.side === side && s.zone === zone)
    .map(([id, s]) => ({ ...s, id }))
    .sort((a, b) => a.ord - b.ord);
}

function moveStrat(id, zone) {
  hideCardMenu();
  sync.update({ [`strat/${id}/zone`]: zone, [`strat/${id}/ord`]: Date.now() });
}

function shuffled(list) {
  const a = [...list];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// Replace my deck, hand and discard with a fresh shuffle of a saved deck,
// and deal the opening hand. My cards in play are cleared too.
function loadDeckToTable(deck) {
  const patch = {};
  for (const [id, s] of Object.entries(sync.state.strat || {})) if (s.side === mySide) patch[`strat/${id}`] = null;
  const ids = [];
  for (const [cardId, n] of Object.entries(deck.cards)) for (let i = 0; i < n; i++) ids.push(cardId);
  const base = Date.now();
  shuffled(ids).forEach((cardId, i) => {
    patch[`strat/s${base}${i}`] = { cardId, side: mySide, zone: i < OPENING_HAND ? "hand" : "draw", ord: i };
  });
  sync.update(patch);
  $("roll-info").textContent = `${myName} shuffled "${deck.name}" and drew ${Math.min(OPENING_HAND, ids.length)}`;
}

function drawCard() {
  const top = stratCards(mySide, "draw")[0];
  if (top) moveStrat(top.id, "hand");
}

// Discard pile goes back into the deck, and the whole deck is reshuffled.
function shuffleDiscardIntoDeck() {
  const pile = [...stratCards(mySide, "draw"), ...stratCards(mySide, "discard")];
  const patch = {};
  shuffled(pile).forEach((s, i) => {
    patch[`strat/${s.id}/zone`] = "draw";
    patch[`strat/${s.id}/ord`] = i;
  });
  sync.update(patch);
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------
function stratMiniEl(inst, { faceUp, mine }) {
  const card = StrategyCatalog.get(inst.cardId);
  const el = document.createElement("div");
  if (!faceUp || !card) {
    el.className = "smini sback";
    el.innerHTML = `<span>MLB<br>SHOWDOWN</span>`;
    return el;
  }
  const type = card.type.toLowerCase();
  el.className = `smini sface-${type} ${inst.side === mySide ? "my-strat" : "opp-strat"}`;
  el.innerHTML = `<span class="sm-name">${esc(card.name)}</span><span class="sm-year">${esc(yearTag(card))}</span>`;
  el.addEventListener("mouseenter", () => showPeekFace(el, card));
  el.addEventListener("mouseleave", hidePeek);
  if (mine) {
    el.draggable = true;
    el.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/strat", inst.id);
      el.classList.add("dragging");
      hidePeek();
    });
    el.addEventListener("dragend", () => el.classList.remove("dragging"));
  }
  return el;
}

function renderStrategy() {
  if (!sync) return;
  for (const [who, side] of [["my", mySide], ["opp", oppSide]]) {
    const draw = stratCards(side, "draw"), hand = stratCards(side, "hand"), discard = stratCards(side, "discard");
    $(`${who}-draw-n`).textContent = draw.length;
    $(`${who}-hand-n`).textContent = hand.length;
    $(`${who}-discard-n`).textContent = discard.length;

    const drawEl = $(`${who}-draw`);
    drawEl.innerHTML = "";
    if (draw.length) drawEl.appendChild(stratMiniEl(draw[0], { faceUp: false }));

    const discEl = $(`${who}-discard`);
    discEl.innerHTML = "";
    if (discard.length) discEl.appendChild(stratMiniEl(discard[discard.length - 1], { faceUp: true, mine: false }));

    const handEl = $(`${who}-hand`);
    handEl.innerHTML = "";
    for (const inst of hand) {
      const el = stratMiniEl(inst, { faceUp: who === "my", mine: who === "my" });
      if (who === "my") {
        el.addEventListener("click", (e) => showCardMenu(e, el, [
          ["Play face up", () => moveStrat(inst.id, "play")],
          ["Discard", () => moveStrat(inst.id, "discard")],
        ]));
      }
      handEl.appendChild(el);
    }
  }

  // shared in-play area: both players' cards, oldest first
  const playEl = $("play-cards");
  playEl.innerHTML = "";
  const inPlay = Object.entries(sync.state.strat || {})
    .filter(([, s]) => s.zone === "play").map(([id, s]) => ({ ...s, id }))
    .sort((a, b) => a.ord - b.ord);
  for (const inst of inPlay) {
    const mine = inst.side === mySide;
    const el = stratMiniEl(inst, { faceUp: true, mine });
    if (mine) {
      el.addEventListener("click", (e) => showCardMenu(e, el, [
        ["Discard", () => moveStrat(inst.id, "discard")],
        ["Back to hand", () => moveStrat(inst.id, "hand")],
      ]));
    }
    playEl.appendChild(el);
  }
  $("play-area").classList.toggle("empty", !inPlay.length);
}

// ---------------------------------------------------------------------------
// Card action menu and discard viewer
// ---------------------------------------------------------------------------
function showCardMenu(e, anchor, actions) {
  e.stopPropagation();
  hidePeek();
  const menu = $("card-menu");
  menu.innerHTML = "";
  for (const [label, fn] of actions) {
    const b = document.createElement("button");
    b.textContent = label;
    b.onclick = (ev) => { ev.stopPropagation(); fn(); };
    menu.appendChild(b);
  }
  menu.classList.remove("hidden");
  const r = anchor.getBoundingClientRect();
  const top = r.top - menu.offsetHeight - 6 > 0 ? r.top - menu.offsetHeight - 6 : r.bottom + 6;
  menu.style.left = Math.min(r.left, window.innerWidth - menu.offsetWidth - 8) + "px";
  menu.style.top = top + "px";
}

function hideCardMenu() { $("card-menu").classList.add("hidden"); }

function showDiscardPile(side) {
  const mine = side === mySide;
  const pile = stratCards(side, "discard").reverse();   // newest first
  $("pile-title").textContent = `${mine ? "Your" : (sync.state.players[side] || "Opponent") + "'s"} discard pile (${pile.length})`;
  const list = $("pile-list");
  list.innerHTML = pile.length ? "" : `<p class="rb-placeholder">Empty</p>`;
  for (const inst of pile) {
    const card = StrategyCatalog.get(inst.cardId);
    if (!card) continue;
    const row = document.createElement("div");
    row.className = "pile-row";
    row.innerHTML = strategyFaceHTML(card);
    if (mine) {
      const back = document.createElement("button");
      back.className = "btn btn-tiny";
      back.textContent = "To hand";
      back.onclick = () => { moveStrat(inst.id, "hand"); showDiscardPile(side); };
      row.appendChild(back);
    }
    list.appendChild(row);
  }
  $("pile-shuffle").classList.toggle("hidden", !mine);
  $("pile-modal").classList.remove("hidden");
}

// ---------------------------------------------------------------------------
// Wiring (called once when joining a room)
// ---------------------------------------------------------------------------
function wireStrategyTable() {
  StrategyCatalog.load().then(renderStrategy).catch((err) => { $("roll-info").textContent = err.message; });

  $("my-draw").onclick = drawCard;
  $("my-discard").onclick = () => showDiscardPile(mySide);
  $("opp-discard").onclick = () => showDiscardPile(oppSide);
  $("pile-close").onclick = () => $("pile-modal").classList.add("hidden");
  $("pile-shuffle").onclick = () => {
    if (!confirm("Shuffle your discard pile back into your deck?")) return;
    shuffleDiscardIntoDeck();
    $("pile-modal").classList.add("hidden");
  };
  document.addEventListener("click", hideCardMenu);

  document.querySelectorAll(".strat-drop").forEach((el) => {
    el.addEventListener("dragover", (e) => {
      if (!e.dataTransfer.types.includes("text/strat")) return;
      e.preventDefault();
      el.classList.add("drag-over");
    });
    el.addEventListener("dragleave", () => el.classList.remove("drag-over"));
    el.addEventListener("drop", (e) => {
      el.classList.remove("drag-over");
      const id = e.dataTransfer.getData("text/strat");
      if (!id) return;
      e.preventDefault();
      if (sync.state.strat?.[id]?.side === mySide) moveStrat(id, el.dataset.szone);
    });
  });

  $("load-deck-btn").onclick = () => {
    const opts = deckOptionsHTML();
    if (!opts) { if (confirm("You have no saved strategy decks yet. Go to the Strategy tab?")) location.hash = "#/strategy"; return; }
    $("ld-select").innerHTML = opts;
    const last = localStorage.getItem(LS_LAST_DECK);
    if (last && Decks.get(last)) $("ld-select").value = last;
    $("deck-modal").classList.remove("hidden");
  };
  $("ld-cancel").onclick = () => $("deck-modal").classList.add("hidden");
  $("ld-go").onclick = async () => {
    const d = Decks.get($("ld-select").value);
    $("deck-modal").classList.add("hidden");
    if (!d) return;
    const mine = Object.values(sync.state.strat || {}).filter((s) => s.side === mySide).length;
    if (mine && !confirm("Replace your current deck, hand and discard with a fresh shuffle?")) return;
    localStorage.setItem(LS_LAST_DECK, d.id);
    loadDeckToTable(d);
  };
}

// ---------------------------------------------------------------------------
// Lobby
// ---------------------------------------------------------------------------
const LS_LAST_DECK = "showdown-last-deck";

function deckOptionsHTML() {
  return Decks.all().map((d) => {
    const mark = deckIsLegal(d, StrategyCatalog.all()) ? "✓" : "⚠";
    return `<option value="${esc(d.id)}">${mark} ${esc(d.name)} — ${deckSize(d)} cards</option>`;
  }).join("");
}

async function refreshDeckSelect() {
  await StrategyCatalog.load().catch(() => null);
  const sel = $("deck-select");
  sel.innerHTML = `<option value="">— No strategy deck —</option>` + deckOptionsHTML();
  const last = localStorage.getItem(LS_LAST_DECK);
  if (last && Decks.get(last)) sel.value = last;
  $("deck-hint").innerHTML = Decks.all().length ? "" : `No saved decks yet — <a href="#/strategy">build one</a>.`;
}
