"""Coherence cross-checks — run on EVERY extracted value, all tiers.

If ANY check conflicts the record is marked coherence_status='conflict' and
ABSTAINS (check-yourself). The engine never overrules the lab and never
silently "fixes" a value.

Checks:
  1. value-vs-range agreement WITH the lab's own OBX-8 flag
  2. physiological plausibility hard bounds (resources/plausibility_bounds.yaml)
  3. unit / decimal sanity (unit-vs-analyte compatibility; bounds catch
     misplaced decimals)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ruamel.yaml import YAML

from .. import paths
from .records import (ABNORMAL_FLAGS, CHANGE_INDICATOR_FLAGS, CRITICAL_FLAGS,
                      ExtractedResult, NORMAL_FLAGS, QUALITATIVE_FLAGS)


@lru_cache(maxsize=1)
def _bounds() -> dict:
    yaml = YAML(typ="safe")
    data = yaml.load(Path(paths.resources_dir() / "plausibility_bounds.yaml").read_text(encoding="utf-8"))
    return data.get("analytes") or {}


def _flag_reps(res: ExtractedResult) -> list[str]:
    return [r.strip().upper() for r in (res.lab_abnormal_flag or "").split("~") if r.strip()]


def _norm_unit(u: str) -> str:
    return u.replace(" ", "").replace("µ", "u").lower()


def check_flag_vs_range(res: ExtractedResult) -> str | None:
    """Numeric value inside the lab's own stated range but flagged abnormal
    (or outside it but flagged N) is a conflict — do not overrule the lab."""
    if res.value_num is None or (res.ref_low is None and res.ref_high is None):
        return None
    reps = set(_flag_reps(res))
    substantive = reps - CHANGE_INDICATOR_FLAGS - QUALITATIVE_FLAGS
    if not substantive:
        return None

    below = res.ref_low is not None and res.value_num < res.ref_low
    above = res.ref_high is not None and res.value_num > res.ref_high
    inside = not below and not above

    flagged_abnormal = bool(substantive & (CRITICAL_FLAGS | ABNORMAL_FLAGS))
    flagged_normal = substantive <= NORMAL_FLAGS

    if inside and flagged_abnormal:
        return (f"value {res.value_num} sits inside stated range "
                f"'{res.ref_range_raw}' but lab flagged {'~'.join(sorted(substantive))}")
    if (below or above) and flagged_normal:
        return (f"value {res.value_num} sits outside stated range "
                f"'{res.ref_range_raw}' but lab flagged N")
    return None


def check_plausibility(res: ExtractedResult) -> str | None:
    if res.value_num is None or not res.analyte_canonical:
        return None
    spec = _bounds().get(res.analyte_canonical)
    if not spec:
        return None
    lo, hi = spec.get("min"), spec.get("max")
    if lo is not None and res.value_num < lo:
        return f"value {res.value_num} below physiological hard bound {lo} — extraction error suspected"
    if hi is not None and res.value_num > hi:
        return f"value {res.value_num} above physiological hard bound {hi} — extraction error suspected"
    return None


def check_unit(res: ExtractedResult) -> str | None:
    if not res.analyte_canonical or not res.unit_raw:
        return None
    spec = _bounds().get(res.analyte_canonical)
    if not spec:
        return None
    expected = [_norm_unit(str(u)) for u in (spec.get("expected_units") or []) if str(u)]
    if not expected:
        return None
    if _norm_unit(res.unit_raw) not in expected:
        return (f"unit '{res.unit_raw}' incompatible with {res.analyte_canonical} "
                f"(expected one of {spec.get('expected_units')})")
    return None


def run_coherence(res: ExtractedResult) -> ExtractedResult:
    """Apply all checks; first conflict abstains the record."""
    if res.abstained:
        return res
    for check in (check_unit, check_plausibility, check_flag_vs_range):
        conflict = check(res)
        if conflict:
            return res.abstain(conflict)
    return res
