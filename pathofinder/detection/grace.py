"""Grace matrix: per-analyte, per-severity hours before a flag is overdue.

Ships as a clinician-editable YAML (resources/grace_matrix.yaml, DRAFT).
The live copy is versioned in config_versions; this module loads whichever
is current, validates it against a schema, and computes deadlines.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

from ruamel.yaml import YAML

from .. import paths

VALID_SEVERITIES = {"critical", "high", "borderline"}


class GraceMatrixError(ValueError):
    pass


def load_default_yaml() -> str:
    return (paths.resources_dir() / "grace_matrix.yaml").read_text(encoding="utf-8")


def parse_and_validate(yaml_text: str) -> dict:
    yaml = YAML(typ="safe")
    data = yaml.load(io.StringIO(yaml_text))
    if not isinstance(data, dict):
        raise GraceMatrixError("grace matrix must be a mapping")
    defaults = data.get("defaults")
    if not isinstance(defaults, dict) or not defaults:
        raise GraceMatrixError("grace matrix needs a 'defaults' section")
    for sev in VALID_SEVERITIES:
        if sev not in defaults:
            raise GraceMatrixError(f"defaults missing severity '{sev}'")
    for sev, spec in defaults.items():
        if sev not in VALID_SEVERITIES:
            raise GraceMatrixError(f"unknown severity '{sev}' in defaults")
        _validate_hours(spec, f"defaults.{sev}")
    for analyte, spec in (data.get("per_analyte") or {}).items():
        if not isinstance(spec, dict):
            raise GraceMatrixError(f"per_analyte.{analyte} must be a mapping")
        for sev, s in spec.items():
            if sev not in VALID_SEVERITIES:
                raise GraceMatrixError(f"unknown severity '{sev}' under per_analyte.{analyte}")
            _validate_hours(s, f"per_analyte.{analyte}.{sev}")
    return data


def _validate_hours(spec, where: str) -> None:
    if not isinstance(spec, dict) or "grace_hours" not in spec:
        raise GraceMatrixError(f"{where} must contain grace_hours")
    h = spec["grace_hours"]
    if not isinstance(h, (int, float)) or h <= 0 or h > 24 * 365:
        raise GraceMatrixError(f"{where}.grace_hours must be a positive number of hours (≤ 1 year)")


class GraceMatrix:
    def __init__(self, data: dict):
        self.data = data

    @classmethod
    def from_yaml(cls, yaml_text: str) -> "GraceMatrix":
        return cls(parse_and_validate(yaml_text))

    @classmethod
    def default(cls) -> "GraceMatrix":
        return cls.from_yaml(load_default_yaml())

    @property
    def version(self) -> str:
        return str(self.data.get("version", "?"))

    def grace_hours(self, severity: str, analyte_canonical: str | None) -> float | None:
        """None for severities with no deadline (check_yourself/none —
        check-yourself items are queued by abstention, not by clock)."""
        if severity not in VALID_SEVERITIES:
            return None
        per = (self.data.get("per_analyte") or {})
        if analyte_canonical and analyte_canonical in per:
            spec = per[analyte_canonical].get(severity)
            if spec:
                return float(spec["grace_hours"])
        return float(self.data["defaults"][severity]["grace_hours"])

    def deadline(self, severity: str, analyte_canonical: str | None,
                 reported_at: datetime) -> datetime | None:
        hours = self.grace_hours(severity, analyte_canonical)
        if hours is None:
            return None
        return reported_at + timedelta(hours=hours)


def parse_hl7_timestamp(ts: str | None) -> datetime | None:
    """YYYYMMDD[HHMM[SS]] → aware UTC datetime (labs send local; treated as
    naive-local → UTC-naive comparison is avoided by consistent use)."""
    if not ts:
        return None
    ts = ts.strip().split("+")[0].split("-")[0]
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d"):
        try:
            return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
