(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const TOKEN_KEY = "rf-token";
  let token = "";
  try { token = localStorage.getItem(TOKEN_KEY) || ""; } catch { /* private mode etc. */ }

  const MAP_PROVIDER_KEY = "rf-map-provider";
  const MAP_PROVIDERS = new Set(["google", "apple", "osm"]);
  let mapProvider = "google";
  try {
    const stored = localStorage.getItem(MAP_PROVIDER_KEY);
    if (stored && MAP_PROVIDERS.has(stored)) mapProvider = stored;
  } catch { /* private mode etc. */ }

  function mapUrl(lat, lon) {
    if (mapProvider === "apple") return `https://maps.apple.com/?ll=${lat},${lon}&q=${lat},${lon}`;
    if (mapProvider === "osm") return `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=17`;
    return `https://www.google.com/maps/search/?api=1&query=${lat},${lon}`;
  }

  let data = null;    // latest scan payload
  let state = {};     // {id: {status, note, address, emailed}}
  let profile = {};   // applicant profile, see applicant_profile.py
  // {normalized_email: {contact_email, company, note, updated}} -- a
  // company-level do-not-contact note (see worker/src/index.js's
  // /api/company-notes), keyed by contact_email rather than address or
  // listing id since that's the one thing shared across every listing from
  // the same property manager, however many different addresses they post
  // under.
  let companyNotes = {};
  // Locations (see groupByAddress's key) with at least one contacted
  // listing -- recomputed on every render() from the FULL listing set, not
  // just what's currently shown, so contacting one unit in a building
  // still hides the rest of that building's group even if e.g. it's since
  // been dismissed or spam-flagged out of view on its own.
  let contactedLocationKeys = new Set();

  const fmt = (n) => Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
  const tierLabel = (ft) => (ft === 1320 ? "¼ mi" : ft === 2640 ? "½ mi" : `${ft} ft`);
  // Craigslist's own limit on its reply-box textarea, not this project's --
  // must match worker/src/index.js's CRAIGSLIST_BODY_LIMIT (that's what
  // actually rejects an over-length draft; this is just the on-page
  // warning). Verify it against what Craigslist shows you if it ever seems
  // off -- it's an estimate this tool has never measured against a real send.
  const CRAIGSLIST_BODY_LIMIT = 4000;

  async function api(path, options = {}) {
    const resp = await fetch(path, {
      ...options,
      headers: { authorization: `Bearer ${token}`, ...(options.body ? { "content-type": "application/json" } : {}), ...(options.headers || {}) },
    });
    if (resp.status === 401) throw new Error("unauthorized");
    if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).error || `HTTP ${resp.status}`);
    return resp.json();
  }

  function showAuth(message) {
    $("#auth").classList.remove("hidden");
    $("#summary").classList.add("hidden");
    $("#filters").classList.add("hidden");
    $("#status").textContent = message || "";
    $("#list").innerHTML = "";
  }

  async function load() {
    if (!token) return showAuth();
    $("#status").textContent = "Loading…";
    try {
      [data, state, profile, companyNotes] = await Promise.all([
        api("/api/data"), api("/api/state"), api("/api/profile"), api("/api/company-notes"),
      ]);
    } catch (err) {
      if (err.message === "unauthorized") {
        const typedLength = token.length;
        token = ""; try { localStorage.removeItem(TOKEN_KEY); } catch {}
        let detail = "";
        try {
          const h = await (await fetch("/api/health")).json();
          detail = h.token_configured
            ? ` The site's secret is ${h.token_length} characters${h.token_has_whitespace ? " and contains whitespace" : ""}; what you entered is ${typedLength}.`
            : " The site has no API_TOKEN secret configured at all.";
        } catch {}
        return showAuth("That token wasn't accepted." + detail);
      }
      $("#status").textContent = err.message === "no scan results yet" ? "No scan has run yet. Results appear after the first GitHub Action run." : `Couldn't load: ${err.message}`;
      return;
    }
    $("#auth").classList.add("hidden");
    $("#summary").classList.remove("hidden");
    $("#filters").classList.remove("hidden");
    renderSummary();
    renderTierOptions();
    renderCategoryOptions();
    fillProfileForm();
    render();
  }

  function fillProfileForm() {
    const form = $("#profile-form");
    for (const [key, value] of Object.entries(profile)) {
      if (form.elements[key]) form.elements[key].value = value;
    }
  }

  function renderSummary() {
    const tiles = $("#tiles");
    tiles.innerHTML = "";
    for (const tier of data.settings.buffer_tiers_ft) {
      const el = document.createElement("div");
      el.className = "tile";
      el.innerHTML = `<div class="n"></div><div class="l"></div>`;
      $(".n", el).textContent = data.tier_counts[String(tier)] ?? 0;
      $(".l", el).textContent = `clear ${tierLabel(tier)}`;
      tiles.appendChild(el);
    }
    const when = new Date(data.generated_at);
    const newCount = data.listings.filter((l) => l.new).length;
    $("#meta").textContent = `${data.listings.length} listings in ${data.settings.county} at or under $${fmt(data.settings.max_rent)} · ${newCount} new · scanned ${when.toLocaleString()}. Tiles count clean listings with a street address that clear every facility type. Family-home daycares and co-op preschools aren't in ANY dataset this checks, and co-ops aren't in Child Care Check either — search a map for "preschool"/"daycare" near any address you're serious about.`;
  }

  function renderTierOptions() {
    const sel = $("#f-tier");
    while (sel.options.length > 1) sel.remove(1);
    for (const tier of data.settings.buffer_tiers_ft) {
      const opt = document.createElement("option");
      opt.value = String(tier);
      opt.textContent = `clears ${tierLabel(tier)}`;
      sel.appendChild(opt);
    }
  }

  const CATEGORY_LABELS = { apa: "apartment", roo: "room" };

  function renderCategoryOptions() {
    const sel = $("#f-category");
    const previous = sel.value;
    while (sel.options.length > 1) sel.remove(1);
    const categories = [...new Set(data.listings.map((l) => l.category).filter(Boolean))].sort();
    for (const category of categories) {
      const opt = document.createElement("option");
      opt.value = category;
      opt.textContent = CATEGORY_LABELS[category] || category;
      sel.appendChild(opt);
    }
    if (categories.includes(previous)) sel.value = previous;
  }

  // A listing counts as contacted once either an auto-sent RentCast email
  // went out (outreach_result === "sent") or the owner clicked "mark
  // replied" for a Craigslist reply-box message (review.emailed) -- the
  // same two conditions the .outreach/.dates display already treats as
  // "emailed" elsewhere in this file.
  function isContacted(listing, review) {
    return Boolean(review.emailed) || listing.outreach_result === "sent";
  }

  // Same normalization as worker/src/index.js's POST /api/company-notes and
  // main.py's load_company_notes() -- lowercase/trimmed contact_email.
  function companyNoteFor(listing) {
    if (!listing.contact_email) return null;
    return companyNotes[listing.contact_email.trim().toLowerCase()] || null;
  }

  function passes(listing) {
    const review = state[listing.id] || {};
    if ($("#f-hide-contacted").checked && contactedLocationKeys.has(listing.location || listing.id)) return false;
    const status = $("#f-status").value;
    if (status === "active" && review.status === "dismissed") return false;
    if (status === "starred" && review.status !== "starred") return false;
    if (status === "dismissed" && review.status !== "dismissed") return false;
    const tier = $("#f-tier").value;
    if (tier && listing.clears[tier] !== true) return false;
    const cat = $("#f-category").value;
    if (cat && listing.category !== cat) return false;
    if ($("#f-new").checked && !listing.new) return false;
    if ($("#f-clean").checked && listing.spam_score > 0) return false;
    // Doesn't drop the listing from the underlying data -- only from view --
    // so a future outreach check-in still sees it and doesn't repeat contact
    // research that already came up empty.
    if ($("#f-no-contact").checked && listing.source === "rentcast" && !listing.contact_email) return false;
    const q = $("#f-search").value.trim().toLowerCase();
    const haystack = $("#f-search-desc").checked
      ? `${listing.title} ${listing.location || ""} ${listing.description || ""}`
      : `${listing.title} ${listing.location || ""}`;
    if (q && !haystack.toLowerCase().includes(q)) return false;
    return true;
  }

  function render() {
    const list = $("#list");
    list.innerHTML = "";
    contactedLocationKeys = new Set();
    for (const l of data.listings) {
      if (isContacted(l, state[l.id] || {})) contactedLocationKeys.add(l.location || l.id);
    }
    const shown = data.listings.filter(passes);
    $("#status").textContent = `${shown.length} of ${data.listings.length} listings`;
    const tpl = $("#card-tpl");
    for (const group of groupByAddress(shown)) list.appendChild(renderGroup(group, tpl));
  }

  // Same grouping key the outreach agent already uses to send one draft/
  // contact per building instead of one per posting (worker/src/index.js's
  // /api/agent/candidates) -- a plain string match on the listing's own
  // `location`, not a normalized/geocoded address. A listing with no
  // location groups alone, same as there. Large complexes commonly post
  // several units (or the same unit under several titles) at once; this is
  // purely a display grouping -- each listing keeps its own row, its own
  // state (star/dismiss/note/emailed), and its own Craigslist reply link.
  function groupByAddress(listings) {
    const byKey = new Map();
    for (const listing of listings) {
      const key = listing.location || listing.id;
      if (!byKey.has(key)) byKey.set(key, []);
      byKey.get(key).push(listing);
    }
    return [...byKey.values()];
  }

  function renderGroup(group, tpl) {
    if (group.length === 1) return card(group[0], tpl);
    const wrap = document.createElement("div");
    wrap.className = "building-group";
    const header = document.createElement("p");
    header.className = "group-header";
    header.textContent = `${group.length} postings at ${group[0].location}`;
    wrap.appendChild(header);
    group.forEach((listing, i) => {
      const node = card(listing, tpl);
      // The address, distance chips, map link, and child care check link are
      // identical for every listing in the group (same location) -- show
      // them once, on the first card, instead of repeating them per unit.
      if (i > 0) {
        for (const sel of [".location", ".tiers", ".distances", ".act-map", ".act-ccc"]) {
          const el = $(sel, node);
          if (el) el.classList.add("hidden");
        }
      }
      wrap.appendChild(node);
    });
    return wrap;
  }

  function card(listing, tpl) {
    const node = tpl.content.firstElementChild.cloneNode(true);
    const review = state[listing.id] || {};
    node.dataset.id = listing.id;
    node.classList.toggle("starred", review.status === "starred");
    node.classList.toggle("dismissed", review.status === "dismissed");

    $(".price", node).textContent = listing.price != null ? `$${fmt(listing.price)}` : "—";
    const badges = $(".badges", node);
    const badge = (text, cls = "") => { const b = document.createElement("span"); b.className = `badge ${cls}`; b.textContent = text; badges.appendChild(b); };
    if (listing.new) badge("new", "new");
    badge(listing.source === "rentcast" ? "RentCast" : "Craigslist");
    badge(listing.category === "roo" ? "room" : listing.bedrooms != null ? `${listing.bedrooms === 0 ? "studio" : listing.bedrooms + " BR"}` : listing.category || "apartment");
    if (listing.precision === "address") badge("street address");
    else if (listing.precision === "area") badge("no address yet", "warn");
    else badge("no location", "warn");

    const a = $(".title a", node);
    a.textContent = listing.title;
    a.href = listing.url;
    $(".location", node).textContent = review.address ? `${review.address} (your address; measured next run)` : listing.location || "";

    const tiers = $(".tiers", node);
    for (const tier of data.settings.buffer_tiers_ft) {
      const v = listing.clears[String(tier)];
      const chip = document.createElement("span");
      chip.className = `chip ${v === true ? "yes" : v === false ? "no" : "unk"}`;
      chip.textContent = `${tierLabel(tier)} ${v === true ? "✓" : v === false ? "✗" : "?"}`;
      tiers.appendChild(chip);
    }

    const parts = [];
    for (const [type, ft] of Object.entries(listing.nearest_ft)) {
      if (ft === null) continue;
      parts.push(`${type} ${ft < 0 ? `> ${fmt(Math.max(...data.settings.buffer_tiers_ft))}` : fmt(ft)} ft`);
    }
    $(".distances", node).textContent = parts.length ? `nearest: ${parts.join(" · ")}` : listing.precision === "address" ? "distance check pending" : "add the street address below to get distances";

    $(".flags", node).textContent = listing.spam_flags.length ? `⚠ ${listing.spam_flags.join(", ")}` : "";
    const companyNote = companyNoteFor(listing);
    const companyNoteEl = $(".company-note", node);
    if (companyNote) {
      companyNoteEl.textContent = `🚫 ${companyNote.company ? `${companyNote.company}: ` : ""}${companyNote.note}`;
      companyNoteEl.classList.remove("hidden");
    } else {
      companyNoteEl.classList.add("hidden");
    }
    $(".desc", node).textContent = listing.description || "";
    const dateParts = [listing.posted && `posted ${listing.posted}`, listing.first_seen && `first seen ${listing.first_seen}`];
    if (listing.contact_email) dateParts.push(`contact: ${listing.contact_email}${listing.contact_source ? " (via research)" : ""}`);
    else if (review.research_checked_at) dateParts.push(`researched ${new Date(review.research_checked_at).toLocaleDateString()}, no contact found${review.research_note ? ` (${review.research_note})` : ""}`);
    $(".dates", node).textContent = dateParts.filter(Boolean).join(" · ");

    const outreach = $(".outreach", node);
    outreach.className = "outreach";
    if (review.emailed) {
      outreach.textContent = `✓ emailed ${new Date(review.emailed).toLocaleDateString()}`;
      outreach.classList.add("sent");
    } else if (listing.outreach_result === "sent") {
      outreach.textContent = "✓ emailed just now";
      outreach.classList.add("sent");
    } else if (listing.outreach_result === "ready to send") {
      outreach.textContent = "ready to auto-send next run";
      outreach.classList.add("ready");
    } else if (listing.outreach_result) {
      outreach.textContent = `not auto-sent: ${listing.outreach_result}`;
    }

    const isCraigslist = listing.source === "craigslist";
    // A personally-written draft (state, from a Claude check-in) takes
    // priority over the scan's own template draft -- see README's "Outreach
    // and auto-send".
    const personalDraft = Boolean(review.draft_body);
    const draftSubject = review.draft_subject || listing.draft_subject || "";
    const draftBody = review.draft_body || listing.draft_body || "";

    const draftBtn = $(".act-draft", node);
    const draftBox = $(".draft", node);
    if (draftBody) {
      draftBtn.classList.remove("hidden");
      $(".draft-source", draftBox).textContent = personalDraft
        ? `personally drafted ${new Date(review.drafted_at).toLocaleString()}`
        : "auto-drafted template -- read before sending; see README's known wording issues";
      $(".draft-subject", draftBox).textContent = isCraigslist ? "" : draftSubject;
      $(".draft-body", draftBox).textContent = draftBody;
      draftBtn.onclick = () => draftBox.classList.toggle("hidden");

      const countEl = $(".draft-count", draftBox);
      if (isCraigslist) {
        const over = draftBody.length > CRAIGSLIST_BODY_LIMIT;
        countEl.textContent = `${fmt(draftBody.length)} / ${fmt(CRAIGSLIST_BODY_LIMIT)} characters (Craigslist's own reply-box estimate)${over ? " -- likely too long, trim before pasting" : ""}`;
        countEl.classList.toggle("warn", over);
      } else {
        countEl.textContent = "";
      }

      $(".draft-copy", draftBox).onclick = async () => {
        // Craigslist's reply box is a message body with no subject field;
        // an email needs both.
        const toCopy = isCraigslist ? draftBody : `${draftSubject}\n\n${draftBody}`;
        try {
          await navigator.clipboard.writeText(toCopy);
          $(".draft-copy", draftBox).textContent = "copied!";
          setTimeout(() => { $(".draft-copy", draftBox).textContent = "copy draft"; }, 1500);
        } catch { /* clipboard unavailable -- the text is still selectable */ }
      };
    }

    const replyCl = $(".act-reply-cl", node);
    if (isCraigslist && draftBody) {
      replyCl.classList.remove("hidden");
      replyCl.href = listing.url;
    }

    const replied = $(".act-replied", node);
    if (draftBody) {
      replied.classList.remove("hidden");
      replied.classList.toggle("replied", Boolean(review.emailed));
      replied.textContent = review.emailed ? "✓ replied (undo)" : "mark replied";
      replied.onclick = () => save(listing.id, { emailed: review.emailed ? "" : new Date().toISOString() }, replied);
    }

    const map = $(".act-map", node);
    if (listing.lat != null && listing.lon != null) map.href = mapUrl(listing.lat, listing.lon);
    else map.remove();

    const star = $(".act-star", node);
    star.textContent = review.status === "starred" ? "★ starred" : "☆ star";
    star.onclick = () => save(listing.id, { status: review.status === "starred" ? "" : "starred" }, star);
    const dismiss = $(".act-dismiss", node);
    dismiss.textContent = review.status === "dismissed" ? "restore" : "dismiss";
    dismiss.onclick = () => save(listing.id, { status: review.status === "dismissed" ? "" : "dismissed" }, dismiss);

    const form = $(".edit", node);
    $(".edit-address", form).value = review.address || "";
    $(".edit-note", form).value = review.note || "";
    $(".act-edit", node).onclick = () => form.classList.toggle("hidden");
    $(".edit-cancel", form).onclick = () => form.classList.add("hidden");
    form.onsubmit = (e) => {
      e.preventDefault();
      save(listing.id, { address: $(".edit-address", form).value.trim(), note: $(".edit-note", form).value.trim() }, $("button[type=submit]", form));
    };
    $(".note", node).textContent = review.note || "";
    return node;
  }

  async function save(id, patch, button) {
    // Disabling immediately, before the request even starts, is the fix for
    // a real reported bug: with no visible feedback during the round trip,
    // a dismiss (which makes the card disappear once it lands, under the
    // site's default "not dismissed" filter) looked like it hadn't
    // registered, so a second tap landed on whatever card had shifted up
    // into that same spot once the first one actually went through.
    if (button) button.disabled = true;
    try {
      const entry = await api(`/api/state/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
      if (Object.keys(entry).length) state[id] = entry; else delete state[id];
      render();
    } catch (err) {
      $("#status").textContent = `Couldn't save: ${err.message}`;
      if (button) button.disabled = false;
    }
  }

  $("#auth-form").onsubmit = (e) => {
    e.preventDefault();
    token = $("#token").value.trim();
    try { localStorage.setItem(TOKEN_KEY, token); } catch {}
    load();
  };
  $("#settings-btn").onclick = () => { $("#auth").classList.toggle("hidden"); };
  $("#profile-btn").onclick = () => { $("#profile").classList.toggle("hidden"); };
  $("#profile-close").onclick = () => { $("#profile").classList.add("hidden"); };
  $("#profile-form").onsubmit = async (e) => {
    e.preventDefault();
    const form = e.target;
    const payload = Object.fromEntries(new FormData(form).entries());
    try {
      profile = await api("/api/profile", { method: "PUT", body: JSON.stringify(payload) });
      $("#profile-status").textContent = profile.disclosure_text
        ? "Saved. Outreach emails can now be drafted." : "Saved, but no disclosure text yet -- nothing will be drafted or sent until it's filled in.";
    } catch (err) {
      $("#profile-status").textContent = `Couldn't save: ${err.message}`;
    }
  };
  for (const id of ["f-tier", "f-category", "f-status", "f-new", "f-clean", "f-no-contact", "f-hide-contacted", "f-search-desc"]) $(`#${id}`).onchange = render;
  $("#f-search").oninput = render;
  $("#map-provider").value = mapProvider;
  $("#map-provider").onchange = () => {
    mapProvider = $("#map-provider").value;
    try { localStorage.setItem(MAP_PROVIDER_KEY, mapProvider); } catch {}
    render();
  };

  load();
})();
