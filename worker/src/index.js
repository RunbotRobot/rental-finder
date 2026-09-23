// Tiny API behind the site, gated by one of two shared tokens.
//
//   API_TOKEN (full access -- the site itself uses this):
//     GET  /api/data            latest scan results (written by the GitHub Action)
//     PUT  /api/data            store scan results
//     GET  /api/state           review state for every listing {id: {status, note, address, emailed, updated}}
//     PATCH /api/state/:id      merge fields into one listing's review state
//     GET  /api/overrides       CSV of `source_id,address` for the Action to feed back into the scan
//     GET  /api/emailed         JSON array of listing ids already emailed, for the Action's send gate
//     GET  /api/profile         read the applicant profile
//     PUT  /api/profile         save the applicant profile
//
//   AGENT_TOKEN (narrow, read-mostly -- for the Claude session that drafts
//   and sends outreach email; deliberately can't touch review state, the
//   full profile-editing endpoint, or the raw scan data, so holding it in a
//   chat session is a much smaller exposure than the full token would be):
//     GET  /api/agent/candidates   listings ready for outreach, plus the
//                                  profile (read-only, bundled in so the
//                                  agent never needs a second call)
//
//   Either token:
//     POST /api/emailed         body: array of ids to mark emailed just now
//
// State is one KV value ("state") holding a JSON object. It's a few hundred
// listings at most, so a single document is simpler than a key per listing.
// The profile is a second, separate KV value ("profile") -- unrelated to
// any one listing, so it doesn't belong in the state object.

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

// "full" | "agent" | null. Never both -- if a deployment ever set the two
// secrets to the same value, full access is what's granted, which is the
// safe direction for that misconfiguration to fail in.
function tokenScope(request, env) {
  const header = request.headers.get("authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!token) return null;
  if (env.API_TOKEN && timingSafeEqual(token, env.API_TOKEN)) return "full";
  if (env.AGENT_TOKEN && timingSafeEqual(token, env.AGENT_TOKEN)) return "agent";
  return null;
}

async function readState(env) {
  return (await env.STATE.get("state", "json")) || {};
}

function csvCell(value) {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

async function handleApi(request, env, path) {
  // Unauthenticated on purpose: says whether the secret reached the runtime
  // and how long it is, never what it is. Lets a mismatch be diagnosed
  // without a terminal.
  if (path === "/api/health" && request.method === "GET") {
    const token = env.API_TOKEN;
    return json({
      ok: true,
      token_configured: typeof token === "string" && token.length > 0,
      token_length: typeof token === "string" ? token.length : 0,
      token_has_whitespace: typeof token === "string" && /\s/.test(token),
    });
  }

  const scope = tokenScope(request, env);
  if (!scope) return json({ error: "unauthorized" }, 401);

  if (path === "/api/agent/candidates" && request.method === "GET") {
    const raw = await env.STATE.get("data", "json");
    if (!raw) return json({ error: "no scan results yet" }, 404);
    const state = await readState(env);
    const candidates = (raw.listings || []).filter(
      (l) => l.outreach_result === "ready to send" && !state[l.id]?.emailed
    );
    const profile = (await env.STATE.get("profile", "json")) || {};
    return json({ profile, candidates });
  }

  if (scope !== "full") {
    // Everything below here is full-token-only except /api/emailed POST,
    // handled inside its own block further down.
    if (!(path === "/api/emailed" && request.method === "POST")) {
      return json({ error: "unauthorized" }, 401);
    }
  }

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
    for (const key of ["status", "note", "address", "emailed"]) {
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

  if (path === "/api/emailed") {
    if (request.method === "GET") {
      const state = await readState(env);
      const ids = Object.entries(state)
        .filter(([, entry]) => entry.emailed)
        .map(([id]) => id);
      return json(ids);
    }
    if (request.method === "POST") {
      // The Action calls this once after a run with every id it just sent
      // to, so a later run's send gate treats them as already contacted.
      const ids = await request.json();
      if (!Array.isArray(ids) || !ids.every((id) => typeof id === "string" && id.length <= 64)) {
        return json({ error: "expected an array of id strings" }, 400);
      }
      const state = await readState(env);
      const now = new Date().toISOString();
      for (const id of ids) {
        state[id] = { ...(state[id] || {}), emailed: now, updated: now };
      }
      await env.STATE.put("state", JSON.stringify(state));
      return json({ ok: true, marked: ids.length });
    }
  }

  if (path === "/api/profile") {
    if (request.method === "GET") {
      return json((await env.STATE.get("profile", "json")) || {});
    }
    if (request.method === "PUT") {
      const body = await request.json();
      const allowed = ["name", "phone", "email", "move_in_date", "income_text", "employment_text", "disclosure_text"];
      const profile = {};
      for (const key of allowed) {
        if (typeof body[key] === "string" && body[key].length <= 4000) profile[key] = body[key];
      }
      await env.STATE.put("profile", JSON.stringify(profile));
      return json(profile);
    }
  }

  return json({ error: "not found" }, 404);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    // Tolerate a WORKER_URL with a trailing slash ("//api/...") and trailing slashes generally.
    const path = url.pathname.replace(/\/{2,}/g, "/").replace(/\/+$/, "") || "/";
    if (path.startsWith("/api/")) {
      try {
        return await handleApi(request, env, path);
      } catch (err) {
        return json({ error: err.message || "bad request" }, 400);
      }
    }
    return env.ASSETS.fetch(request);
  },
};
