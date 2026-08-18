"""Flag building: results → queue-able flags.

A flag is raised for every result the LAB flagged abnormal (or, with no lab
flag, outside the lab's stated range — shown as such) and for every
abstained/quarantine-derived "check-yourself" item. Suppression is applied
downstream at queue time and only ever from human dispositions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..extraction.records import ExtractedResult
from . import severity as sev
from .grace import GraceMatrix, parse_hl7_timestamp


def build_flag(res: ExtractedResult, matrix: GraceMatrix,
               reported_at_raw: str | None,
               now: datetime | None = None) -> dict | None:
    """Returns a flags-table row dict, or None when no flag is warranted.
    Preliminary results (OBX-11=P) still flag — they are lower-trust for
    suppression, never for alerting."""
    tier, reason = sev.classify(res)
    if tier == sev.SEVERITY_NONE:
        return None

    now = now or datetime.now(timezone.utc)
    is_check = tier == sev.SEVERITY_CHECK_YOURSELF
    reported_at = parse_hl7_timestamp(reported_at_raw) or now
    deadline = None if is_check else matrix.deadline(tier, res.analyte_canonical, reported_at)

    return {
        "severity_tier": tier,
        "flag_reason": reason,
        "is_check_yourself": is_check,
        "grace_deadline": deadline.isoformat() if deadline else None,
        "overdue": bool(deadline and now > deadline),
    }
