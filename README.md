# rental-finder

A personal tool for pre-screening King County rental listings against two
constraints at once:

1. **Affordability** — rent at or below a cap you set.
2. **Proximity** — measured distance from the listing to the nearest
   school, park, and licensed childcare facility, reported at several buffer
   distances side by side, since there's often no single written rule to
   target.

It produces a ranked CSV for you to review by hand, plus a short summary of
how many candidates survive at each buffer distance. **It does not contact
any landlord, submit any application, or make any compliance decision on
its own.** Its job is to cut the pile of listings you'd otherwise have to
rule out one at a time, and to hand you numbers instead of guesses for the
conversation with your CCO.

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
   code, within your rent cap.
2. Fetches each new listing's own page for the full description, post date,
   bedroom count, and street address if the poster gave one (capped per run
   and cached, so day-to-day runs only fetch what's new).
3. Flags likely spam/scam posts — wire-transfer language, the same canned
   description under several listings, a listing recycled from another
   state, prices far below the market for its category. Flags are weighted
   signals that sort the junk to the bottom; they never delete anything.
4. Geocodes listings that have a **street address**, via the US Census
   geocoder (with an OpenStreetMap fallback that's only accepted when it
   resolves to a specific building). Listings that only give a
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
7. Writes `candidates.csv`, ranked: no spam flags first, then by how many
   buffer tiers the listing clears, then cheapest first. Prints the
   per-tier survivor counts.

Anything the tool couldn't verify — a failed lookup, a listing without a
street address — shows as **unknown**, never as a pass.

## What it does NOT cover — read this

**Licensed family home child care (in-home daycares) is not in any open
dataset.** DCYF only exposes those locations through its interactive
[Child Care Check](https://www.findchildcarewa.org/) tool. There are far
more family homes than centers, and they're scattered through exactly the
residential neighborhoods where affordable rentals are, so a listing that
clears every check here can still be next door to one. **Look up every
address you're serious about in Child Care Check by hand before it goes
anywhere near your CCO** — and expect your CCO to do the same.

Other things a CCO might count that this tool doesn't measure: school bus
stops, libraries, community centers, pools, churches with youth programs,
private playgrounds. If your CCO names a category, ask; some of these have
public datasets that could be added.

## Usage

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m rental_finder.main --out candidates.csv --max-rent 1900 --postal 98188 --radius-miles 25 -v
```

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

**1. Worker** (`worker/`):

```bash
cd worker
npx wrangler kv namespace create STATE        # paste the printed id into wrangler.toml
openssl rand -hex 32                          # this is your API token; keep it
npx wrangler secret put API_TOKEN             # paste the token
npx wrangler deploy                           # prints the site URL
```

**2. GitHub repo secrets** (Settings → Secrets and variables → Actions):
`WORKER_URL` = the deployed URL with no trailing slash, `API_TOKEN` = the
same token.

**3. Run it once** from the Actions tab (`scan` → Run workflow); after that
it runs every six hours. The Action commits `cache.json` to the repo — that
file is what makes "new since last run" work — so expect a bot commit per
run.

Open the site on your phone, paste the token once (it's stored on the
device, nowhere else), and add it to your home screen. The tiles at the
top are the per-tier survivor counts. On each card: star, dismiss, a note,
and an address field for when a poster gives you one — the next scan
geocodes and distance-checks it.

If Craigslist blocks GitHub's runners, the Action's log will show HTTP 403
on the search fetch; the fallback is to run `python -m rental_finder.main
--json data.json` on a home machine and `PUT` the file to
`$WORKER_URL/api/data` with the token, exactly as the workflow does.

## Limitations, read before relying on this

- **Not legal advice, not a compliance guarantee.** Public facility data
  can be incomplete or stale, and the family-home gap above is real. Confirm
  every specific address with your CCO before treating it as viable.
- **Craigslist's HTML changes.** Selectors live in
  `rental_finder/sources/craigslist.py`; the tool warns rather than failing
  silently if it finds zero results.
- **Craigslist's own map pins are coarse** (verified live: often a
  neighborhood centroid, sometimes wrong), so they're used only to work out
  which county a listing is in, never for distances.
- **Rate limiting is deliberate.** `request_delay_seconds` and
  `max_detail_fetches` keep this looking like what it is — one person's
  periodic search. Don't lower them.
