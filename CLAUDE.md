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
- As of the most recent real RentCast fetch (500 listings, checked live):
  0 had a listingAgent or listingOffice email, AND 0 had a listingAgent or
  listingOffice phone number either -- not just email being spottier than
  phone, but neither field present on any listing at all. This means no
  RentCast listing can currently reach "ready to send" (contact_email is
  one of the gate's rules), and an SMS-based outreach channel -- raised
  once as an alternative to email, since phone numbers seemed like they
  might be more reliably present -- has nothing to work with either. This
  is RentCast's data, not a bug here: their own docs say these fields are
  sometimes omitted, and `rentcast.py` already logs both counts on every
  real fetch (`with_agent_phone`/`with_office_phone`) specifically to
  monitor whether that ever changes. Phone isn't captured onto the
  `Listing` model since there's nothing yet to do with it. If a future
  fetch shows non-zero phone counts, that's worth revisiting; don't assume
  it's still zero without checking a recent log.
- `_gate_reason()`'s check ORDER matters, not just its content: the
  contact-email check must stay LAST, after address/spam/buffer. It used to
  run first, which meant "no automatable contact" -- the string
  `/api/agent/candidates` treats as "cleared everything else, just needs a
  personal Craigslist draft" -- became the reason for literally every
  Craigslist listing, address or no address, spam-flagged or not (found
  when a live check-in returned 607 "candidates," most with no verified
  location at all). If you add a new eligibility rule, add it before the
  contact-email check, never after.
  A source-level check was added ahead of the final contact-email check:
  `listing.source == "craigslist" and not listing.contact_source` returns
  "no automatable contact ...". Before contact overrides existed (see
  below), Craigslist was safe from ever auto-sending only because
  craigslist.py never set contact_email -- an assumption, not an enforced
  rule. Once ANY mechanism can set contact_email on a listing (a research
  override), that assumption stops holding on its own. This check makes it
  an explicit rule instead, but -- per the owner's later, explicit ask --
  NOT an unconditional one: a Craigslist listing with a VERIFIED override
  (contact_source set, meaning a check-in actually recorded a cited
  contact via POST /api/agent/contact -- see below) is allowed through,
  same as any other listing. What stays blocked is an UNVERIFIED
  contact_email on a Craigslist listing -- one that got there some other
  way, with no citation to back it -- see
  `test_craigslist_listing_with_an_unverified_contact_email_still_never_auto_sends`
  and `test_craigslist_listing_with_a_verified_contact_override_can_auto_send`.
  Don't loosen this to "any contact_email" -- the citation requirement is
  the entire safety property; without it, this degrades back to trusting
  whatever ends up in the field, exactly what this file's eligibility rule
  above exists to rule out.
- Since neither source reliably supplies a real contact on its own (0/500
  from RentCast -- see the fetch-diagnostic note above; Craigslist's own
  reply widget is never a real address), a listing that clears every OTHER
  outreach rule can get a contact_email from a **contact override**
  instead -- `main.py`'s `load_contact_overrides()` reads it from the same
  overrides CSV as address overrides (`/api/overrides`, now
  `source_id,address,contact_name,contact_email,contact_source`), applied
  in `run()` right after address overrides, ALWAYS winning when present
  (same "override always wins" precedent as `override_address`). Once
  applied, `outreach.py`'s gate treats it exactly like a RentCast-provided
  contact -- no special-casing, no separate code path for "researched" vs
  "provider" contact_email (Craigslist still needs contact_source
  specifically, per the check above, but that's the only source-dependent
  part) -- the eligibility decision stays 100% in the same deterministic
  gate regardless of where contact_email came from.
  The override is written by a check-in session via
  `POST /api/agent/contact` (`{id, contact_name?, contact_email,
  contact_source}`, either token) for a `"research"`-action candidate from
  `/api/agent/candidates`: RentCast with `outreach_result == "no contact
  email"`, or Craigslist with `outreach_result == "no automatable contact
  ..."` (grouped by verified address, same as the "draft" bucket and for
  the same reason -- a poster's direct contact found for one unit almost
  certainly covers every unit posted at that address, so `/api/agent/contact`
  gets called once per id in `same_address_ids`). For Craigslist, check the
  listing's OWN description for a direct email/phone the poster gave first
  -- cheaper and more reliable than web research, and some posters do
  bypass Craigslist's relay themselves. `contact_source` is REQUIRED and
  must be a real citation (e.g. "AI research (high confidence): <url>", or
  "found directly in the listing's own description"), never a bare
  confidence label -- every write needs to be auditable later. The
  endpoint can only write contact_name/contact_email/contact_source, same
  narrow-field pattern as `/api/agent/draft` for status/note/address/emailed.
  A Craigslist listing with a verified contact stops being offered as a
  "draft" candidate too (the Worker's `draftEligible` filter also checks
  `!state[l.id]?.contact_email`) -- once a direct email is on its way, a
  reply-box draft for the same listing is just wasted effort.
  **The owner's explicit confidence policy** (chosen after a real batch of
  19 researched addresses came back with real variance -- 4 with no
  reliable contact, several confirmed only at the building level rather
  than the specific unit, one source already stale on a recheck, and two
  listings that turned out miscategorized entirely: a parking-garage unit
  priced as "Single Family," and a 55+ senior community RentCast gave no
  name/description for, which `senior_housing_filter.py` had nothing to
  catch it with): auto-send (record the override, trigger a scan, then send
  on the next check-in once "ready to send") on BOTH high AND moderate
  confidence -- skip recording anything only for "not found" or something
  too shaky even for moderate. Don't tighten this to "high confidence only"
  without the owner asking for it back; that stricter option was presented
  and explicitly not chosen. This policy was set for RentCast research
  first, then the owner separately asked for the same research step (and,
  implicitly, the same policy -- nothing narrower was asked for or applied)
  to extend to Craigslist too, specifically to also try emailing a poster
  directly instead of only ever leaving a reply-box draft.
  A contact override does NOT retroactively flip the CURRENT scan's
  `outreach_result` -- exactly like an address override, it only takes
  effect once a fresh scan run re-evaluates the gate. A check-in that
  records new contacts must trigger a scan and wait for it before treating
  those listings as "ready to send"; don't shortcut this by personally
  deciding a listing is now eligible and sending anyway; that recreates the
  exact "self-reported confidence" pattern this file's eligibility rule
  above exists to rule out.
  Before recording ANY researched contact, personally check the listing's
  own category/price/description for the same kind of internal-consistency
  red flags already required for Craigslist drafting below -- both
  miscategorized listings above (the garage unit, the senior community)
  would have been caught by that same read, not by the contact research
  itself.
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
  read `/api/agent/candidates` and POST `/api/emailed`, `/api/agent/draft`
  (only draft_subject/draft_body/drafted_at, never
  status/note/address/emailed), or `/api/agent/contact` (only
  contact_name/contact_email/contact_source, same reasoning -- see the
  contact-override note above; it was widened for this specific,
  owner-requested reason, not casually). Don't widen its access further
  without an equally specific reason — the whole point is that a session
  holding it for outreach check-ins has a small blast radius if exposed.
