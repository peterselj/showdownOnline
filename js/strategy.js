// Strategy tab: browse every strategy card ever printed and build 60-card
// decks (max 4 copies per card name across all years), saved in this browser.

const StrategyBuilder = (() => {
  const LS_CURRENT = "showdown-current-deck";
  const TYPES = ["Offense", "Defense", "Utility"];
  let currentId = null;
  let wired = false;
  let catalog = null;

  const current = () => (currentId && Decks.get(currentId)) || null;

  async function show() {
    if (!wired) { wire(); wired = true; }
    if (!catalog) {
      try { catalog = await StrategyCatalog.load(); }
      catch (err) { $("cat-count").textContent = err.message; return; }
    }
    if (!current()) currentId = localStorage.getItem(LS_CURRENT);
    if (!current()) currentId = Decks.all()[0]?.id || null;
    renderAll();
  }

  function select(id) {
    currentId = id;
    try { localStorage.setItem(LS_CURRENT, id || ""); } catch { /* per-viewer convenience only */ }
    renderAll();
  }

  function edit(fn) {
    const d = current();
    if (!d) return;
    fn(d);
    Decks.save(d);
    renderAll();
  }

  const addCard = (id) => edit((d) => {
    if (copiesLeft(d, catalog[id], catalog) > 0) d.cards[id] = (d.cards[id] || 0) + 1;
  });
  const removeCard = (id) => edit((d) => {
    if (--d.cards[id] <= 0) delete d.cards[id];
  });

  // -------------------------------------------------------------------------
  // Wiring
  // -------------------------------------------------------------------------
  function wire() {
    for (const id of ["cat-search", "cat-type", "cat-year", "cat-sort"]) $(id).addEventListener("input", renderCatalog);
    $("dk-first").onclick = createDeck;
    $("deck-name").addEventListener("input", (e) => {
      const d = current();
      if (!d) return;
      d.name = e.target.value.slice(0, 30) || "Untitled";
      Decks.save(d);
      renderTabs();
    });
    $("dk-dup").onclick = () => {
      const d = current();
      if (!d || Decks.all().length >= DECK_RULES.maxDecks) return;
      const copy = JSON.parse(JSON.stringify(d));
      copy.id = "d" + Date.now().toString(36);
      copy.name = (d.name + " copy").slice(0, 30);
      Decks.save(copy);
      select(copy.id);
    };
    $("dk-del").onclick = () => {
      const d = current();
      if (!d || !confirm(`Delete deck "${d.name}"?`)) return;
      Decks.remove(d.id);
      select(Decks.all()[0]?.id || null);
    };
  }

  function createDeck() {
    const n = Decks.all().length;
    if (n >= DECK_RULES.maxDecks) return;
    const d = newDeck(`Deck ${n + 1}`);
    Decks.save(d);
    select(d.id);
    $("deck-name").select();
  }

  function peekable(el, card) {
    el.addEventListener("mouseenter", () => showPeekFace(el, card));
    el.addEventListener("mouseleave", hidePeek);
  }

  // -------------------------------------------------------------------------
  // Rendering
  // -------------------------------------------------------------------------
  function renderAll() {
    renderTabs();
    renderDeck();
    renderCatalog();
  }

  function renderTabs() {
    const list = Decks.all();
    const el = $("deck-tabs");
    el.innerHTML = list.map((d) => `
      <button class="rt ${d.id === currentId ? "active" : ""}" data-id="${esc(d.id)}">
        <span class="rt-dot ${deckIsLegal(d, catalog) ? "ok" : "bad"}"></span>${esc(d.name)}
      </button>`).join("")
      + (!list.length ? ""
        : list.length < DECK_RULES.maxDecks
          ? `<button class="rt rt-new" id="dt-new">+ New deck</button>`
          : `<span class="rt-max">${DECK_RULES.maxDecks} decks max</span>`);
    el.querySelectorAll(".rt[data-id]").forEach((b) => { b.onclick = () => select(b.dataset.id); });
    if ($("dt-new")) $("dt-new").onclick = createDeck;
  }

  function renderDeck() {
    const d = current();
    $("dk-empty").classList.toggle("hidden", !!d);
    $("dk-body").classList.toggle("hidden", !d);
    if (!d) return;

    if (document.activeElement !== $("deck-name")) $("deck-name").value = d.name;
    $("dk-dup").disabled = Decks.all().length >= DECK_RULES.maxDecks;

    // meter: size against 60, split by type
    const byType = Object.fromEntries(TYPES.map((t) => [t, 0]));
    for (const [id, n] of Object.entries(d.cards)) if (catalog[id]) byType[catalog[id].type] = (byType[catalog[id].type] || 0) + n;
    const size = deckSize(d);
    const scale = Math.max(DECK_RULES.size, size);
    const pct = (v) => (100 * v / scale).toFixed(2) + "%";
    const diff = size - DECK_RULES.size;
    const status = diff > 0 ? `<span class="bud-over">${diff} too many</span>`
      : diff < 0 ? `<span class="bud-under">${-diff} to go</span>`
      : `<span class="bud-ok">ready</span>`;
    $("deck-meter").innerHTML = `
      <div class="bud-top"><b>${size}</b> / ${DECK_RULES.size} cards · ${status}</div>
      <div class="bud-bar">${TYPES.map((t) => `<span class="seg seg-${t.toLowerCase()}" style="width:${pct(byType[t])}"></span>`).join("")}
        <span class="bud-cap" style="left:${pct(DECK_RULES.size)}"></span></div>
      <div class="bud-legend">${TYPES.map((t) => `<span><i class="seg-${t.toLowerCase()}"></i>${t} ${byType[t]}</span>`).join("")}</div>`;
    $("deck-meter").className = "budget" + (diff > 0 ? " over" : "");

    // deck list, grouped by type
    const copies = deckCopies(d, catalog);
    const list = $("deck-list");
    list.innerHTML = "";
    const entries = Object.entries(d.cards).filter(([id]) => catalog[id])
      .sort(([a], [b]) => catalog[a].name.localeCompare(catalog[b].name) || catalog[a].year.localeCompare(catalog[b].year));
    for (const t of TYPES) {
      const rows = entries.filter(([id]) => catalog[id].type === t);
      const h = document.createElement("h3");
      h.innerHTML = `${t} <span class="rb-n">${byType[t]}</span>`;
      list.appendChild(h);
      if (!rows.length) {
        list.insertAdjacentHTML("beforeend", `<p class="rb-placeholder">No ${t.toLowerCase()} cards yet</p>`);
        continue;
      }
      for (const [id, n] of rows) {
        const card = catalog[id];
        const total = copies[card.baseName].total;
        const row = document.createElement("div");
        row.className = `dk-row sface-${t.toLowerCase()}` + (total > DECK_RULES.maxCopies ? " over" : "");
        row.innerHTML = `
          <span class="dk-n">${n}×</span>
          <span class="dk-name">${esc(card.name)} <small>${esc(yearTag(card))}</small></span>
          <span class="dk-limit" title="Copies of this name across all years">${total}/${DECK_RULES.maxCopies}</span>
          <button class="dk-btn" data-d="-1" title="Remove one">−</button>
          <button class="dk-btn" data-d="1" title="Add one" ${total >= DECK_RULES.maxCopies ? "disabled" : ""}>+</button>`;
        row.querySelector('[data-d="-1"]').onclick = () => removeCard(id);
        row.querySelector('[data-d="1"]').onclick = () => addCard(id);
        peekable(row.querySelector(".dk-name"), card);
        list.appendChild(row);
      }
    }

    $("dk-checks").innerHTML = validateDeck(d, catalog).map((c) =>
      `<li class="chk-${c.level}"><span class="chk-icon">${{ ok: "✓", warn: "!", error: "✕" }[c.level]}</span>${esc(c.msg)}</li>`).join("");
  }

  function renderCatalog() {
    if (!catalog) return;
    const d = current();
    const q = normName($("cat-search").value);
    const type = $("cat-type").value, year = $("cat-year").value, sort = $("cat-sort").value;
    const cards = Object.values(catalog).filter((c) =>
      (!type || c.type === type) && (!year || c.year === year)
      && (!q || normName(`${c.name} ${c.when} ${c.text}`).includes(q)));
    cards.sort(sort === "year"
      ? (a, b) => a.year.localeCompare(b.year) || a.name.localeCompare(b.name)
      : (a, b) => a.name.localeCompare(b.name) || a.year.localeCompare(b.year));

    const total = Object.keys(catalog).length;
    $("cat-count").textContent = `${cards.length} of ${total} cards${d ? " · press + to add" : " · start a deck to add cards"}`;

    const copies = d ? deckCopies(d, catalog) : {};
    const grid = $("cat-grid");
    grid.innerHTML = "";
    for (const c of cards) {
      const inDeck = d?.cards[c.id] || 0;
      const nameTotal = copies[c.baseName]?.total || 0;
      const full = nameTotal >= DECK_RULES.maxCopies;
      const tile = document.createElement("div");
      tile.className = `cat-tile sface-${c.type.toLowerCase()}` + (inDeck ? " in-roster" : "");
      tile.innerHTML = `
        <div class="ct-info">
          <span class="lt-name">${esc(c.name)} <small>${esc(yearTag(c))}</small></span>
          <span class="ct-when">${esc(c.when)}</span>
          <span class="ct-text">${c.text ? esc(c.text) : "<em>effect not transcribed yet</em>"}</span>
        </div>
        <div class="lt-actions">
          ${inDeck ? `<span class="ct-count" title="In this deck">${inDeck}</span>` : ""}
          ${d ? `<button class="lt-add" title="${full ? `Already ${DECK_RULES.maxCopies} copies of ${esc(c.name)}` : "Add to deck"}" ${full ? "disabled" : ""}>+</button>` : ""}
        </div>`;
      peekable(tile.querySelector(".ct-info"), c);
      const add = tile.querySelector(".lt-add");
      if (add) add.onclick = () => addCard(c.id);
      grid.appendChild(tile);
    }
  }

  return { show };
})();
