// Showdown card server (Cloudflare Worker).
//
// Showdown Bot's API has no CORS headers and deletes generated images after a
// few minutes, so this Worker:
//   1. builds cards on Showdown Bot on the browser's behalf (POST /build),
//   2. lets the browser download the fresh image (GET /source?t=...) so it can
//      shrink it to a ~100 KB WebP/JPEG,
//   3. stores that small image permanently in KV (PUT /cards/<slug>) and
//      serves it forever at GET /img/<slug>,
//   4. caches finished cards, so a card built once comes back instantly for
//      anyone (GET /cards/<slug>, and POST /build checks the cache first).
//
// Between steps 1 and 3 the unfinished card travels as a signed token, so the
// browser can't store arbitrary card data or images under a card's name.

const SB_BASE = "https://www.showdownbot.com";
const MAX_IMAGE_BYTES = 900 * 1024;
const TOKEN_TTL_MS = 30 * 60 * 1000;
const IMAGE_TYPES = ["image/webp", "image/jpeg"];

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const cors = corsHeaders(origin, env);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

    const url = new URL(request.url);
    const path = url.pathname;
    try {
      // Images are plain <img> loads: no Origin header, so they're always served.
      if (request.method === "GET" && path.startsWith("/img/")) return await serveImage(env, path.slice(5));

      if (!isAllowedOrigin(origin, env)) return json({ error: "Origin not allowed" }, 403, cors);

      if (request.method === "POST" && path === "/build") return await build(request, env, cors);
      if (request.method === "GET" && path === "/source") return await source(url, env, cors);
      if (request.method === "GET" && path.startsWith("/cards/")) return await getCard(env, path.slice(7), cors);
      if (request.method === "PUT" && path.startsWith("/cards/")) return await finish(request, env, path.slice(7), cors);
      return json({ error: "Not found" }, 404, cors);
    } catch (err) {
      return json({ error: err.message || String(err) }, err.status || 500, cors);
    }
  },
};

// ---------------------------------------------------------------------------
// Routes
// ---------------------------------------------------------------------------
async function build(request, env, cors) {
  const { name, year, set } = await request.json();
  if (!name || !year || !["2004", "2005"].includes(String(set)) || String(name).length > 60 || String(year).length > 12) {
    return json({ error: "Need a player name, a season year, and set 2004 or 2005" }, 400, cors);
  }
  const cached = await lookup(env, cardSlug(name, year, set));
  if (cached) return json({ card: cached, cached: true }, 200, cors);

  const built = await sbPost("/api/build_custom_card", { name, year: String(year), set: String(set) });
  if (!built.card) {
    return json({ error: built.error_for_user || built.error || "Showdown Bot couldn't find that player/season" }, 422, cors);
  }
  const card = libraryCard(built.card);
  // A different spelling (accents, "Jr.") may already be cached under the canonical name.
  const canonical = await lookup(env, card.slug);
  if (canonical) {
    await env.CARDS.put(aliasKey(cardSlug(name, year, set)), card.slug);
    return json({ card: canonical, cached: true }, 200, cors);
  }

  const img = await sbPost("/api/build_image_for_card", { card: built.card });
  const ic = img.card || img;
  const folder = ic.image?.output_folder_path || ic.output_folder_path;
  const file = ic.image?.output_file_name || ic.output_file_name;
  if (!folder || !file) throw httpError(502, "Showdown Bot built the card but returned no image");

  const sourcePath = `${folder.replace(/^\/+|\/+$/g, "")}/${file}`;
  const requested = cardSlug(name, year, set);
  const token = await sign(env, { card, sourcePath, requested, exp: Date.now() + TOKEN_TTL_MS });
  return json({ pending: { slug: card.slug, token } }, 200, cors);
}

// Stream the freshly built full-size PNG to the browser for resizing.
async function source(url, env, cors) {
  const t = await verify(env, url.searchParams.get("t") || "");
  const path = t.sourcePath.split("/").map(encodeURIComponent).join("/");
  const res = await withRetry(() => fetch(`${SB_BASE}/${path}`), "image download");
  if (!res.ok) throw httpError(502, `Showdown Bot image expired or missing (${res.status}) — try building again`);
  return new Response(res.body, { headers: { ...cors, "Content-Type": res.headers.get("Content-Type") || "image/png" } });
}

// Store the shrunken image and the finished card.
async function finish(request, env, slug, cors) {
  const t = await verify(env, request.headers.get("X-Card-Token") || "");
  if (t.card.slug !== slug) throw httpError(400, "Token is for a different card");
  const type = (request.headers.get("Content-Type") || "").split(";")[0];
  if (!IMAGE_TYPES.includes(type)) throw httpError(415, "Image must be WebP or JPEG");
  const bytes = await request.arrayBuffer();
  if (!bytes.byteLength || bytes.byteLength > MAX_IMAGE_BYTES) throw httpError(413, "Image too large");

  await env.CARDS.put(imgKey(slug), bytes, { metadata: { type } });
  const card = { ...t.card, imgUrl: `${new URL(request.url).origin}/img/${slug}`, builtAt: Date.now() };
  await env.CARDS.put(cardKey(slug), JSON.stringify(card));
  if (t.requested && t.requested !== slug) await env.CARDS.put(aliasKey(t.requested), slug);
  return json({ card }, 200, cors);
}

