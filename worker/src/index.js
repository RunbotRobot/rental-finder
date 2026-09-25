// Tiny API behind the site, gated by one of two shared tokens.
//
//   API_TOKEN (full access -- the site itself uses this):
//     GET  /api/data            latest scan results (written by the GitHub Action)
//     PUT  /api/data            store scan results
//     GET  /api/state           review state for every listing {id: {status, note, address, emailed, updated}}
//     PATCH /api/state/:id      merge fields into one listing's review state
//     GET  /api/overrides       CSV of `source_id,address,contact_name,contact_email,
//                               contact_source,contact_address` for the Action to feed
//                               back into the scan -- contact_* columns come from POST
//                               /api/agent/contact below, for a listing RentCast/
//                               Craigslist itself gave no contact for. contact_address
//                               (the listing's own address at the moment the contact was
//                               recorded) lets main.py's load_contact_overrides_by_address()
//                               apply the same contact to a LATER listing at the same
//                               address even if its id has changed -- see that function's
//                               docstring for why this matters specifically for Craigslist,
//                               whose posting ids churn on every repost.
//     GET  /api/emailed         JSON array of listing ids already emailed, for the Action's send gate
//     GET  /api/profile         read the applicant profile
//     PUT  /api/profile         save the applicant profile
//
//   AGENT_TOKEN (narrow, read-mostly -- for the Claude session that drafts
//   and sends outreach email; deliberately can't touch review state, the
//   full profile-editing endpoint, or the raw scan data, so holding it in a
//   chat session is a much smaller exposure than the full token would be.
//   One narrow, explicit exception: /api/agent/research-checked's dismiss
//   flag, which can only ever set status to "dismissed", never anything
//   else and never clear it -- see that endpoint below):
//     GET  /api/agent/candidates   listings ready for outreach, plus the
//                                  profile (read-only, bundled in so the
//                                  agent never needs a second call). Three
//                                  kinds, told apart by each entry's
//                                  `action` field:
//                                    "send"     -- RentCast, gate-eligible
//                                                  (has a contact_email, from
//                                                  RentCast or a prior
//                                                  research override); the
//                                                  agent drafts AND sends.
//                                    "draft"    -- Craigslist, eligible except
//                                                  for having no automatable
//                                                  contact; the agent drafts a
//                                                  reply-box-sized message and
//                                                  leaves it for you to paste
//                                                  into Craigslist's own reply
//                                                  flow yourself. Grouped by
//                                                  verified address first (the
//                                                  same unit is often posted
//                                                  under several titles), so
//                                                  each entry also carries
//                                                  `same_address_ids`: every
//                                                  posting the one draft should
//                                                  be saved to.
//                                    "research" -- either source, eligible
//                                                  except for having no
//                                                  VERIFIED contact: RentCast
//                                                  gave none at all, or the
//                                                  listing is Craigslist
//                                                  (which outreach.py blocks
//                                                  unconditionally unless
//                                                  contact_source is set --
//                                                  its own reply widget is
//                                                  never a real address, but a
//                                                  poster's own listing text,
//                                                  or the property/company
//                                                  behind it, sometimes has a
//                                                  real one). The agent
//                                                  researches a real contact
//                                                  itself and, if found with
//                                                  enough confidence, POSTs it
//                                                  to /api/agent/contact --
//                                                  see README's "Outreach and
//                                                  auto-send" for the exact
//                                                  confidence bar and the next
//                                                  steps (a scan run has to
//                                                  pick the override up before
//                                                  it becomes "send"-eligible;
//                                                  this endpoint only records
//                                                  the finding). Craigslist
//                                                  entries are grouped by
//                                                  verified address first,
//                                                  same as "draft" above and
//                                                  for the same reason, and
//                                                  stay a candidate even after
//                                                  a personal draft already
//                                                  exists -- a found direct
//                                                  email is strictly better
//                                                  than a reply-box draft.
//     GET  /api/data               read-only: the full raw scan results,
//                                  same as the site sees. For debugging --
//                                  the agent endpoints above already
//                                  summarize what a check-in needs; this is
//                                  for looking something up directly
//                                  instead of working around not having it.
//     GET  /api/state              read-only: review state for every
//                                  listing (status/note/address/emailed).
//                                  Same reasoning -- read access only, no
//                                  PATCH; can't touch your review state.
//
//   Either token:
//     POST /api/emailed         body: array of ids to mark emailed just now
//     POST /api/agent/draft     body: {id, subject, body}. Saves a
//                               personally-written draft for one listing,
//                               for a "draft"-kind candidate above. Can only
//                               write draft_subject/draft_body/drafted_at --
//                               not status, note, address, or emailed, which
//                               stay full-token-only (or the site's own
//                               buttons) so this narrow token can't touch
//                               your review state.
//     POST /api/agent/contact   body: {id, contact_name?, contact_email,
//                               contact_source}. Records a personally-
//                               researched contact for a "research"-kind
//                               candidate above -- contact_source is
//                               required (a citation of how/where it was
//                               found; never a bare confidence score) so
//                               every write is auditable. Can only write
//                               contact_name/contact_email/contact_source --
//                               same narrow-field pattern as
//                               /api/agent/draft, and for the same reason.
//                               Doesn't touch outreach_result or make
//                               anything "ready to send" by itself -- that
//                               still only happens once a scan run applies
//                               it as a contact override (see /api/overrides
//                               above and main.py's load_contact_overrides).
//     POST /api/agent/research-checked
//                               body: {id, note, dismiss?}. Records that a
//                               check-in researched this "research"-kind
//                               candidate and found nothing usable -- note is
//                               required (what was checked / why it came up
//                               empty), same auditability reasoning as
//                               contact_source. This is deliberately NOT a
//                               contact_email/contact_source write: it never
//                               makes anything eligible, and unlike a found
//                               contact it has no effect once a scan runs --
//                               it only removes the id from a future
//                               /api/agent/candidates response's "research"
//                               bucket (see below), so a later check-in
//                               doesn't repeat research that already came up
//                               empty. dismiss: true also sets status to
//                               "dismissed" -- the one, narrow exception to
//                               AGENT_TOKEN never touching review state,
//                               added because the owner asked for genuinely
//                               bad matches (senior housing, a garage/
//                               commercial unit, a room in a shared house,
//                               corporate short-term housing, ...) to
//                               disappear from the site's default view
//                               automatically, not just from future research.
//                               Can only write research_checked_at/
//                               research_note/status, and status can only
//                               ever be set to "dismissed" this way, never
//                               anything else and never cleared.
//
// Each listing's review state is its own KV key ("state:<id>"), not one
// shared JSON blob -- found the hard way, live, during a real outreach
// check-in: the original design held every listing's state in a single KV
// value, read-modified-written as a whole on every change. That's safe for
// one write at a time, but a check-in recording several contacts/drafts in
// a row (twenty-odd POSTs within a couple of minutes) raced on that shared
// key -- two requests reading the same snapshot, each writing back a
// version missing the other's change -- and silently lost 6 of 20 contact
// writes and 3 of 8 draft writes, despite every single request returning
// 200. Splitting to a key per listing means two different listings' writes
// never touch the same key, so that failure mode can't recur for the case
// that actually happened; two writes to the very same listing at the very
// same instant remain a narrower, accepted residual risk. See
// migrateLegacyStateIfNeeded() for the one-time move off the old shared key
// -- self-healing, runs at most once, safe to leave in indefinitely. The
// profile is a separate, single KV value ("profile") -- unrelated to any
// one listing, so it was never part of this problem.

