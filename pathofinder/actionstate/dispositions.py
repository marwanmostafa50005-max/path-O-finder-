"""Disposition domain rules (the write path lives in db/repository.py —
add_disposition is the ONLY code path that creates suppression rows).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

DISPOSITION_TYPES = ("handled", "watching", "not-relevant", "escalate", "check-done")

# Sensible suppression scope per disposition type. "watching" is typically
# time-boxed by the clinician (e.g. "watching this ferritin for 3 months").
DEFAULT_SCOPE = {
    "handled": "this_result",
    "watching": "patient_analyte",
    "not-relevant": "patient_analyte",
    "escalate": "this_result",
    "check-done": "this_result",
}


def watching_expiry(months: int = 3, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return (now + timedelta(days=30 * months)).isoformat()


def validate(disposition_type: str, operator_initials: str) -> None:
    if disposition_type not in DISPOSITION_TYPES:
        raise ValueError(f"unknown disposition type '{disposition_type}'")
    if not operator_initials or not operator_initials.strip():
        raise ValueError("operator initials are required")
