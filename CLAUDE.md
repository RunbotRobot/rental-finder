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
- Outreach emails (`email_draft.py`, `outreach.py`, `mailer.py`) are gated
  by deterministic, auditable rules only — never a model's self-reported
  confidence. Auto-send applies to RentCast listings alone (Craigslist has
  no real, scriptable contact address); see `outreach.py`'s docstring.
- The disclosure paragraph in an outreach email is the applicant's own
  words from their profile, verbatim. This tool must never draft, edit, or
  suggest that paragraph, or send/draft anything when it's missing.
- A plain local run of `main.py` must never send real email regardless of
  configured credentials — only an explicit `--send-emails` flag (used
  solely by the scheduled Action) allows a send.
