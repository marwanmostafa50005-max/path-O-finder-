"""Guideline layer — POINTER/CITATION-ONLY (TGA-safe by construction).

For HIGH-CONFIDENCE abnormal findings ONLY: guideline name, publisher,
edition/date, section, and the URL as display text. Edition/date is always
shown. No body text, no dose, no patient-specific tailoring — the map is
keyed by analyte concept alone, never filtered by patient age/renal
function/pregnancy/weight (TGA red line ii).

Low-confidence / check-yourself items get NO citation.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ruamel.yaml import YAML

from .. import paths

HIGH_CONFIDENCE_THRESHOLD = 0.80


class CitationMapError(ValueError):
    pass


@dataclass(frozen=True)
class Citation:
    concept: str
    name: str
    publisher: str
    edition: str
    section: str
    url: str

    @property
    def display(self) -> str:
        # Edition/date ALWAYS shown; URL is display text, never fetched.
        return f"{self.name} — {self.publisher}, {self.edition}. Section: {self.section}. {self.url}"


def load_default_yaml() -> str:
    return (paths.resources_dir() / "citation_map.yaml").read_text(encoding="utf-8")


def parse_and_validate(yaml_text: str) -> dict:
    yaml = YAML(typ="safe")
    data = yaml.load(io.StringIO(yaml_text))
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise CitationMapError("citation map must contain an 'entries' list")
    for i, e in enumerate(data["entries"]):
        for key in ("concept", "name", "publisher", "edition", "section", "url"):
            if not e.get(key):
                raise CitationMapError(f"entries[{i}] missing '{key}' (edition/date is mandatory)")
        if not isinstance(e.get("analytes", []), list):
            raise CitationMapError(f"entries[{i}].analytes must be a list")
    cadence = data.get("review_cadence_days")
    if not isinstance(cadence, int) or cadence <= 0:
        raise CitationMapError("review_cadence_days must be a positive integer")
    return data


class CitationMap:
    def __init__(self, data: dict, loaded_at: datetime | None = None):
        self.data = data
        self.loaded_at = loaded_at or datetime.now(timezone.utc)
        self._by_analyte: dict[str, Citation] = {}
        for e in data["entries"]:
            c = Citation(concept=e["concept"], name=e["name"], publisher=e["publisher"],
                         edition=str(e["edition"]), section=e["section"], url=e["url"])
            for analyte in e.get("analytes", []):
                self._by_analyte.setdefault(str(analyte), c)

    @classmethod
    def from_yaml(cls, yaml_text: str) -> "CitationMap":
        return cls(parse_and_validate(yaml_text))

    @classmethod
    def default(cls) -> "CitationMap":
        return cls.from_yaml(load_default_yaml())

    def citation_for(self, flag: dict) -> Citation | None:
        """Pointer for a flag — HIGH-CONFIDENCE abnormal findings only."""
        if flag.get("is_check_yourself"):
            return None
        if (flag.get("confidence") or 0.0) < HIGH_CONFIDENCE_THRESHOLD:
            return None
        if flag.get("coherence_status", "ok") != "ok":
            return None
        if flag.get("severity_tier") not in ("critical", "high", "borderline"):
            return None
        analyte = flag.get("analyte_canonical")
        return self._by_analyte.get(analyte) if analyte else None

    def review_due(self, last_reviewed: datetime | None, now: datetime | None = None) -> bool:
        """Review-cadence reminder: prompt the clinician to re-verify
        editions/URLs every review_cadence_days."""
        now = now or datetime.now(timezone.utc)
        cadence = timedelta(days=int(self.data["review_cadence_days"]))
        anchor = last_reviewed or self.loaded_at
        return now - anchor >= cadence
