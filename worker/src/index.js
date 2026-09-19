// Tiny API behind the site. Everything is gated by one shared token because
// this is a private, personal search.
//
//   GET  /api/data            latest scan results (written by the GitHub Action)
//   PUT  /api/data            store scan results
//   GET  /api/state           review state for every listing {id: {status, note, address, updated}}
//   PATCH /api/state/:id      merge fields into one listing's review state
//   GET  /api/overrides       CSV of `source_id,address` for the Action to feed back into the scan
//
// State is one KV value ("state") holding a JSON object. It's a few hundred
// listings at most, so a single document is simpler than a key per listing.

const JSON_HEADERS = { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" };

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function authorized(request, env) {
  const header = request.headers.get("authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  return env.API_TOKEN && token && timingSafeEqual(token, env.API_TOKEN);
}

async function readState(env) {
  return (await env.STATE.get("state", "json")) || {};
}

function csvCell(value) {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

async function handleApi(request, env, path) {
  if (!authorized(request, env)) return json({ error: "unauthorized" }, 401);

  if (path === "/api/data") {
    if (request.method === "GET") {
      const data = await env.STATE.get("data");
      return data
        ? new Response(data, { headers: JSON_HEADERS })
        : json({ error: "no scan results yet" }, 404);
    }
    if (request.method === "PUT") {
      const body = await request.text();
      JSON.parse(body); // reject anything that isn't JSON before storing it
      await env.STATE.put("data", body);
      return json({ ok: true });
    }
  }

  if (path === "/api/state" && request.method === "GET") {
    return json(await readState(env));
  }

  const stateMatch = path.match(/^\/api\/state\/([A-Za-z0-9_-]{1,64})$/);
  if (stateMatch && request.method === "PATCH") {
    const id = stateMatch[1];
    const patch = await request.json();
    const state = await readState(env);
    const entry = { ...(state[id] || {}) };
    for (const key of ["status", "note", "address"]) {
      if (key in patch) {
        const value = patch[key];
        if (value === null || value === "") delete entry[key];
        else if (typeof value === "string" && value.length <= 2000) entry[key] = value;
      }
    }
    entry.updated = new Date().toISOString();
    if (Object.keys(entry).length === 1) delete state[id];
    else state[id] = entry;
    await env.STATE.put("state", JSON.stringify(state));
    return json(state[id] || {});
  }

  if (path === "/api/overrides" && request.method === "GET") {
    const state = await readState(env);
    const lines = ["source_id,address"];
    for (const [id, entry] of Object.entries(state)) {
      if (entry.address) lines.push(`${id},${csvCell(entry.address)}`);
    }
    return new Response(lines.join("\n") + "\n", {
      headers: { "content-type": "text/csv; charset=utf-8", "cache-control": "no-store" },
    });
  }

  return json({ error: "not found" }, 404);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/")) {
      try {
        return await handleApi(request, env, url.pathname);
      } catch (err) {
        return json({ error: err.message || "bad request" }, 400);
      }
    }
    return env.ASSETS.fetch(request);
  },
};
