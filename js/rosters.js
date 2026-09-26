// Rosters tab: the card library (every card you've built, saved in this
// browser) and the roster editor with a live budget and rule checks.

const RosterBuilder = (() => {
  const LS_CURRENT = "showdown-current-roster";
  let currentId = null;
  let wired = false;

  const current = () => (currentId && Rosters.get(currentId)) || null;

  function show() {
    if (!wired) { wire(); wired = true; }
    if (!current()) currentId = localStorage.getItem(LS_CURRENT);
    if (!current()) currentId = Rosters.all()[0]?.id || null;
    renderAll();
  }

  function select(id) {
    currentId = id;
    try { localStorage.setItem(LS_CURRENT, id || ""); } catch { /* per-viewer convenience only */ }
    renderAll();
  }

  // Apply a change to the open roster, save it, and redraw.
  function edit(fn) {
    const r = current();
    if (!r) return;
    fn(r);
    Rosters.save(r);
    renderAll();
  }

  // -------------------------------------------------------------------------
  // Wiring
  // -------------------------------------------------------------------------
  function wire() {
    $("lib-build").onsubmit = (e) => {
      e.preventDefault();
      const name = $("lb-name").value.trim(), year = $("lb-year").value.trim();
      if (!name || !year) return;
      enqueueBuild(name, year, $("lb-set").value);
      $("lb-name").value = "";
      $("lb-name").focus();
    };
    for (const id of ["lib-search", "lib-filter", "lib-sort"]) $(id).addEventListener("input", renderLibrary);

    $("rb-first").onclick = createRoster;
    $("roster-name").addEventListener("input", (e) => {
      const r = current();
      if (!r) return;
      r.name = e.target.value.slice(0, 30) || "Untitled";
      Rosters.save(r);
      renderTabs();
    });
    $("rb-dup").onclick = () => {
      const r = current();
      if (!r || Rosters.all().length >= RULES.maxRosters) return;
      const copy = JSON.parse(JSON.stringify(r));
      copy.id = "r" + Date.now().toString(36);
      copy.name = (r.name + " copy").slice(0, 30);
      Rosters.save(copy);
      select(copy.id);
    };
    $("rb-del").onclick = () => {
      const r = current();
      if (!r || !confirm(`Delete roster "${r.name}"? The cards stay in your library.`)) return;
      Rosters.remove(r.id);
      select(Rosters.all()[0]?.id || null);
    };

    // list sections accept drops at the end; rows inside insert before themselves
    for (const list of ROSTER_LISTS) dropTarget($(`rb-${list}`), () => ({ list }));
    // dropping a roster card back on the library removes it from the roster
    dropTarget($("lib-panel"), null);
  }

  function dropTarget(el, targetFn) {
    el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("drag-over"); });
    el.addEventListener("dragleave", (e) => { if (!el.contains(e.relatedTarget)) el.classList.remove("drag-over"); });
    el.addEventListener("drop", (e) => {
      e.preventDefault();
      e.stopPropagation();
      el.classList.remove("drag-over");
      const cardId = e.dataTransfer.getData("text/plain");
      if (!cardId || !Library.get(cardId)) return;
      if (!targetFn) { edit((r) => rosterDetach(r, cardId)); return; }
      edit((r) => rosterPlace(r, cardId, targetFn()));
    });
  }

  function draggable(el, cardId) {
    el.draggable = true;
    el.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", cardId);
      e.dataTransfer.effectAllowed = "move";
      el.classList.add("dragging");
      hidePeek();
    });
    el.addEventListener("dragend", () => el.classList.remove("dragging"));
  }

  function createRoster() {
    const n = Rosters.all().length;
    if (n >= RULES.maxRosters) return;
    const r = newRoster(`Roster ${n + 1}`);
    Rosters.save(r);
    select(r.id);
    $("roster-name").select();
  }

  // -------------------------------------------------------------------------
  // Build queue: cards take ~30s each, so builds run one at a time in the
  // background while you keep editing.
  // -------------------------------------------------------------------------
  const queue = [];
  let building = false;

  // repair: rebuild a library card whose image has expired (don't add it to the roster)
  function enqueueBuild(name, year, set, repair = false) {
    const existing = Library.find(name, year, set);
    if (existing && !repair) {
      const job = { name, year, set, status: "done", msg: `${existing.name} ${existing.year} is already in your library` };
      queue.push(job);
      fadeOut(job);
      renderQueue();
      return;
    }
    if (queue.some((j) => cardKey(j.name, j.year, j.set) === cardKey(name, year, set) && j.status !== "done" && j.status !== "error")) return;
    queue.push({ name, year, set, repair, status: "queued", msg: "Waiting…" });
    renderQueue();
    pump();
  }

  async function pump() {
    if (building) return;
    const job = queue.find((j) => j.status === "queued");
    if (!job) return;
    building = true;
    job.status = "building";
    renderQueue();
    try {
      const card = await buildPlayerCard(job.name, job.year, job.set, (msg) => { job.msg = msg; renderQueue(); });
      Library.put(card);
      job.status = "done";
      job.msg = `${card.name} ${card.year} — ${card.points} pts`;
      fadeOut(job);
      if (current() && !job.repair) edit((r) => rosterQuickAdd(r, card)); else renderAll();
    } catch (err) {
      job.status = "error";
      job.msg = err.message;
    }
    building = false;
    renderQueue();
    pump();
  }

  // Finished builds clear themselves after a few seconds; failures stay until dismissed.
  function fadeOut(job) {
    setTimeout(() => {
      const i = queue.indexOf(job);
      if (i >= 0) { queue.splice(i, 1); renderQueue(); }
    }, 8000);
  }

  function renderQueue() {
    const ul = $("build-queue");
    ul.innerHTML = queue.map((j, i) => `
      <li class="bq-${j.status}">
        <span class="bq-name">${esc(j.name)} ${esc(j.year)}</span>
        <span class="bq-msg">${esc(j.msg)}</span>
        ${j.status === "done" || j.status === "error" ? `<button class="bq-x" data-i="${i}" title="Dismiss">×</button>` : ""}
      </li>`).join("");
    ul.querySelectorAll(".bq-x").forEach((b) => { b.onclick = () => { queue.splice(+b.dataset.i, 1); renderQueue(); }; });
  }

  // -------------------------------------------------------------------------
  // Rendering
  // -------------------------------------------------------------------------
  function renderAll() {
    renderTabs();
    renderEditor();
    renderLibrary();
  }

  function renderTabs() {
    const lib = Library.all();
    const list = Rosters.all();
    const el = $("roster-tabs");
    el.innerHTML = list.map((r) => `
      <button class="rt ${r.id === currentId ? "active" : ""}" data-id="${esc(r.id)}">
        <span class="rt-dot ${rosterIsLegal(r, lib) ? "ok" : "bad"}"></span>${esc(r.name)}
      </button>`).join("")
      + (!list.length ? ""
        : list.length < RULES.maxRosters
        ? `<button class="rt rt-new" id="rt-new">+ New roster</button>`
        : `<span class="rt-max">${RULES.maxRosters} rosters max</span>`);
    el.querySelectorAll(".rt[data-id]").forEach((b) => { b.onclick = () => select(b.dataset.id); });
    if ($("rt-new")) $("rt-new").onclick = createRoster;
  }

  function renderEditor() {
    const r = current();
    $("rb-empty").classList.toggle("hidden", !!r);
    $("rb-body").classList.toggle("hidden", !r);
    if (!r) return;
    const lib = Library.all();

    if (document.activeElement !== $("roster-name")) $("roster-name").value = r.name;
    $("rb-dup").disabled = Rosters.all().length >= RULES.maxRosters;

    renderBudget(r, lib);
    renderLineup(r, lib);
    for (const list of ROSTER_LISTS) {
      const box = $(`rb-${list}`);
      box.innerHTML = "";
      r[list].forEach((id, i) => {
        const row = cardRow(lib[id], id);
        dropTarget(row, () => ({ list, i }));
        box.appendChild(row);
      });
      if (!r[list].length) box.innerHTML = `<p class="rb-placeholder">${list === "bench" ? "Drop hitters here" : "Drop pitchers here"}</p>`;
    }
    $("n-bench").textContent = r.bench.length;
    $("n-rotation").textContent = `${r.rotation.length} / ${RULES.minStarters}–${RULES.maxStarters}`;
    $("n-bullpen").textContent = r.bullpen.length;

    $("rb-checks").innerHTML = validateRoster(r, lib).map((c) =>
      `<li class="chk-${c.level}"><span class="chk-icon">${{ ok: "✓", warn: "!", error: "✕" }[c.level]}</span>${esc(c.msg)}</li>`).join("");
  }

  function renderBudget(r, lib) {
    const p = rosterPoints(r, lib);
    const cap = RULES.pointCap;
    const scale = Math.max(cap, p.total);
    const pct = (v) => (100 * v / scale).toFixed(2) + "%";
    const diff = p.total - cap;
    const status = diff > 0 ? `<span class="bud-over">${diff.toLocaleString()} over</span>`
      : diff < 0 ? `<span class="bud-under">${(-diff).toLocaleString()} left</span>`
      : `<span class="bud-ok">right on ${cap.toLocaleString()}</span>`;
    $("budget").innerHTML = `
      <div class="bud-top"><b>${p.total.toLocaleString()}</b> / ${cap.toLocaleString()} pts · ${status}
        <span class="bud-count">${rosterCount(r)} / ${RULES.rosterSize} players</span></div>
      <div class="bud-bar">
        <span class="seg seg-lineup" style="width:${pct(p.lineup)}"></span><span class="seg seg-bench" style="width:${pct(p.bench)}"></span><span class="seg seg-pitch" style="width:${pct(p.pitching)}"></span>
        <span class="bud-cap" style="left:${pct(cap)}"></span>
      </div>
      <div class="bud-legend">
        <span><i class="seg-lineup"></i>Lineup ${p.lineup.toLocaleString()}</span>
        <span><i class="seg-bench"></i>Bench ${p.bench.toLocaleString()}</span>
        <span><i class="seg-pitch"></i>Pitching ${p.pitching.toLocaleString()}</span>
      </div>`;
    $("budget").className = "budget" + (diff > 0 ? " over" : "");
  }

  function renderLineup(r, lib) {
    const ol = $("rb-lineup");
    ol.innerHTML = "";
    r.lineup.forEach((slot, i) => {
      const card = slot.cardId ? lib[slot.cardId] : null;
      const li = document.createElement("li");
      li.className = "rb-lslot";
      const elig = eligiblePositions(card);
      const taken = new Set(r.lineup.filter((s, j) => j !== i && s.cardId).map((s) => s.pos));
      const opts = [`<option value="">Pos</option>`].concat(LINEUP_POSITIONS.map((p) => {
        const off = card && !elig.includes(p);
        return `<option value="${p}" ${slot.pos === p ? "selected" : ""}>${p}${off ? " (out of pos)" : ""}${taken.has(p) ? " •" : ""}</option>`;
      }));
      li.innerHTML = `<span class="rb-order">${i + 1}</span>
        <select class="rb-pos ${card && slot.pos && !elig.includes(slot.pos) ? "off" : ""}" ${card ? "" : "disabled"}>${opts.join("")}</select>
        <div class="rb-slot"></div>
        <span class="rb-move">
          <button title="Move up" ${i === 0 ? "disabled" : ""} data-d="-1">▲</button>
          <button title="Move down" ${i === r.lineup.length - 1 ? "disabled" : ""} data-d="1">▼</button>
        </span>`;
      const slotEl = li.querySelector(".rb-slot");
      if (card) slotEl.appendChild(cardRow(card, slot.cardId));
      else slotEl.innerHTML = `<p class="rb-placeholder">Drop a hitter</p>`;
      dropTarget(li, () => ({ list: "lineup", i }));

      li.querySelector(".rb-pos").onchange = (e) => edit((rr) => { rr.lineup[i].pos = e.target.value; });
      li.querySelectorAll(".rb-move button").forEach((b) => {
        b.onclick = () => edit((rr) => {
          const j = i + Number(b.dataset.d);
          [rr.lineup[i], rr.lineup[j]] = [rr.lineup[j], rr.lineup[i]];
        });
      });
      ol.appendChild(li);
    });
  }

  // One roster entry: thumbnail, name, positions, points, remove button.
  function cardRow(card, cardId) {
    const row = document.createElement("div");
    row.className = "rb-row";
    if (!card) {
      row.innerHTML = `<span class="rb-missing">Missing card</span><button class="rb-x" title="Remove">×</button>`;
    } else {
      row.innerHTML = `
        <img class="rb-thumb" src="${esc(card.imgUrl)}" alt="" loading="lazy">
        <span class="rb-info"><span class="rb-name">${esc(card.name)} <small>’${esc(String(card.year).slice(-2))}</small></span>
          <span class="rb-meta">${esc(positionLabel(card))}</span></span>
        <span class="rb-pts">${card.points}</span>
        <button class="rb-x" title="Remove from roster">×</button>`;
      const thumb = row.querySelector(".rb-thumb");
      thumb.addEventListener("mouseenter", () => showPeek(thumb, card.imgUrl));
      thumb.addEventListener("mouseleave", hidePeek);
      thumb.addEventListener("dblclick", () => showZoom(card.imgUrl));
      draggable(row, cardId);
    }
    row.querySelector(".rb-x").onclick = () => edit((r) => rosterDetach(r, cardId));
    return row;
  }

  function renderLibrary() {
    const lib = Library.all();
    const r = current();
    const q = normName($("lib-search").value);
    const f = $("lib-filter").value;
    const sort = $("lib-sort").value;
    let cards = Object.values(lib).filter((c) => {
      if (q && !normName(`${c.name} ${c.year} ${c.team || ""}`).includes(q)) return false;
      if (!f) return true;
      if (f === "hitters") return !c.isPitcher;
      if (f === "SP" || f === "RP") return c.isPitcher && c.role === f;
      return eligiblePositions(c).includes(f);
    });
    cards.sort(sort === "name" ? (a, b) => a.name.localeCompare(b.name)
      : sort === "recent" ? (a, b) => (b.builtAt || 0) - (a.builtAt || 0)
      : (a, b) => b.points - a.points);

    const total = Object.keys(lib).length;
    $("lib-count").textContent = total
      ? `${cards.length} of ${total} cards${r ? " · drag onto the roster or press +" : ""}`
      : "Your library is empty. Build a card above — it's saved in this browser.";

    // Cards built before the card server have Showdown Bot image links, which expire.
    const stale = Object.values(lib).filter((c) => !String(c.imgUrl).startsWith(window.CARD_SERVER));
    const repair = $("lib-repair");
    repair.classList.toggle("hidden", !stale.length);
    repair.textContent = `Repair ${stale.length} expired card image${stale.length === 1 ? "" : "s"}`;
    repair.onclick = () => stale.forEach((c) => enqueueBuild(c.name, c.year, c.set, true));

    const grid = $("lib-grid");
    grid.innerHTML = "";
    for (const c of cards) {
      const inRoster = r && rosterLocate(r, c.id);
      const tile = document.createElement("div");
      tile.className = "lib-tile" + (inRoster ? " in-roster" : "");
      tile.innerHTML = `
        <img src="${esc(c.imgUrl)}" alt="${esc(c.name)}" loading="lazy">
        <div class="lt-info">
          <span class="lt-name">${esc(c.name)}</span>
          <span class="lt-meta">${esc(c.year)} · ${esc(positionLabel(c))}</span>
          <span class="lt-pts">${c.points} pts</span>
        </div>
        <div class="lt-actions">
          ${r ? (inRoster ? `<span class="lt-in" title="On this roster">✓</span>` : `<button class="lt-add" title="Add to roster">+</button>`) : ""}
          <button class="lt-del" title="Delete from library">🗑</button>
        </div>`;
      const img = tile.querySelector("img");
      img.addEventListener("mouseenter", () => showPeek(img, c.imgUrl));
      img.addEventListener("mouseleave", hidePeek);
      img.addEventListener("dblclick", () => showZoom(c.imgUrl));
      draggable(tile, c.id);
      const add = tile.querySelector(".lt-add");
      if (add) add.onclick = () => edit((rr) => rosterQuickAdd(rr, c));
      tile.querySelector(".lt-del").onclick = () => {
        const used = Rosters.all().filter((rr) => rosterLocate(rr, c.id)).map((rr) => rr.name);
        const msg = used.length
          ? `Delete ${c.name} ${c.year}? It will also be removed from: ${used.join(", ")}.`
          : `Delete ${c.name} ${c.year} from your library?`;
        if (confirm(msg)) { Library.remove(c.id); renderAll(); }
      };
      grid.appendChild(tile);
    }
  }

  return { show, enqueueBuild };
})();
