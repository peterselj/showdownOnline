// Showdown Bot API (https://www.showdownbot.com) — card generation.
// Their API has no CORS headers, so JSON calls go through the CORS proxy.
// Generated card images are plain <img> hotlinks and need no proxy.

const SB_BASE = "https://www.showdownbot.com";

async function sbPost(path, body) {
  const res = await fetch(window.CORS_PROXY(SB_BASE + path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Showdown Bot ${path} failed: ${res.status}`);
  return res.json();
}

// Build a card and its image. Returns {name, year, set, imgUrl, points, chart}.
// onStatus(msg) is called with progress updates (the image render is slow).
async function buildPlayerCard(name, year, set, onStatus) {
  onStatus("Fetching stats & building card…");
  const built = await sbPost("/api/build_custom_card", { name, year, set });
  if (!built.card) throw new Error(built.error_for_user || built.error || "No card returned");
  const card = built.card;

  onStatus("Rendering card image (can take ~30s)…");
  const img = await sbPost("/api/build_image_for_card", { card });
  const ic = img.card || img;
  const folder = ic.image?.output_folder_path || ic.output_folder_path;
  const file = ic.image?.output_file_name || ic.output_file_name;
  if (!folder || !file) throw new Error("Image built but no file path returned");

  return {
    name: card.name,
    year: String(card.year),
    set: String(card.set),
    points: card.points,
    command: card.chart?.command,
    outs: card.chart?.outs,
    isPitcher: !!card.chart?.is_pitcher,
    imgUrl: `${SB_BASE}/${folder.replace(/^\/+|\/+$/g, "")}/${encodeURIComponent(file)}`,
  };
}

window.buildPlayerCard = buildPlayerCard;
