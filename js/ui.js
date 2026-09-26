// Small DOM helpers shared by the Play and Rosters tabs.

const $ = (id) => document.getElementById(id);

const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------------------------------------------------------------------------
// Hover magnifier
// ---------------------------------------------------------------------------
function showPeek(anchorEl, imgUrl) {
  const peek = $("peek");
  $("peek-img").src = imgUrl;
  peek.classList.remove("hidden");
  const r = anchorEl.getBoundingClientRect();
  const pw = Math.min(340, window.innerWidth * 0.38);
  const ph = pw * 1.4;
  // prefer to the right of the card; flip left if it would overflow
  let x = r.right + 12;
  if (x + pw > window.innerWidth - 8) x = r.left - pw - 12;
  let y = Math.min(Math.max(8, r.top + r.height / 2 - ph / 2), window.innerHeight - ph - 8);
  peek.style.left = Math.max(8, x) + "px";
  peek.style.top = y + "px";
}

function hidePeek() {
  $("peek").classList.add("hidden");
  $("peek-face").classList.add("hidden");
}

// Magnifier for a drawn strategy card (no image to show).
function showPeekFace(anchorEl, card) {
  const peek = $("peek-face");
  peek.innerHTML = strategyFaceHTML(card, "big");
  peek.classList.remove("hidden");
  const r = anchorEl.getBoundingClientRect();
  const pw = peek.offsetWidth, ph = peek.offsetHeight;
  let x = r.right + 12;
  if (x + pw > window.innerWidth - 8) x = r.left - pw - 12;
  const y = Math.min(Math.max(8, r.top + r.height / 2 - ph / 2), window.innerHeight - ph - 8);
  peek.style.left = Math.max(8, x) + "px";
  peek.style.top = y + "px";
}

// A strategy card drawn in HTML, styled after the printed cards:
// type-colored frame, name, when to play, effect, type + year/set/number.
function strategyFaceHTML(card, size = "") {
  const type = (card.type || "").toLowerCase();
  const text = card.text
    ? esc(card.text)
    : `<em class="sf-missing">Effect text not transcribed yet</em>`;
  return `<div class="sface sface-${type} ${size}">
    <div class="sf-name">${esc(card.name)}</div>
    <div class="sf-when">${esc(card.when)}</div>
    <div class="sf-text">${text}</div>
    <div class="sf-foot"><span class="sf-type">${esc(card.type)}</span>
      <span class="sf-set">${esc(yearTag(card))}${card.set ? " " + esc(card.set) : ""}${card.number ? " #" + esc(card.number) : ""}</span></div>
  </div>`;
}

function showZoom(imgUrl) {
  $("zoom-img").src = imgUrl;
  $("zoom").classList.remove("hidden");
}
