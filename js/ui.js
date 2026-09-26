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

function hidePeek() { $("peek").classList.add("hidden"); }

function showZoom(imgUrl) {
  $("zoom-img").src = imgUrl;
  $("zoom").classList.remove("hidden");
}