async function getCard(env, slug, cors) {
  const card = await lookup(env, slug);
  return card ? json({ card }, 200, cors) : json({ error: "Not built yet" }, 404, cors);
}

async function serveImage(env, slug) {
  const { value, metadata } = await env.CARDS.getWithMetadata(imgKey(slug), { type: "arrayBuffer", cacheTtl: 86400 });
  if (!value) return new Response("Not found", { status: 404 });
  return new Response(value, {
    headers: {
      "Content-Type": metadata?.type || "image/webp",
      "Cache-Control": "public, max-age=31536000, immutable",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

// ---------------------------------------------------------------------------
// Cards
// ---------------------------------------------------------------------------
const normName = (name) => String(name || "")
  .normalize("NFD").replace(/[̀-ͯ]/g, "")
  .toLowerCase().replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ").trim();

// URL/KV-safe id: "derek-jeter-1999-2005"
const cardSlug = (name, year, set) =>
  `${normName(name)} ${String(year).trim()} ${set}`.replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

const cardKey = (slug) => `card:${slug}`;
const imgKey = (slug) => `img:${slug}`;
const aliasKey = (slug) => `alias:${slug}`;

async function lookup(env, slug) {
  const card = await env.CARDS.get(cardKey(slug), "json");
  if (card) return card;
  const target = await env.CARDS.get(aliasKey(slug));
  return target ? env.CARDS.get(cardKey(target), "json") : null;
}

// The fields the app keeps for a card (mirrors js/api.js).
function libraryCard(c) {
  const pd = c.positions_and_defense || {};
  const isPitcher = !!c.chart?.is_pitcher;
  const year = String(c.year), set = String(c.set);
  return {
    slug: cardSlug(c.name, year, set),
    name: c.name,
    year,
    set,
    points: Number(c.points) || 0,
    command: c.chart?.command ?? null,
    outs: c.chart?.outs ?? null,
    isPitcher,
    role: isPitcher ? ("STARTER" in pd || c.player_sub_type === "starting_pitcher" ? "SP" : "RP") : null,
    positions: isPitcher ? {} : pd,
    ip: c.ip ?? null,
    speed: c.speed?.speed ?? null,
    hand: c.hand || "",
    team: c.team || "",
  };
}

// ---------------------------------------------------------------------------
// Showdown Bot calls, with retries for its occasional hiccups
// ---------------------------------------------------------------------------
async function sbPost(path, body) {
  const res = await withRetry(() => fetch(SB_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "User-Agent": "showdown-online (github.com/peterselj/showdownOnline)" },
    body: JSON.stringify(body),
  }), path);
  if (!res.ok) throw httpError(502, `Showdown Bot ${path} failed (${res.status})`);
  return res.json();
}

async function withRetry(fn, label, tries = 3) {
  let last;
  for (let i = 0; i < tries; i++) {
    try {
      const res = await fn();
      if (res.status < 500 && res.status !== 429) return res;
      last = new Error(`${label}: HTTP ${res.status}`);
    } catch (err) {
      last = err;
    }
    await new Promise((r) => setTimeout(r, 1000 * 2 ** i));
  }
  throw httpError(502, `Showdown Bot is not responding (${last.message}) — try again in a minute`);
}

// ---------------------------------------------------------------------------
// Signed tokens (HMAC-SHA256 with the SIGNING_KEY secret)
// ---------------------------------------------------------------------------
const b64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64url = (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));

async function hmacKey(env) {
  if (!env.SIGNING_KEY) throw httpError(500, "Worker is missing its SIGNING_KEY secret");
  return crypto.subtle.importKey("raw", new TextEncoder().encode(env.SIGNING_KEY),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}

async function sign(env, payload) {
  const body = b64url(new TextEncoder().encode(JSON.stringify(payload)));
  const sig = await crypto.subtle.sign("HMAC", await hmacKey(env), new TextEncoder().encode(body));
  return `${body}.${b64url(sig)}`;
}

async function verify(env, token) {
  const [body, sig] = token.split(".");
  if (!body || !sig) throw httpError(400, "Missing card token");
  const key = await hmacKey(env);
  let ok = false, payload;
  try {
    ok = await crypto.subtle.verify("HMAC", key, unb64url(sig), new TextEncoder().encode(body));
    if (ok) payload = JSON.parse(new TextDecoder().decode(unb64url(body)));
  } catch { ok = false; }
  if (!ok) throw httpError(403, "Bad card token");
  if (Date.now() > payload.exp) throw httpError(410, "Card token expired — build the card again");
  return payload;
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------
function isAllowedOrigin(origin, env) {
  if (!origin) return false;
  if (/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) return true;
  return (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).includes(origin);
}

function corsHeaders(origin, env) {
  return isAllowedOrigin(origin, env)
    ? {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, X-Card-Token",
      "Access-Control-Max-Age": "86400",
      "Vary": "Origin",
    }
    : { "Vary": "Origin" };
}

const json = (data, status, headers) =>
  new Response(JSON.stringify(data), { status, headers: { ...headers, "Content-Type": "application/json" } });

function httpError(status, message) {
  const err = new Error(message);
  err.status = status;
  return err;
}
