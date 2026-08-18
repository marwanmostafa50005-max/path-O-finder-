"""Test-name normalisation: RCPA SPIA seed map + clinician-editable alias table.

If a raw name cannot be confidently normalised it KEEPS its raw name and is
marked for clinician review — a canonical mapping is never guessed.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from ruamel.yaml import YAML

from .. import paths
from .records import ExtractedResult


def _clean(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[\s]+", " ", s)
    s = s.strip(" .:;")
    return s


@lru_cache(maxsize=1)
def _seed_map() -> dict[str, tuple[str, str | None]]:
    """alias(lower) -> (canonical, loinc) from the bundled SPIA seed."""
    yaml = YAML(typ="safe")
    data = yaml.load(Path(paths.resources_dir() / "spia_aliases.yaml").read_text())
    out: dict[str, tuple[str, str | None]] = {}
    for canonical, spec in (data.get("canonical") or {}).items():
        loinc = spec.get("loinc")
        out[_clean(canonical)] = (canonical, loinc)
        for alias in spec.get("aliases") or []:
            out[_clean(str(alias))] = (canonical, loinc)
    return out


def normalize_result(res: ExtractedResult,
                     local_aliases: dict[str, tuple[str, str | None]] | None = None) -> ExtractedResult:
    """Set analyte_canonical/loinc. Local (clinician-maintained) aliases win
    over the SPIA seed. LOINC present on the wire always wins for identity."""
    raw = _clean(res.analyte_raw or "")
    local = { _clean(k): v for k, v in (local_aliases or {}).items() }

    hit = local.get(raw) or _seed_map().get(raw)
    if hit is None and res.loinc:
        for canonical, loinc in _seed_map().values():
            if loinc and loinc == res.loinc:
                hit = (canonical, loinc)
                break
    if hit:
        res.analyte_canonical = hit[0]
        if not res.loinc and hit[1]:
            res.loinc = hit[1]
        res.unit_canonical = res.unit_raw
    else:
        res.analyte_canonical = None      # unmapped: keep raw, mark for review
        res.notes.append("analyte name not confidently normalised — clinician review")
    return res
