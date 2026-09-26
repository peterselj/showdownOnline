// Card building through our card server (worker/ — a Cloudflare Worker).
// The server calls Showdown Bot for us, and keeps a permanent, shrunken copy
// of every card image (Showdown Bot deletes its own after a few minutes).

const IMG_MAX_WIDTH = 700;

async function cardServer(path, opts = {}) {
  if (location.protocol === "file:") {
    throw new Error("Cards can't be built from a page opened as a file. Run a local server (see README → Running locally) or use the live site.");
  }
  let res;
  try {
    res = await fetch(window.CARD_SERVER + path, opts);
  } catch {
    throw new Error("Can't reach the card server — check your connection and try again");
  }
  const data = res.headers.get("Content-Type")?.includes("application/json") ? await res.json() : null;
  if (!res.ok) throw new Error(data?.error || `Card server error ${res.status}`);
  return data;
}

// Shrink the full-size card PNG (~3.6 MB) to a ~100 KB WebP (JPEG where the
// browser can't encode WebP).
async function shrinkImage(blob) {
  const bmp = await createImageBitmap(blob);
  const scale = Math.min(1, IMG_MAX_WIDTH / bmp.width);
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bmp.width * scale);
  canvas.height = Math.round(bmp.height * scale);
  canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
  const encode = (type, q) => new Promise((res) => canvas.toBlob(res, type, q));
  const webp = await encode("image/webp", 0.85);
  return webp && webp.type === "image/webp" ? webp : encode("image/jpeg", 0.85);
}

// Build (or fetch the already-built) card. Returns a library card:
// {id, name, year, set, points, command, outs, isPitcher, role, positions,
//  ip, speed, hand, team, imgUrl, builtAt}.
// onStatus(msg) is called with progress updates (a new card takes ~30s).
async function buildPlayerCard(name, year, set, onStatus) {
  onStatus("Building card on Showdown Bot (can take ~30s)…");
  const res = await cardServer("/build", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, year: String(year), set: String(set) }),
  });

  let card = res.card;
  if (!card) {
    const { slug, token } = res.pending;
    onStatus("Saving card image…");
    const png = await fetch(`${window.CARD_SERVER}/source?t=${encodeURIComponent(token)}`);
    if (!png.ok) throw new Error((await png.json().catch(() => ({}))).error || "Couldn't download the card image");
    const small = await shrinkImage(await png.blob());
    card = (await cardServer(`/cards/${slug}`, {
      method: "PUT",
      headers: { "Content-Type": small.type, "X-Card-Token": token },
      body: small,
    })).card;
  }
  const { slug, ...rest } = card;
  return { ...rest, id: cardKey(card.name, card.year, card.set), builtAt: Date.now() };
}

window.buildPlayerCard = buildPlayerCard;
