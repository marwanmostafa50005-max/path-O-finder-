"""Versioned clinician-editable configs.

Each named config (grace_matrix, citation_map, settings) lives in
config_versions; the bundled resources/*.yaml files seed the first version.
Every edit is validated BEFORE it is stored, then versioned + audited via
Repository.save_config.
"""

from __future__ import annotations

import io
import json

from ruamel.yaml import YAML

from ..db.repository import Repository
from ..detection import grace
from ..guidelines import citations

VALIDATORS = {
    "grace_matrix": grace.parse_and_validate,
    "citation_map": citations.parse_and_validate,
}

DEFAULTS = {
    "grace_matrix": grace.load_default_yaml,
    "citation_map": citations.load_default_yaml,
    "settings": lambda: DEFAULT_SETTINGS_YAML,
}

DEFAULT_SETTINGS_YAML = """\
# path-O-finder practice settings
watched_folder: ""            # secure-messaging drop folder (read-only copy source)
source_adapter: generic       # medical-objects | healthlink | argus | referralnet | generic
closed_loop_mode: inbox       # inbox | recall
closed_loop_strictness: strict  # strict | lenient
ocr_confidence_gate: 80
vlm_enabled: auto             # auto | on | off
overnight_build_hour: 5
"""


def _validate_settings(yaml_text: str) -> dict:
    yaml = YAML(typ="safe")
    data = yaml.load(io.StringIO(yaml_text)) or {}
    if data.get("closed_loop_mode") not in ("inbox", "recall"):
        raise ValueError("closed_loop_mode must be 'inbox' or 'recall'")
    if data.get("closed_loop_strictness") not in ("strict", "lenient"):
        raise ValueError("closed_loop_strictness must be 'strict' or 'lenient'")
    gate = data.get("ocr_confidence_gate")
    if not isinstance(gate, (int, float)) or not (0 <= gate <= 100):
        raise ValueError("ocr_confidence_gate must be between 0 and 100")
    if data.get("vlm_enabled") not in ("auto", "on", "off"):
        raise ValueError("vlm_enabled must be auto|on|off")
    return data


VALIDATORS["settings"] = _validate_settings


class ConfigStore:
    def __init__(self, repo: Repository):
        self.repo = repo

    def get_yaml(self, name: str) -> str:
        stored = self.repo.load_config(name)
        if stored is not None:
            return stored
        return DEFAULTS[name]()

    def get(self, name: str) -> dict:
        yaml = YAML(typ="safe")
        return yaml.load(io.StringIO(self.get_yaml(name))) or {}

    def save(self, name: str, yaml_text: str, initials: str) -> None:
        """Validate then store as a new version (audited). Invalid YAML never
        replaces the live config."""
        validator = VALIDATORS.get(name)
        if validator:
            validator(yaml_text)
        self.repo.save_config(name, yaml_text, initials)

    def settings_json(self) -> str:
        return json.dumps(self.get("settings"), sort_keys=True)
