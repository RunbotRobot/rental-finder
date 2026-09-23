# rental-finder

A personal tool for pre-screening King County rental listings against two
constraints at once:

1. **Affordability** — rent at or below a cap you set.
2. **Proximity** — measured distance from the listing to the nearest
   school, park, and licensed childcare facility, reported at several buffer
   distances side by side, since there's often no single written rule to
   target.

It pulls listings from Craigslist and (optionally) RentCast, produces a
ranked CSV/site for you to review, and — only for listings that clear a
deterministic, auditable set of checks and only with your own pre-written
disclosure text — **can draft, or automatically send, an outreach email**.
It still makes no compliance decision on its own, and it never decides
*what* to disclose or *whether* to; see **Outreach and auto-send** below
for exactly what "automatic" means here and where the hard stops are.

## Why several buffer distances instead of one

Supervision conditions are often silent on an exact distance, leaving it
to a CCO's judgment. Guessing one number and filtering on it would be
either needlessly restrictive or quietly wrong. So the report shows, for
each listing, whether it clears **500 ft, 1000 ft, 1/4 mile, and 1/2 mile**
of every facility type (`buffer_tiers_ft` in `rental_finder/config.py`),
and the run summary counts how many clean, located listings survive at
each tier. That's the thing to bring to your CCO: *"at 1000 ft there are
nine candidates; at a quarter mile there are two"* is a conversation about
a real tradeoff, not a hypothetical.

**This tool cannot tell you whether an address will be approved.** Every
result is a starting point for that conversation, not an answer.

## What it does

