# Working notes for Claude

- The owner works from a phone. When you open a pull request, merge it
  yourself once it's ready (tests pass, live checks done) — don't wait for
  a manual merge. Anything that would normally need a terminal (wrangler,
  secrets) should come with dashboard/browser instructions instead.
- Run `python -m pytest tests/` before every push.
- Every distance the tool reports must come from a street address; never
  let an unverified check read as a pass. See `rental_finder/compliance.py`
  and `models.py` for the invariant.
- Licensed family-home child care isn't in any open dataset, and parent
  cooperative preschools are exempt from DCYF licensing entirely (absent
  from Child Care Check too, not just this tool). Don't claim coverage for
  either anywhere.
- `room_share_filter.py` drops Craigslist "rooms & shares" listings that
  have a description or room_attrs, UNLESS the listing itself has an
  explicit self-contained signal (ADU, in-law, private entrance, studio,
  detached, ...) -- that's the one thing that keeps it. A "roo" listing is
  an occupied shared room BY DEFAULT once there's something to read; a
  "private bath" attribute or an otherwise-neutral whole-house description
  are NOT self-contained signals and do not save a listing on their own (a
  real listing missed this exact way: "private room" + "private bath" + a
  neutral description, no self-contained language anywhere -- still
  excluded now). A listing with NEITHER a description nor room_attrs is the
  one case kept regardless (nothing to judge yet). If you touch this, keep
  that default -- the owner asked for this specifically to stop seeing
  occupied-room listings, and an earlier, more conservative version of this
  file (default-keep, exclude only on a strong signal like "no private
  bath") missed real room-for-rent listings that had no strong negative
  signal, which is why the default flipped.
  The "nothing to judge yet" gate checks `description`/`room_attrs`
  directly, NOT `details_fetched` -- a second real listing was missed
  because of exactly that distinction: main.py's room_attrs backfill resets
  `details_fetched` to False on listings that already have a perfectly
  good description from before room_attrs existed, and checking
  `details_fetched` treated that stale-but-still-accurate description as
  "nothing to judge from yet." Don't go back to gating on `details_fetched`.
  Also: a "roo" listing already marked `details_fetched` from before
  `room_attrs` existed has an empty `room_attrs` indistinguishable from
  "genuinely has no badges" -- `main.py`'s `run()` re-queues those for one
  more detail fetch (see the room_attrs backfill comment there) rather than
  leave them unclassifiable forever. Don't remove that backfill without
  another way to fix already-cached listings.
  Explicit roommate/shared-space language (`_STRONG_SHARED_RE`: "roommate,"
  "housemate," "shared bath/kitchen/space/common," "share the/my/our
  bath/kitchen/common," "share my/the/our studio/apartment/house/room/
  place," "other tenant(s)") is checked FIRST, before the self-contained
  check AND before the "nothing to judge yet" gate -- it overrides
  everything, even from the title alone with no description yet. Three real
  listings were missed without this: "Roommate Wanted to Share Studio
  Apartment" (the bare word "studio" kept it self-contained); a room
  described as having "its own entrance, kitchen, laundry and bathroom"
  that in the same paragraph says that bathroom is "shared with a total of
  3 people" and calls them "roommates" (the own-entrance/own-kitchen
  signals kept it); and "Large Room for Rent" describing a "Shared
  bathroom/kitchenette w/ 1 other" ("kitchenette" alone said nothing about
  whether it was private, so it's been removed from the self-contained list
  entirely -- don't add it back). If you touch this filter again, keep the
  strong-shared check ahead of the self-contained check, and ahead of the
  gate too.
- The owner is 39 -- doesn't qualify for 55+/62+ senior housing.
  `senior_housing_filter.py`'s `is_age_restricted()` drops it from BOTH
  sources (RentCast's aggregated listings can include senior communities
  same as Craigslist's), unconditionally, off whatever text is available
  (title alone if not yet detail-fetched) -- unlike the room-share filter,
  there's no "haven't looked yet, keep it" carve-out here, since an age
  restriction is something posters advertise up front, not something that
  needs a detail page to discover.
- `settings.min_latitude` (`config.py`, currently 47.35 -- Kent's southern
  edge) drops anything further south, applied to `listing.latitude` after
  geocoding (kept, not dropped, when there's no latitude at all -- nothing
  to measure). The owner named Kent/Des Moines as the boundary but had
  already gotten an outreach draft for an Auburn listing (~47.31, further
  south than Kent) without objecting to it; asked directly, the owner
  picked the strict Kent/Des Moines line anyway, which means Auburn is
  excluded too going forward. Don't loosen this back toward "keep Auburn"
  without the owner asking for it back -- that was the explicitly declined
  option, not an oversight.
- Outreach *eligibility* (`outreach.py`) is gated by deterministic,
  auditable rules only — never a model's self-reported confidence. A
  listing is only ever marked "ready to send" (RentCast listings alone;
  Craigslist has no real, scriptable contact address) when it clears every
  rule; see `outreach.py`'s docstring.
- `_gate_reason()`'s check ORDER matters, not just its content: the
  contact-email check must stay LAST, after address/spam/buffer. It used to
  run first, which meant "no automatable contact" -- the string
  `/api/agent/candidates` treats as "cleared everything else, just needs a
  personal Craigslist draft" -- became the reason for literally every
  Craigslist listing, address or no address, spam-flagged or not (found
  when a live check-in returned 607 "candidates," most with no verified
  location at all). If you add a new eligibility rule, add it before the
  contact-email check, never after.
- Outreach *drafting and sending* is deliberately NOT done by
  `email_draft.py`'s template for the live flow — the owner found the
  templated output choppy (raw profile-field text slotted into fixed
  sentences, e.g. a literal "around When available" -- fixed to "Move-in
  timeline: ..." but the template still inserts the whole
  employment/income text verbatim regardless of relevance, which is a
  template limitation, not a bug to chase further). Instead, a Claude
  session reads candidates via the Worker's `AGENT_TOKEN`-gated
  `/api/agent/candidates` endpoint and handles each by its `action` field:
  - `"send"` (RentCast, gate-eligible): personally write the email with
    real per-listing judgment and send it via the connected Gmail
    integration directly (no draft-then-approve step — the owner
    explicitly chose immediate sending).
  - `"draft"` (Craigslist, eligible except for having no automatable
    contact): personally write ONE message body sized for Craigslist's
    reply box (no subject line -- see `craigslist_body_limit` in the
    response, currently 4000 characters; treat it as an estimate, not a
    hard fact) per candidate, and POST it to `/api/agent/draft` as
    `{id, subject: "", body}` once for EVERY id in that candidate's
    `same_address_ids` (the Worker already grouped same-address postings --
    large complexes commonly post one unit under several titles -- so this
    is how the one draft reaches every posting instead of writing a
    separate message per posting at the same address). Never send this one
    yourself and never call `/api/emailed` for it -- there's no scriptable
    way to submit Craigslist's reply box, so only the owner, clicking "mark
    replied" on the site after actually pasting it in, can correctly say it
    went out.
  **This runs only when the owner pings a session and asks for a
  check-in — not on a recurring schedule.** An unattended, self-rewaking
  version was tried and refused by the coding environment's own safety
  controls (an autonomous job that repeatedly sends real email with no one
  present, even with the owner's prior sign-off on immediate sending, isn't
  something to force through); manual triggering is the accepted fallback,
  not a placeholder for a future recurring version — don't re-attempt
  scheduling this without the owner asking for it back.
  `email_draft.py`/`mailer.py` still exist as the immediate, always-on
  fallback draft (Craigslist) and for local testing of the SMTP path, but
  are not part of the live send path. If you are the session doing a
  check-in: keep drafting real per-listing prose (skip irrelevant profile
  fields, phrase things naturally), and never reintroduce template-based
  auto-send as the live mechanism without the owner asking for it back.
- Before drafting each candidate in a check-in, personally read its
  category, attributes, price, and description together for internal
  consistency -- that's exactly the kind of judgment `spam_filter.py`'s
  regexes can't apply, and it's why a human/agent review layer on top of
  the deterministic gate is worth having. Concretely: a Craigslist "rooms &
  shares" listing with a "private room" attribute and a whole-house
  description (fireplace, garden, garage) is normal, not suspicious --
  Craigslist's own "$620 / 2br" title format states the ASKING price
  alongside the UNIT's total bedroom count regardless of whether a whole
  unit or one room is being rented, so the price is for the room, not the
  house; `_price_floor_by_category()` already compares it against other
  room prices for exactly this reason (see its docstring). Skip and flag to
  the owner only for a genuine inconsistency (e.g. the described property
  type contradicts the category in a way no normal posting convention
  explains, or specifics in the text contradict each other). Do NOT try to
  cross-verify a listing's price against Zillow/Trulia/HotPads/etc: they're
  far more aggressive against scraping than Craigslist (confirmed live --
  one direct request 403'd), and treating whatever they show as ground
  truth repeats the exact mistake this file already warns about with AI
  chatbots (see README's "What it does NOT cover"). Live-verified case: an
  outside chatbot claimed Trulia "independently verified" $2,775/mo for a
  Craigslist room listed at $620, as proof of fraud. Fetching that exact
  Trulia page directly showed the property marked OFF MARKET, with a
  different bed/bath/sqft profile than either source described, and an
  automated rent *estimate* of $1,383 -- nothing resembling $2,775, and
  not an active listing to compare against in the first place. The
  chatbot's specific citation didn't hold up; don't take a chatbot's
  claimed citations, including this file's or your own, on faith.
- The disclosure paragraph in an outreach email is the applicant's own
  words from their profile, verbatim, regardless of who or what drafts the
  rest of the email. Never draft, edit, or suggest that paragraph, and
  never draft or send anything when it's missing.
- A plain local run of `main.py` must never send real email regardless of
  configured credentials — only an explicit `--send-emails` flag (a local
  testing aid only; the scheduled Action never passes it) allows a send
  via the SMTP path.
- `AGENT_TOKEN` is intentionally narrower than `API_TOKEN`: it can only
  read `/api/agent/candidates` and POST `/api/emailed` or
  `/api/agent/draft` (and even that last one can only write
  draft_subject/draft_body/drafted_at, never status/note/address/emailed).
  Don't widen its access without a specific reason — the whole point is
  that a session holding it for outreach check-ins has a small blast
  radius if exposed.
