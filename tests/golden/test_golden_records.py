"""Golden-file tests: the canonical extracted record for representative
messages is pinned as JSON. Any regression in the extraction engine that
changes an emitted record fails here.

To intentionally re-pin after a reviewed change:
    PATHOFINDER_REPIN_GOLDEN=1 python -m pytest tests/golden -q
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pathofinder.extraction import coherence, hl7_tier1, normalize, pit
from tests.fixtures import generator

GOLDEN_DIR = Path(__file__).parent
REPIN = os.environ.get("PATHOFINDER_REPIN_GOLDEN") == "1"


def _canonical_records(msg) -> list[dict]:
    out = []
    for order in msg.orders:
        for res in order.results:
            normalize.normalize_result(res)
            coherence.run_coherence(res)
            rec = res.db_record()
            rec["abstained"] = res.abstained
            rec["abstain_reason"] = res.abstain_reason
            out.append(rec)
    return out


CASES = {
    "golden_simple_abnormal.json": lambda: _canonical_records(
        hl7_tier1.parse_oru(generator.hl7_simple_abnormal())),
    "golden_multi_obr_all_types.json": lambda: _canonical_records(
        hl7_tier1.parse_oru(generator.hl7_multi_obr_all_types())),
    "golden_conflict_flag_vs_range.json": lambda: _canonical_records(
        hl7_tier1.parse_oru(generator.hl7_conflict_flag_vs_range())),
    "golden_pit_standalone.json": lambda: [
        r.db_record() | {"abstained": r.abstained}
        for r in coherence_all(pit.parse_pit(generator.pit_standalone())[0])
    ],
}


def coherence_all(results):
    for r in results:
        normalize.normalize_result(r)
        coherence.run_coherence(r)
    return results


@pytest.mark.parametrize("name", sorted(CASES))
def test_golden(name):
    actual = CASES[name]()
    path = GOLDEN_DIR / name
    if REPIN or not path.exists():
        # Explicit encoding + newline: goldens must be byte-identical across
        # platforms (Windows locale default is cp1252, which mangles UTF-8).
        path.write_text(json.dumps(actual, indent=2, sort_keys=True, ensure_ascii=False),
                        encoding="utf-8", newline="\n")
        if REPIN:
            pytest.skip(f"re-pinned {name}")
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected, f"extracted record drifted from golden file {name}"