- **Root cause of a real "recorded contacts never take effect" incident,
  found and fixed in a later check-in**: `GET /api/overrides` built each
  CSV row as `[id, csvCell(address), csvCell(contact_name),
  csvCell(contact_email), csvCell(contact_source)].join(",")` -- every
  column EXCEPT `id` went through `csvCell()`'s comma/quote escaping.
  RentCast ids are address-derived slugs that legitimately contain commas
  (e.g. `"4736-18th-Ave-Ne-Apt-C,-Seattle,-WA-98105"`), so an unescaped
  comma in the id corrupted the row's column boundaries and
  `load_contact_overrides()` silently misparsed every RentCast row --
  confirmed live: 20 contacts recorded and verified present in
  `/api/state`, two full scan cycles each fetching a non-empty overrides
  CSV ("23 overrides" in the Action's own log), and still zero listings
  ever reached "ready to send" until this was fixed (wrap `id` in
  `csvCell(id)` too). If a future check-in ever sees recorded contacts
  not taking effect despite `/api/state` and the fetched CSV both looking
  right, this is the first thing to re-check for regression.
- **`senior_housing_filter.py` has a confirmed live gap**: it only matches
  explicit phrases like "senior living/community/apartments", "55+", or
  "independent living" in a listing's own title+description. Two real,
  currently-live buildings slipped through it during a check-in and had
  to be caught by hand and excluded from outreach: **Highlands West
  Apartments** (18520 8th Ave NW, Shoreline -- confirmed 55-and-better via
  a live fetch of liveathighlandswest.com) had ONE posting whose title
  said bare "senior" with no qualifying word after it (doesn't match the
  regex, which requires "senior" immediately followed by
  living/community/communities/housing/apartments?/residence), and a
  SECOND posting for the exact same building that didn't mention "senior"
  or any age language anywhere at all -- only the address itself gives it
  away, which the filter has no way to check since it never looks up a
  building name/address against known senior communities, only the
  listing's own text. Also caught the same way: **Covington Place**
  (26902 169th Pl SE, Covington), a Village Concepts 55+ community, whose
  RentCast listing text likewise carried no qualifying phrase. Both were
  excluded from outreach by hand rather than by fixing the filter, since
  tightening the regex (e.g. matching bare "senior") risks new false
  positives and the address-lookup approach is a bigger change -- flagged
  for the owner to decide, not changed unilaterally. If you hit another
  one, check it here before assuming it's a one-off.
- Also caught by hand during that same check-in, same "read the listing
  before trusting the category" habit as the price-comparison note above:
  a RentCast "Single Family" listing at "325 5th Ave S, Unit GARAGE1,
  Kirkland" priced at $495/month with 0 bedrooms (almost certainly a
  literal parking/storage garage, not a residence), and a RentCast "Condo"
  at "17713 15th Ave NE, Ste 101, Shoreline" ($1195/month, bedrooms null,
  "Ste" = Suite, reads like a commercial/office unit). Both excluded from
  outreach and flagged rather than researched/contacted -- this is the
  same failure mode as the parking-garage-unit and uncaught-senior-
  community listings from the original 19-address batch, RentCast data
  quality rather than a bug here, and worth a quick category/unit-label
  sanity check on every candidate before researching or drafting for it.
