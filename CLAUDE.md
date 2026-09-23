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
- Outreach *eligibility* (`outreach.py`) is gated by deterministic,
  auditable rules only — never a model's self-reported confidence. A
  listing is only ever marked "ready to send" (RentCast listings alone;
  Craigslist has no real, scriptable contact address) when it clears every
  rule; see `outreach.py`'s docstring.
- Outreach *drafting and sending* is deliberately NOT done by
  `email_draft.py`'s template for the live flow — the owner found the
  templated output choppy (raw profile-field text slotted into fixed
  sentences, e.g. a literal "around When available"). A Claude session,
  woken on a recurring check-in, reads eligible listings via the Worker's
  `AGENT_TOKEN`-gated `/api/agent/candidates` endpoint, personally writes
  each email with real per-listing judgment, and sends it via its
  connected Gmail integration directly (no draft-then-approve step — the
  owner explicitly chose immediate sending). `email_draft.py`/`mailer.py`
  still exist for the Craigslist manual-copy draft and for local testing
  of the SMTP path, but are not part of the live send path. If you are the
  session doing these check-ins: keep drafting real per-listing prose
  (skip irrelevant profile fields, phrase things naturally), never
  reintroduce template-based auto-send as the live mechanism without the
  owner asking for it back.
- The disclosure paragraph in an outreach email is the applicant's own
  words from their profile, verbatim, regardless of who or what drafts the
  rest of the email. Never draft, edit, or suggest that paragraph, and
  never draft or send anything when it's missing.
- A plain local run of `main.py` must never send real email regardless of
  configured credentials — only an explicit `--send-emails` flag (a local
  testing aid only; the scheduled Action never passes it) allows a send
  via the SMTP path.
- `AGENT_TOKEN` is intentionally narrower than `API_TOKEN`: it can only
  read `/api/agent/candidates` and POST `/api/emailed`. Don't widen its
  access without a specific reason — the whole point is that a session
  holding it for outreach check-ins has a small blast radius if exposed.
