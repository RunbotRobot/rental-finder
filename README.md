# rental-finder

A personal tool for pre-screening King County rental listings against two
constraints at once:

1. **Affordability** — rent at or below a cap you set.
2. **Proximity** — distance from the listing to the nearest school, park,
   and licensed childcare facility, checked at several buffer distances
   since there's often no single documented rule to target.

It produces a ranked CSV for you to review by hand. **It does not contact
any landlord, submit any application, or make any compliance decision on
its own** — it exists to cut down how many listings you have to manually
chase down and rule out.

## Why several buffer distances instead of one

There's frequently no single written proximity rule to build against —
supervision terms are often silent on the exact distance, leaving it to a
CCO's judgment case by case. Guessing one number and filtering everything
else out would either be needlessly restrictive or, worse, quietly wrong.
Instead, the report shows whether each listing clears **500 ft, 1000 ft,
1/4 mile, and 1/2 mile** buffers around schools, parks, and licensed
childcare facilities (`rental_finder/config.py` — `buffer_tiers_ft`), so you
can see how much inventory survives at each tier and take that — not a
guess — into the conversation with your CCO about what buffer they'll
actually apply.

**This tool cannot tell you whether an address will be approved.** Treat
every result as a starting point for that conversation, not an answer.

## What it does

1. Fetches current listings from Craigslist (apartments + rooms categories)
   around a given postal code / radius, filtered to your rent cap.
2. Flags likely spam/scam posts (heuristics: scam phrasing, duplicate
   postings, price outliers, missing location info) — flags are signals for
   you to weigh, not automatic rejections.
3. Geocodes each listing's address text via the free US Census geocoder,
   falling back to OpenStreetMap/Nominatim.
4. Checks distance from each listing to the nearest school, park, and
   licensed childcare facility, using:
   - King County GIS's "School Sites" layer (public **and** private schools)
   - King County GIS's countywide parks layer (city, county, and state park
     sites, including Seattle's)
   - WA DCYF's open dataset of licensed childcare/school-age providers
     (King County GIS doesn't publish its own childcare layer)
5. Writes a ranked CSV (`candidates.csv` by default) — cleanest, most
   affordable, most likely-compliant listings first, with distances, a map
   link, and spam flags for every row so you can sanity-check anything.

A failed distance check is always reported as **unknown**, never as a silent
pass — see `rental_finder/compliance.py` for why that distinction matters
here.

## Usage

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m rental_finder.main --out candidates.csv --max-rent 1900 --postal 98188 --radius-miles 25 -v
```

Open `candidates.csv` and review it yourself — check `location_precision`
before trusting any row's distance numbers (`geocoded` rows are
approximate; verify anything promising against an actual map before
treating it as a candidate).

## Limitations, read before relying on this

- **Craigslist's HTML changes.** The scraper's selectors
  (`rental_finder/sources/craigslist.py`) may need updating if Craigslist
  changes their page structure; it logs a warning rather than failing
  silently if it finds zero results.
- **Geocoding vague addresses is imprecise.** A neighborhood name geocodes
  to a rough centroid, not the actual building. Distance numbers for
  `geocoded` (vs. `exact`) rows should be treated as approximate — worth a
  manual map check before ruling a listing in or out.
- **This is not legal advice and not a compliance guarantee.** It's a
  filter to reduce manual effort, built from public facility-location data
  that may be incomplete or out of date. Always confirm any specific
  address with your CCO before treating it as viable.
- **Rate limiting.** Requests are deliberately slow and low-volume
  (`config.py` — `request_delay_seconds`) — this is built for one person's
  periodic personal search, not a bulk crawl. Don't lower it.