- The owner asked for a way to hide RentCast listings that couldn't be
  contacted, but the underlying gap that surfaced first: nothing recorded
  when a check-in researched a listing and came up empty (per this file's
  own confidence policy above, "not found" is deliberately never written
  as a contact_email/contact_source) -- a not-yet-researched listing and
  an already-researched-and-failed one were indistinguishable, so a future
  check-in had no way to skip repeating work already done. Fixed with a
  new, separate marker: `POST /api/agent/research-checked` (`{id, note}`,
  either token, note required, same auditability reasoning as
  contact_source) writes ONLY `research_checked_at`/`research_note` --
  never a contact_email, never anything outreach.py's gate looks at, and
  no scan run needs to pick it up for it to matter. Its only effect is on
  `/api/agent/candidates`: an id carrying this marker drops out of the
  "research" bucket (both RentCast and Craigslist) so it's never re-offered
  as something to research again. If you're the check-in session and you
  research a candidate and come up empty, call this before moving on --
  otherwise the next check-in repeats your work. The site's own toggle
  ("hide RentCast, no contact found," `worker/public/index.html`/`app.js`)
  is a separate, client-side-only view filter on `!contact_email` -- it
  doesn't read this marker and doesn't need to; it only controls what's
  visible on the page, while this marker is what actually stops duplicate
  research.
- Extending the research/contact-override process to Craigslist (per the
  owner's ask) surfaced two more things worth knowing:
  1. **Craigslist posting ids churn faster than a scan cycle.** A contact
     recorded for a Craigslist id is only useful if that exact id is still
     in the next scan's results -- and in practice, several buildings'
     postings had already expired and been reposted under a brand-new id
     (Malmo, Kirin, Liberty Bank Building, Avon Park, and Latitude 112 all
     did this within roughly 10-40 minutes) before a triggered scan even
     finished running. The contact_email/contact_source found for the old
     id doesn't transfer to the new one automatically -- overrides are
     keyed by listing id, not by address -- so a check-in has to notice the
     repost and re-apply the same contact to the new id by hand. This is
     expected, not a bug: it's inherent to Craigslist ids being per-posting
     rather than per-property (unlike RentCast's stable, address-derived
     ids). If a recorded Craigslist contact never seems to reach "ready to
     send," check whether the id it was recorded against is still in
     `/api/data` at all before assuming something's broken.

     **Fixed** (the owner asked for this after seeing it happen live):
     address-based contact matching, as a FALLBACK behind the existing
     id-based match, never instead of it. `POST /api/agent/contact`
     (`worker/src/index.js`) now looks up the listing's own `location` in
     the current scan data at write time and stores it as a new
     `contact_address` field on that state entry (best-effort -- if the id
     isn't in `raw.listings` anymore, there's nothing to look up, and the
     id-keyed override still works fine on its own). `GET /api/overrides`
     gained a 6th CSV column carrying it. `main.py`'s new
     `load_contact_overrides_by_address()` builds a second, address-keyed
     map from that column; `run()` checks it only when a listing has no
     id-level override AND `has_street_number(listing.best_address)` is
     true -- that street-number guard is the whole safety property here,
     since matching on a bare area string like "Seattle, WA" would
     silently cross-wire unrelated buildings that just happen to share a
     neutral location string. The inherited override's `contact_source`
     gets `" (same address as a prior posting)"` appended, so the email
     trail stays honest about where the match actually came from -- it's
     never indistinguishable from a contact personally verified against
     that exact id. RentCast doesn't need this (its ids are themselves
     address-derived, so an id match already catches the same-address
     case there) but isn't excluded from it either -- it's a correct,
     harmless no-op there since address-matching can never find anything
     an id match didn't already find first. Verified live via
     `wrangler dev --local`: recorded a contact against one id, confirmed
     `contact_address` appears correctly (comma and all) in the CSV, then
     confirmed a second, brand-new id at the identical address correctly
     inherits it while a bare area string never matches anything.
  2. **`room_share_filter.py` only inspects `roo`-category listings**, but
     a real one slipped through under `apa`: "Roost on 23rd" was posted as
     an ordinary apartment listing, yet its own description reads "Roost on
     23rd: Room for Rent with Private Attached Bath," and Trulia
     independently lists the property as a "Rooming House." A 161 sq ft "1
     bed 1 bath" at $795 is also a strong practical tell on its own --
     ordinary studios don't run that small. Excluded from outreach by hand
     (marked research-checked, not researched for a contact) rather than
     by changing the filter, same reasoning as the senior-housing gap
     above: worth a human decision on whether/how to extend the filter to
     apa-category listings, not something to change unilaterally mid
     check-in. If you hit another "room for rent" or "private attached
     bath" posting under apa, it's the same failure mode, not a one-off.