const JSON_HEADERS = { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" };

// A listing id, wherever one is validated (a URL path segment above, or a
// JSON body field in the agent endpoints below). Craigslist's ids are
// opaque alphanumeric tokens, but RentCast's are address-derived slugs that
// legitimately contain commas (e.g. "12846-Se-40th-Ln,-Apt-8,-Bellevue,-WA-
// 98006") -- discovered live when the very first attempt to record a
// contact override for a RentCast listing 400'd, and confirmed to ALSO
// break the site's own star/dismiss/note/address-edit buttons for every
// RentCast listing via PATCH /api/state/:id, since that path segment used
// the same too-narrow character class. Comma/period/underscore covers every
// character actually seen in a real id; deliberately still an allowlist,
// not "anything," and long enough (100) for the longest real address seen
// (52) with real headroom.
const LISTING_ID_CHARS = "A-Za-z0-9,._-";
const LISTING_ID_RE = new RegExp(`^[${LISTING_ID_CHARS}]{1,100}$`);

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

function stateKeyFor(id) {
  return `state:${id}`;
}

async function readListingState(env, id) {
  return (await env.STATE.get(stateKeyFor(id), "json")) || {};
}

// Deletes the key entirely once nothing but "updated" is left (mirrors the
// old shared-blob code's "drop empty entries" behavior), otherwise writes
// the entry to its own key -- never touches any other listing's key, which
// is the whole point.
async function writeListingState(env, id, entry) {
  const meaningfulKeys = Object.keys(entry).filter((key) => key !== "updated");
  if (meaningfulKeys.length === 0) {
    await env.STATE.delete(stateKeyFor(id));
  } else {
    await env.STATE.put(stateKeyFor(id), JSON.stringify(entry));
  }
}

// One-time, self-healing migration off the old single-blob "state" key (see
// the module comment above for why). Runs lazily on any readAllState() call;
// a no-op every time after the first, since it only acts when no "state:"
// keys exist yet.
async function migrateLegacyStateIfNeeded(env) {
  const probe = await env.STATE.list({ prefix: "state:", limit: 1 });
  if (probe.keys.length > 0) return;
  const legacy = await env.STATE.get("state", "json");
  if (!legacy) return;
  for (const [id, entry] of Object.entries(legacy)) {
    await env.STATE.put(stateKeyFor(id), JSON.stringify(entry));
  }
}

async function readAllState(env) {
  await migrateLegacyStateIfNeeded(env);
  const result = {};
  let cursor;
  for (;;) {
    const page = await env.STATE.list({ prefix: "state:", cursor });
    // One get() per key, in parallel -- reading N different keys never
    // touches the same key twice, so this has none of the race exposure
    // that made concurrent WRITES to the old shared blob unsafe (see the
    // module comment above). Awaiting each get() sequentially here was a
    // real, measured regression from that same per-key migration: a live
    // check confirmed /api/state taking 10+ seconds cold with under 100
    // keys, one KV round trip at a time, on a page the owner loads on
    // their phone.
    const values = await Promise.all(page.keys.map((key) => env.STATE.get(key.name, "json")));
    page.keys.forEach((key, i) => {
      if (values[i]) result[key.name.slice("state:".length)] = values[i];
    });
    if (page.list_complete) break;
    cursor = page.cursor;
  }
  return result;
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

  // Craigslist has no scriptable send target, so a Craigslist listing can
  // never be auto-sent -- but it can still be personally drafted for you to
  // paste into Craigslist's own reply box. This is Craigslist's own limit on
  // that box, not this project's -- kept here as a single source of truth
  // and mirrored in public/app.js's character counter. Verify it still
  // matches what Craigslist actually shows you; it's an estimate, not
  // something this tool has ever gotten to measure against a real send.
  const CRAIGSLIST_BODY_LIMIT = 4000;

  if (path === "/api/agent/candidates" && request.method === "GET") {
    const raw = await env.STATE.get("data", "json");
    if (!raw) return json({ error: "no scan results yet" }, 404);
    const state = await readAllState(env);
    const sendReady = (raw.listings || [])
      .filter((l) => l.outreach_result === "ready to send" && !state[l.id]?.emailed)
      .map((l) => ({ ...l, action: "send" }));

    const draftEligible = (raw.listings || []).filter(
      (l) =>
        l.source === "craigslist" &&
        l.outreach_result === "no automatable contact (Craigslist has no real send address)" &&
        !state[l.id]?.emailed &&
        !state[l.id]?.draft_body &&
        // A verified contact override (see "research" below) has already
        // been recorded for this listing -- a direct email is on its way
        // once the next scan picks it up, so a reply-box draft would just
        // be wasted effort.
        !state[l.id]?.contact_email
    );
    // Large complexes commonly post the same unit under several different
    // titles -- verified live (the same address showing up 6+ times isn't
    // rare). Group by verified address so a check-in drafts ONE message per
    // address, not one per posting: same_address_ids carries every id that
    // draft should also be saved to (via repeated /api/agent/draft calls).
    const byAddress = new Map();
    for (const listing of draftEligible) {
      const key = listing.location || listing.id;
      if (!byAddress.has(key)) byAddress.set(key, []);
      byAddress.get(key).push(listing);
    }
    const draftReady = [...byAddress.values()].map((group) => ({
      ...group[0],
      action: "draft",
      same_address_ids: group.map((l) => l.id),
    }));

    // RentCast, otherwise gate-eligible, but RentCast itself gave no
    // contact_email at all -- "no contact email" is outreach.py's exact
    // _gate_reason() string for that case. A prior /api/agent/contact write
    // for this id doesn't remove it from this list by itself -- it only
    // takes effect once a scan run picks the override up and outreach_result
    // flips to "ready to send" -- so skip an id we already wrote a contact
    // for this run to avoid re-researching it before that scan has happened.
    // A prior /api/agent/research-checked write DOES remove it here, and for
    // good -- unlike a contact override, that marker has nothing waiting on a
    // future scan to take effect; it exists specifically so a listing a
    // check-in already dug through and found nothing for doesn't come back as
    // a candidate again next time (RentCast ids are address-derived and
    // stable, so the same listing really can resurface run after run).
    const rentcastResearch = (raw.listings || [])
      .filter(
        (l) =>
          l.source === "rentcast" &&
          l.outreach_result === "no contact email" &&
          !state[l.id]?.emailed &&
          !state[l.id]?.contact_email &&
          !state[l.id]?.research_checked_at
      )
      .map((l) => ({ ...l, action: "research" }));

    // Craigslist, otherwise gate-eligible except for having no VERIFIED
    // contact (outreach.py's _gate_reason() blocks Craigslist unconditionally
    // unless contact_source is set -- see its comment). Unlike the "draft"
    // bucket above, this stays a candidate even once a personal draft
    // already exists: drafting the reply-box message and researching a
    // direct email are independent, and a direct email found later is
    // strictly better than a reply-box draft, so it's always worth trying.
    // Same address-grouping as "draft", for the same reason (a poster's
    // direct contact info, once found for one unit, almost certainly covers
    // every other unit posted at that address).
    // Same research_checked_at exclusion as RentCast above, for the same
    // "don't ask a check-in to redo work already done" reason -- shorter-
    // lived here in practice, since a Craigslist posting's id doesn't survive
    // it expiring and being reposted, but still worth honoring for however
    // long the same posting stays live across more than one check-in.
    const craigslistResearchEligible = (raw.listings || []).filter(
      (l) =>
        l.source === "craigslist" &&
        l.outreach_result === "no automatable contact (Craigslist has no real send address)" &&
        !state[l.id]?.emailed &&
        !state[l.id]?.contact_email &&
        !state[l.id]?.research_checked_at
    );
    const byAddressForResearch = new Map();
    for (const listing of craigslistResearchEligible) {
      const key = listing.location || listing.id;
      if (!byAddressForResearch.has(key)) byAddressForResearch.set(key, []);
      byAddressForResearch.get(key).push(listing);
    }
    const craigslistResearch = [...byAddressForResearch.values()].map((group) => ({
      ...group[0],
      action: "research",
      same_address_ids: group.map((l) => l.id),
    }));

    const profile = (await env.STATE.get("profile", "json")) || {};
    return json({
      profile,
      craigslist_body_limit: CRAIGSLIST_BODY_LIMIT,
      candidates: [...sendReady, ...draftReady, ...rentcastResearch, ...craigslistResearch],
    });
  }

  if (path === "/api/agent/draft" && request.method === "POST") {
    const body = await request.json();
    const idMatch = typeof body.id === "string" && body.id.match(LISTING_ID_RE);
    if (!idMatch || typeof body.subject !== "string" || typeof body.body !== "string") {
      return json({ error: "expected {id, subject, body}" }, 400);
    }
    if (body.body.length > CRAIGSLIST_BODY_LIMIT) {
      return json({ error: `body exceeds the ${CRAIGSLIST_BODY_LIMIT}-character estimate for Craigslist's reply box` }, 400);
    }
    const entry = await readListingState(env, body.id);
    entry.draft_subject = body.subject.slice(0, 200);
    entry.draft_body = body.body;
    entry.drafted_at = new Date().toISOString();
    entry.updated = entry.drafted_at;
    await writeListingState(env, body.id, entry);
    return json({ ok: true });
  }

  if (path === "/api/agent/contact" && request.method === "POST") {
    const body = await request.json();
    const idMatch = typeof body.id === "string" && body.id.match(LISTING_ID_RE);
    const email = typeof body.contact_email === "string" ? body.contact_email.trim() : "";
    const source = typeof body.contact_source === "string" ? body.contact_source.trim() : "";
    if (!idMatch || !email.includes("@") || email.length > 200 || !source || source.length > 500) {
      return json({ error: "expected {id, contact_name?, contact_email, contact_source} -- contact_source is required" }, 400);
    }
    if (body.contact_name !== undefined && (typeof body.contact_name !== "string" || body.contact_name.length > 200)) {
      return json({ error: "contact_name must be a string under 200 characters" }, 400);
    }
    const entry = await readListingState(env, body.id);
    if (typeof body.contact_name === "string" && body.contact_name.trim()) entry.contact_name = body.contact_name.trim();
    entry.contact_email = email;
    entry.contact_source = source;
    // Capture this listing's own address at the moment the contact is
    // recorded, so a LATER posting at the same address (a Craigslist
    // repost under a brand-new id -- see the CLAUDE.md note on posting
    // churn) can inherit this contact via address matching in
    // main.py's load_contact_overrides_by_address(), without needing a
    // check-in to notice the repost and manually reapply it. Best-effort
    // only: if this id isn't in the current scan data (e.g. it already
    // expired), there's nothing to look up, and the id-keyed override
    // above still applies on its own regardless.
    const raw = await env.STATE.get("data", "json");
    const listing = (raw?.listings || []).find((l) => l.id === body.id);
    if (listing?.location) entry.contact_address = listing.location;
    entry.updated = new Date().toISOString();
    await writeListingState(env, body.id, entry);
    return json({ ok: true });
  }

  if (path === "/api/agent/research-checked" && request.method === "POST") {
    const body = await request.json();
    const idMatch = typeof body.id === "string" && body.id.match(LISTING_ID_RE);
    const note = typeof body.note === "string" ? body.note.trim() : "";
    if (!idMatch || !note || note.length > 500) {
      return json({ error: "expected {id, note, dismiss?} -- note is required" }, 400);
    }
    const entry = await readListingState(env, body.id);
    entry.research_checked_at = new Date().toISOString();
    entry.research_note = note;
    // Narrow, explicit, owner-requested exception to AGENT_TOKEN's usual
    // "can't touch review state" rule: dismiss is a boolean the caller must
    // pass on purpose, and the only value it can ever write is "dismissed"
    // -- never able to un-dismiss, star, or set any other status, so a
    // leaked token's blast radius here is still just "things disappear from
    // the default view," never "things get un-hidden or re-categorized."
    // For a listing that's genuinely not a match at all (senior housing,
    // a garage/commercial unit, a room in a shared house, corporate
    // short-term housing, ...) rather than merely "no contact found yet."
    if (body.dismiss === true) entry.status = "dismissed";
    entry.updated = entry.research_checked_at;
    await writeListingState(env, body.id, entry);
    return json({ ok: true });
  }

  if (scope !== "full") {
    // Everything below here is full-token-only except: /api/emailed POST
    // and /api/agent/draft POST (handled in their own blocks above/below),
    // and GET on /api/data / /api/state -- read-only visibility into the
    // same things the agent endpoints already summarize, useful for
    // debugging without needing a second, more powerful credential. Still
    // no PUT/PATCH here for the agent token: it can look, not change.
    const agentReadable =
      (path === "/api/data" && request.method === "GET") ||
      (path === "/api/state" && request.method === "GET");
    if (!agentReadable && !(path === "/api/emailed" && request.method === "POST")) {
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
    return json(await readAllState(env));
  }

  const stateMatch = path.match(new RegExp(`^/api/state/([${LISTING_ID_CHARS}]{1,100})$`));
  if (stateMatch && request.method === "PATCH") {
    const id = stateMatch[1];
    const patch = await request.json();
    const entry = await readListingState(env, id);
    for (const key of ["status", "note", "address", "emailed"]) {
      if (key in patch) {
        const value = patch[key];
        if (value === null || value === "") delete entry[key];
        else if (typeof value === "string" && value.length <= 2000) entry[key] = value;
      }
    }
    entry.updated = new Date().toISOString();
    await writeListingState(env, id, entry);
    const meaningfulKeys = Object.keys(entry).filter((key) => key !== "updated");
    return json(meaningfulKeys.length === 0 ? {} : entry);
  }

  if (path === "/api/overrides" && request.method === "GET") {
    const state = await readAllState(env);
    const lines = ["source_id,address,contact_name,contact_email,contact_source,contact_address"];
    for (const [id, entry] of Object.entries(state)) {
      if (entry.address || entry.contact_email) {
        lines.push(
          [
            csvCell(id),
            csvCell(entry.address || ""),
            csvCell(entry.contact_name || ""),
            csvCell(entry.contact_email || ""),
            csvCell(entry.contact_source || ""),
            csvCell(entry.contact_address || ""),
          ].join(",")
        );
      }
    }
    return new Response(lines.join("\n") + "\n", {
      headers: { "content-type": "text/csv; charset=utf-8", "cache-control": "no-store" },
    });
  }

  if (path === "/api/emailed") {
    if (request.method === "GET") {
      const state = await readAllState(env);
      const ids = Object.entries(state)
        .filter(([, entry]) => entry.emailed)
        .map(([id]) => id);
      return json(ids);
    }
    if (request.method === "POST") {
      // The Action calls this once after a run with every id it just sent
      // to, so a later run's send gate treats them as already contacted.
      const ids = await request.json();
      if (!Array.isArray(ids) || !ids.every((id) => typeof id === "string" && id.length <= 100)) {
        return json({ error: "expected an array of id strings" }, 400);
      }
      const now = new Date().toISOString();
      // Each id is its own key, so these writes never race each other even
      // when the array covers many different listings at once.
      for (const id of ids) {
        const entry = await readListingState(env, id);
        entry.emailed = now;
        entry.updated = now;
        await writeListingState(env, id, entry);
      }
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
