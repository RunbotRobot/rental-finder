"""Your side of the outreach email -- edited on the site, not in this repo.

Nothing here is committed: the profile lives in the Worker's KV state (see
worker/src/index.js's /api/profile), fetched fresh into a local file before
each run. This module just loads that file into a plain, safe-by-default
object.

The `disclosure_text` field is the one rule this module enforces: it's
yours, written in your own words (ideally after talking to a tenant/reentry
legal aid organization -- see README), never generated or edited by this
tool. Without it, `is_complete()` is False, `email_draft.build_draft`
refuses to produce anything, and nothing downstream can send or even draft
an email -- deliberately, since sending your history in your own words was
the explicit choice this project was built around, not a default to fall
back from.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ApplicantProfile:
    name: str = ""
    phone: str = ""
    email: str = ""  # shown in the signature; can differ from the Gmail address actually sending
    move_in_date: str = ""
    income_text: str = ""  # your own words, e.g. "$3,800/month starting September at ..."
    employment_text: str = ""
    disclosure_text: str = ""  # your own words -- see module docstring

    def is_complete(self) -> bool:
        return bool(self.name.strip() and self.disclosure_text.strip())


_FIELDS = ("name", "phone", "email", "move_in_date", "income_text", "employment_text", "disclosure_text")


def load_profile(path: str | Path) -> ApplicantProfile:
    path = Path(path)
    if not path.exists():
        return ApplicantProfile()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring unreadable profile %s: %s", path, exc)
        return ApplicantProfile()
    return ApplicantProfile(**{name: str(data.get(name, "")) for name in _FIELDS})
