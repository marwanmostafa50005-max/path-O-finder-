"""Severity tiers derived from the LAB'S OWN OBX-8 flags (HL7 table 0078).

The software computes no clinical interpretation: severity is a display/
ordering tier mapped mechanically from the lab's flag. If OBX-8 is absent,
the value may be compared against the LAB-SUPPLIED reference range ONLY to
decide whether to SHOW the item — presented as "outside the lab's stated
range", never as our judgement — and any ambiguity → check-yourself.
"""

from __future__ import annotations

from ..extraction.records import (ABNORMAL_FLAGS, CHANGE_INDICATOR_FLAGS,
                                  CRITICAL_FLAGS, ExtractedResult, NORMAL_FLAGS)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_BORDERLINE = "borderline"
SEVERITY_NONE = "none"
SEVERITY_CHECK_YOURSELF = "check_yourself"


def classify(res: ExtractedResult) -> tuple[str, str]:
    """Returns (severity_tier, reason). reason always names the lab as the
    source of the abnormality assertion."""
    if res.abstained or res.coherence_status == "conflict":
        return SEVERITY_CHECK_YOURSELF, (res.abstain_reason
                                         or "extraction could not be verified")

    reps = {r.strip().upper() for r in (res.lab_abnormal_flag or "").split("~") if r.strip()}
    substantive = reps - CHANGE_INDICATOR_FLAGS

    if substantive & CRITICAL_FLAGS:
        hit = sorted(substantive & CRITICAL_FLAGS)
        return SEVERITY_CRITICAL, f"lab flagged {'~'.join(hit)} (critical)"
    if substantive & ABNORMAL_FLAGS:
        hit = sorted(substantive & ABNORMAL_FLAGS)
        return SEVERITY_HIGH, f"lab flagged {'~'.join(hit)}"
    if substantive & NORMAL_FLAGS:
        return SEVERITY_NONE, "lab flagged N (normal)"
    if substantive:
        # Unknown flag code preserved verbatim — cautious path: show it.
        return SEVERITY_BORDERLINE, f"lab flag '{'~'.join(sorted(substantive))}' (unrecognised code, shown verbatim)"

    # No OBX-8 at all: range comparison for SHOW/HIDE only.
    if res.value_num is not None and (res.ref_low is not None or res.ref_high is not None):
        below = res.ref_low is not None and res.value_num < res.ref_low
        above = res.ref_high is not None and res.value_num > res.ref_high
        if below or above:
            return SEVERITY_BORDERLINE, "outside the lab's stated range (no lab flag present)"
        return SEVERITY_NONE, "within the lab's stated range"

    if res.value_num is None and res.value_raw:
        return SEVERITY_NONE, "non-numeric report content, no lab flag"
    return SEVERITY_CHECK_YOURSELF, "no lab flag and no usable range — needs human eyes"
