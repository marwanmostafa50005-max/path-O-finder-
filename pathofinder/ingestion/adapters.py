"""Thin per-vendor adapters. They know ONLY folder conventions, filename
patterns and batch quirks; everything downstream is source-agnostic.

No adapter ever writes to the vendor's folder or emits an ACK.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class AdapterSpec:
    name: str
    # glob patterns the vendor's client typically writes
    patterns: tuple[str, ...]
    notes: str = ""


class BaseAdapter:
    spec: AdapterSpec

    def file_patterns(self) -> tuple[str, ...]:
        return self.spec.patterns

    @property
    def name(self) -> str:
        return self.spec.name


class MedicalObjectsAdapter(BaseAdapter):
    spec = AdapterSpec(
        name="medical-objects",
        patterns=("*.hl7", "*.HL7", "*.oru", "*.txt", "*"),
        notes="Capricorn client; usually one ORU per .hl7 file, occasional batch",
    )


class HealthLinkAdapter(BaseAdapter):
    spec = AdapterSpec(
        name="healthlink",
        patterns=("*.hl7", "*.enc", "*.txt", "*"),
        notes="HMS client folders (e.g. HLINK/ffprod); batch FHS/BHS envelopes common",
    )


class ArgusAdapter(BaseAdapter):
    spec = AdapterSpec(
        name="argus",
        patterns=("*.hl7", "*.pit", "*.txt", "*"),
        notes="Argus messenger; PIT payloads still seen from some labs",
    )


class ReferralNetAdapter(BaseAdapter):
    spec = AdapterSpec(
        name="referralnet",
        patterns=("*.hl7", "*.rn", "*.txt", "*"),
        notes="Global Health ReferralNet",
    )


class GenericFolderAdapter(BaseAdapter):
    """Fallback for any conformant secure-messaging drop folder."""
    spec = AdapterSpec(name="generic", patterns=("*",))


ADAPTERS: dict[str, type[BaseAdapter]] = {
    a.spec.name: a
    for a in (MedicalObjectsAdapter, HealthLinkAdapter, ArgusAdapter,
              ReferralNetAdapter, GenericFolderAdapter)
}


def get_adapter(name: str) -> BaseAdapter:
    return ADAPTERS.get(name, GenericFolderAdapter)()
