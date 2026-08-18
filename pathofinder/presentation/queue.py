"""Morning queue: ranked SEVERITY × TIME-ELAPSED, grouped per patient.

Ranking (documented, tunable):

    score = severity_weight * f(time_elapsed_vs_grace)         [confident items]
    score = CHECK_YOURSELF_OFFSET + small_age_term             [abstained items]

where f = 1 + elapsed_fraction_of_grace (capped), so a critical result one
day into a 24h grace outranks a borderline one week into a 168h grace.
Check-yourself / low-confidence items receive a large NEGATIVE offset so they
ALWAYS sink to the bottom regardless of severity: an abstained item can never
outrank a confidently-read abnormal (invariant-tested).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

SEVERITY_WEIGHTS = {
    "critical": 1000.0,
    "high": 100.0,
    "borderline": 10.0,
}
CHECK_YOURSELF_OFFSET = -1_000_000.0
LOW_CONFIDENCE_THRESHOLD = 0.80
MAX_ELAPSED_FACTOR = 10.0


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def score_flag(flag: dict, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    confident = (not flag.get("is_check_yourself")
                 and (flag.get("confidence") or 0.0) >= LOW_CONFIDENCE_THRESHOLD
                 and flag.get("coherence_status", "ok") == "ok")

    created = _parse_iso(flag.get("result_created_at")) or now
    age_hours = max(0.0, (now - created).total_seconds() / 3600)

    if not confident:
        # Bottom of queue always; older abstentions float slightly upward
        # within the bottom band so nothing lingers forever unseen.
        return CHECK_YOURSELF_OFFSET + min(age_hours, 10_000) / 10_000

    weight = SEVERITY_WEIGHTS.get(flag.get("severity_tier", ""), 1.0)
    deadline = _parse_iso(flag.get("grace_deadline"))
    if deadline:
        grace_span = max(1.0, (deadline - created).total_seconds() / 3600)
        elapsed_fraction = min(MAX_ELAPSED_FACTOR, age_hours / grace_span)
    else:
        elapsed_fraction = min(MAX_ELAPSED_FACTOR, age_hours / 168.0)
    return weight * (1.0 + elapsed_fraction)


@dataclass
class PatientGroup:
    patient_id: int | None
    display_name: str
    dob: str | None
    flags: list[dict] = field(default_factory=list)

    @property
    def top_score(self) -> float:
        return max(f["_score"] for f in self.flags)

    @property
    def all_check_yourself(self) -> bool:
        return all(f.get("is_check_yourself") for f in self.flags)


def build_queue(open_flags: list[dict], now: datetime | None = None) -> list[PatientGroup]:
    """Score, group per patient, and order groups. Patient groups containing
    any confident flag rank strictly above groups that are check-yourself
    only — the bottom band stays the bottom band even after grouping."""
    now = now or datetime.now(timezone.utc)
    for f in open_flags:
        f["_score"] = score_flag(f, now)

    groups: dict[object, PatientGroup] = {}
    for f in open_flags:
        key = f.get("patient_id")
        if key not in groups:
            name = ", ".join(x for x in (f.get("family_name"), f.get("given_names")) if x) \
                   or "(patient unidentified — see source)"
            groups[key] = PatientGroup(patient_id=key, display_name=name, dob=f.get("dob"))
        groups[key].flags.append(f)

    for g in groups.values():
        g.flags.sort(key=lambda f: f["_score"], reverse=True)

    return sorted(groups.values(),
                  key=lambda g: (not g.all_check_yourself, g.top_score),
                  reverse=True)