1. Fetches current Craigslist listings (apartments + rooms) around a postal
   code, within your rent cap, plus (if `RENTCAST_API_KEY` is set) active
   long-term rentals from [RentCast](https://www.rentcast.io/api), a paid
   structured-data API — skipped entirely, no error, if no key is
   configured.
2. Fetches each new Craigslist listing's own page for the full description,
   post date, bedroom count, and street address if the poster gave one
   (capped per run and cached, so day-to-day runs only fetch what's new).
   RentCast listings already come with a real address and coordinates from
   the provider, so there's nothing to fetch.
3. Flags likely spam/scam Craigslist posts — wire-transfer language, the
   same canned description under several listings, a listing recycled from
   another state, prices far below the market for its category. Flags are
   weighted signals that sort the junk to the bottom; they never delete
   anything. RentCast listings, from an authenticated structured provider,
   always score 0 — the Craigslist-tuned heuristics don't apply to them.
4. Geocodes Craigslist listings that have a **street address**, via the US
   Census geocoder (with an OpenStreetMap fallback that's only accepted
   when it resolves to a specific building). Listings that only give a
   neighborhood or city are *not* geocoded to a centroid and then measured
   from — they're reported as "unknown" until you get the address from
   the poster (see **Address overrides** below).
5. Drops listings confirmed to be outside King County (the search radius
   reaches into Pierce and Snohomish).
6. Measures distance from each located listing to the nearest:
   - **school** — King County GIS "School Sites" (public **and** private)
   - **park** — King County GIS countywide parks layer (city, county, and
     state park sites, including Seattle's), measured to the park boundary
   - **childcare** — WA DCYF open data: licensed child care *centers* and
     school-age programs, ECEAP preschool sites, and Head Start sites
7. Drafts an outreach email for every listing once your applicant profile
   is complete (see **Outreach and auto-send**), and — only for listings
   that clear every automated check — either sends it or marks it ready to
   send, depending on the `--send-emails` flag.
8. Writes `candidates.csv`, ranked: no spam flags first, then by how many
   buffer tiers the listing clears, then cheapest first. Prints the
   per-tier survivor counts.

Anything the tool couldn't verify — a failed lookup, a listing without a
street address — shows as **unknown**, never as a pass.

## What it does NOT cover — read this

Two categories of real, operating childcare are invisible to every check
in this tool, for two different reasons:

**1. Licensed family home child care (in-home daycares)** isn't in any open
dataset. DCYF only exposes those locations through its interactive
[Child Care Check](https://www.findchildcarewa.org/) tool. Look these up
there by hand.

**2. Parent cooperative preschools are exempt from DCYF licensing
entirely** (WA law excuses parents providing reciprocal, non-commercial
care from needing a license), so DCYF has no authority over them —
**they're absent from Child Care Check too, not just from this tool.**
This isn't theoretical: while testing, a candidate listing at 8500 20th Ave
NE, Seattle came back clearing the childcare check at every tier down to
1,000 ft. Wedgwood Cooperative Preschool, a real operating preschool, is
828 feet away — and it appears in neither the DCYF dataset this tool
queries nor, as far as we could determine, Child Care Check itself.

Both categories are common in exactly the residential neighborhoods where
affordable rentals are, so a listing that clears every check here can
still be next to one. **For any address you're serious about: check Child
Care Check by hand (it has family homes, but not co-ops), AND separately
search an ordinary map for "preschool" and "daycare" near the address**
(co-ops usually show up there as an ordinary business listing even though
they're outside DCYF's system entirely). Do this before an address goes
anywhere near your CCO — expect your CCO to do the same, and expect them
to find things this tool can't.

A related caution: if you use an AI chatbot to sanity-check an address the
way you'd use this tool, verify anything it tells you against a real
source before trusting it. One check during testing confidently named a
specific nonexistent address for a real nearby preschool — right
conclusion, fabricated evidence. Coordinates and distances from a chatbot
with no tool behind them are guesses dressed up as facts.

Other things a CCO might count that this tool doesn't measure: school bus
stops, libraries, community centers, pools, churches with youth programs,
private playgrounds. If your CCO names a category, ask; some of these have
public datasets that could be added.

## Outreach and auto-send

This tool can email a landlord for you. Read this whole section before
turning it on — the design choices here were deliberate and matter.

**Eligibility is a fixed checklist; drafting and sending are not.** Code
can't exercise judgment about whether an email reads naturally, so this
project splits the two: a deterministic, auditable gate (`outreach.py`)
decides *which* listings are safe to contact automatically, and a Claude
session — asked to check in by you, not a line of this codebase —
personally writes and sends the email for each one. A listing is marked
**"ready to send"** only when *every one* of these is true —

- the listing came from **RentCast**, never Craigslist. Craigslist has no
  real, stable contact address — only its own JS "reply" widget, which for
  housing posts is usually an in-page message box, not something a script
  can submit on your behalf. A Craigslist listing that clears every other
  rule below still gets drafted (see **Craigslist outreach** below for how)
  — it's only the *sending* that's never automatic for this source.
- it has a real contact email from the listing provider
- it has a verified street address (never a geocoded guess)
- it has zero spam flags
- it clears every enabled facility type at `auto_send_buffer_ft` (default
  1000 ft; independent of the tiers shown in the report)
- it hasn't been emailed before (tracked on the site, so a rerun never
  double-contacts anyone)
- **your applicant profile is complete** — specifically, has your own
  disclosure text (see below)

Anything that fails even one of these gets a drafted email anyway, marked
with the specific reason it isn't gate-eligible, instead of a silent skip.

**Who actually sends it, and when.** This runs when you ask for it, not on
a schedule. Message a Claude Code session in this repo (any time — there's
no fixed cadence) something like "check for outreach candidates." It reads
candidates through a narrow, read-mostly `AGENT_TOKEN` (see Setup below —
deliberately *not* the same token the site uses, so if it were ever
exposed it can't touch your review state, your profile, or the raw scan
data), and handles each one of two ways:

- **RentCast, gate-eligible** ("ready to send"): writes the email itself —
  real per-listing phrasing, not a template, dropping irrelevant profile
  fields rather than mechanically inserting them — and sends it directly
  through the connected Gmail account, no draft-then-approve step.
- **Craigslist, eligible except for having no automatable contact**: writes
  a message sized for Craigslist's reply box and saves it back to the site
  (same real-judgment drafting, no template) for you to send yourself —
  see **Craigslist outreach** below. It never touches Craigslist itself;
  there's nothing here that could.

An unattended, recurring version of the sending half (a session waking
itself on a timer, indefinitely, to send real email with no one present)
was tried first and refused by the coding environment's own safety
controls, independent of any setting in this repo — that's a reasonable
line to hold given what's being automated, so the fallback is manual: you
decide when a check-in happens, which also means nothing gets sent at a
moment you didn't choose to trigger. Eligible listings simply queue up
("ready to send" on the site, or with a stale/no draft for Craigslist)
until you ask.

The Gmail SMTP path (`mailer.py`, the `--send-emails` flag) still exists
in the code but is no longer used by the live flow — it's kept for local
testing of that mechanism only. The scheduled Action never sends email; it
only computes and publishes which listings are eligible.

**Craigslist outreach.** Every Craigslist listing with a complete profile
gets a draft the moment the scan runs — from `email_draft.py`'s plain
template, so it's there immediately, before any check-in ever happens.
That template only ever inserts data this tool has verified (address,
price, bedrooms) plus your own profile text unchanged, so it's safe but
sometimes reads mechanically (it includes your whole employment/income
text as its own paragraph, verbatim, whether or not it's relevant to this
particular listing — a template can't make that judgment call). A Claude
check-in replaces it with a personally-written one when it gets to that
listing; the site always shows whichever is newer, labeled "personally
drafted" or "auto-drafted template" so you know which you're looking at.
Either way, on each listing's card:

- **view draft** shows the message (Craigslist's reply box has no subject
  line, so only the body matters here) and a running character count
  against ~4,000 characters — Craigslist's own limit on that box, not this
  project's, and an estimate this tool has never had the chance to measure
  against a real send. If your box shows a different limit, or no counter
  at all, trust what's actually in front of you over this number.
- **copy draft** copies just that body, ready to paste.
- **reply on Craigslist** opens the listing's own page in a new tab. It
  can't jump straight to the reply box itself — that widget has no
  separate URL, it's rendered by Craigslist's own JS on top of the same
  page — so you'll still click "reply" there yourself.
- **mark replied** flips the listing to the same "✓ emailed" state RentCast
  listings get after a real send. This is the one step nothing here can do
  for you (there's no way to script Craigslist's box), so it's a manual
  button rather than something a check-in sets on its own — a check-in
  will draft a Craigslist listing again next time if you never mark it.

**The disclosure paragraph is yours, not this tool's — and not the
drafting session's either.** Fill in your profile once on the site (✎
profile). Every email — sent by a Claude session or manually copied for
Craigslist — includes your disclosure text verbatim, in your own words.
No part of this project, human-templated or agent-drafted, will rewrite,
edit, or suggest that paragraph. Consider having it reviewed by a
tenant/reentry legal aid organization before relying on it — e.g. King
County's **Housing Justice Project** or **Civil Survival Project** — since
what's wise to say and when can depend on the specific city.

**Know the legal landscape before you decide what to say.** Seattle's Fair
Chance Housing Ordinance (SMC 14.09) has a carve-out specifically for
adult registered sex offenders: unlike other criminal history, a landlord
there *can* screen the registry and *can* deny tenancy on that basis (with
a "legitimate business reason," which is not a high bar). Since a 2023
Ninth Circuit ruling, Seattle also no longer enforces its ban on landlords
simply asking about criminal history at all. In short: there is no
protected disclosure-timing window in Seattle for this specific situation.
Whether unincorporated King County or other cities in the search radius
(Kent, Tukwila, Federal Way, Renton, ...) have different rules is exactly
the kind of city-by-city question worth a real legal-aid conversation, not
a guess from this README or from any AI chatbot.

**Setup**, all through the site and repo secrets, no code changes:

- **RentCast** (optional, needed for any auto-send at all): create an
  account at rentcast.io, generate an API key, add it as the GitHub repo
  secret `RENTCAST_API_KEY`. One search call returns up to 500 listings
  with full contact info already included — no per-listing follow-up
  calls — so the free tier (~50 calls/mo) comfortably covers **one King
  County search a day**. The scheduled Action runs every 6 hours, which
  would burn the free tier 2–3x over if it called RentCast on every run,
  so it doesn't: `cache.py` gates RentCast to once per calendar day
  regardless of how often the Action fires (Craigslist, which has no
  quota, still runs on the full schedule). A run that skips the fetch
  still shows the previous fetch's RentCast listings on the site rather
  than dropping them for the rest of the day. Force an extra fetch the
  same day with `--force-rentcast` if you're deliberately testing.
- **Agent access** (needed for a Claude session to draft/send at all): in
  the Cloudflare dashboard, add a second Worker secret `AGENT_TOKEN` — a
  different long random string from `API_TOKEN`, not shared with GitHub.
  A Claude Code session doing an outreach check-in holds this token for
  the life of that session, since it calls `/api/agent/candidates`,
  `/api/agent/draft`, and `/api/emailed`; that's the reason it's a
  separate, narrow credential rather than the site's full-access one --
  it still can't touch review state, the profile editor, or raw scan data.
- **Gmail sending**: no setup needed for the live flow — a Claude session
  sends through its already-connected Gmail integration. The
  `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` secrets and the App Password flow
  are only relevant if you want to locally test `mailer.py`'s SMTP path
  (`--send-emails`) directly; skip them otherwise.
- **Applicant profile**: open the site → ✎ profile → fill in name,
  contact info, employment/income in your own words, and disclosure text.
  Nothing drafts or sends until this is saved with disclosure text filled
  in.

## Usage

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m rental_finder.main --out candidates.csv --max-rent 1900 --postal 98188 --radius-miles 25 -v
```

This never sends email regardless of configured credentials — add
`--send-emails` explicitly to actually send (the scheduled Action does;
a local run shouldn't, unless you mean to test a real send).

The first run is slow: it fetches up to 150 listing pages (`--max-detail-fetches`)
with a 3-second pause between each, then geocodes and distance-checks
every located listing. Later runs reuse `cache.json` and only do that work
for new listings. If Craigslist starts refusing requests, the run stops
fetching pages and finishes with what it has; try again in a few hours.

Open `candidates.csv` and read `location_precision` before trusting any
row: `address` rows were measured from a real street address; `area` rows
weren't measured at all.

### Address overrides

Many posters only give the address once you contact them. Put those in
`address_overrides.csv`:

```
source_id,address
9b2PK1KjrBfu72ouovYfRD,2619 5th Avenue, Seattle, WA
```

(`source_id` is the last path segment of the listing URL, and is in the
CSV.) The next run geocodes and distance-checks those listings like any
other.

## Running it as a website (phone-friendly)

The scan can't run in a browser, so the site is three parts: a scheduled
GitHub Action runs the scan, a Cloudflare Worker serves the results page
and stores your review state (starred/dismissed, notes, addresses you get
from posters), and the Action feeds those addresses back into the next
scan. Nothing is public — one shared token gates everything.

**1. Worker** (`worker/`) — no terminal needed. In the Cloudflare
dashboard: Workers & Pages → Create → Import a repository → pick this
repo, branch `main`, **root directory `worker`**, build command left
default (`npx wrangler deploy`). It deploys on every push to `main`.
`wrangler.toml` already names the KV namespace. Then under the Worker's
Settings → Variables and Secrets add a secret `API_TOKEN` — a long random
string (a password manager's generator is fine); keep it. (Or from a
terminal: `cd worker && npx wrangler secret put API_TOKEN && npx wrangler deploy`.)

**2. GitHub repo secrets** (Settings → Secrets and variables → Actions):
`WORKER_URL` = the Worker's URL with no trailing slash, `API_TOKEN` = the
same token.

**3. Run it once** from the Actions tab (`scan` → Run workflow); after that
it runs every six hours. The Action commits `cache.json` to the repo — that
file is what makes "new since last run" work — so expect a bot commit per
run.

Open the site on your phone, paste the token once (it's stored on the
device, nowhere else), and add it to your home screen. The tiles at the
top are the per-tier survivor counts. On each card: star, dismiss, a note,
an address field for when a poster gives you one (the next scan geocodes
and distance-checks it), and — once a draft exists — a "view draft" /
"copy draft" button and a line showing whether it was auto-sent, is ready
to be, or wasn't and why. The ✎ profile button holds your applicant
profile (see **Outreach and auto-send**).

If Craigslist blocks GitHub's runners, the Action's log will show HTTP 403
on the search fetch; the fallback is to run `python -m rental_finder.main
--json data.json` on a home machine and `PUT` the file to
`$WORKER_URL/api/data` with the token, exactly as the workflow does.

## Limitations, read before relying on this

- **Not legal advice, not a compliance guarantee.** Public facility data
  can be incomplete or stale, and the family-home and co-op childcare gaps
  above are real. Confirm every specific address with your CCO before
  treating it as viable, and see **Outreach and auto-send** for the
  disclosure/legal caveats around emailing landlords.
- **An email is not a compliance check.** Auto-send only verifies the
  things this tool can verify (distance, spam score, a real contact). It
  does not know your CCO's actual buffer, and clearing every check here is
  not the same as an address being approved.
- **Craigslist's HTML changes.** Selectors live in
  `rental_finder/sources/craigslist.py`; the tool warns rather than failing
  silently if it finds zero results.
- **Craigslist's own map pins are coarse** (verified live: often a
  neighborhood centroid, sometimes wrong), so they're used only to work out
  which county a listing is in, never for distances.
- **RentCast has no public listing-page URL in its data**, so RentCast
  cards link to a map search of the address instead of a real listing page.
- **Rate limiting is deliberate.** `request_delay_seconds` and
  `max_detail_fetches` keep this looking like what it is — one person's
  periodic search. Don't lower them.
