"""Tier 1 — deterministic HL7 v2 ORU parsing (the trust anchor).

hl7apy is attempted first for conformance information; the permissive
tokeniser below is the workhorse and NEVER hard-fails on minor
non-conformance. A message that yields nothing usable raises ParseFailure so
the caller quarantines it — silent guessing is the cardinal sin.

Provenance for every value is the segment+field path, e.g. "OBR[1]/OBX[3]-5".
"""

from __future__ import annotations

import base64
import re

from .records import (ExtractedResult, OrderInfo, ParsedMessage, PatientInfo,
                      Provenance, Tier)


class ParseFailure(Exception):
    """Message could not be parsed with confidence → quarantine."""


def _try_hl7apy(text: str) -> bool:
    """Best-effort conformance parse; failure is informational only."""
    try:
        from hl7apy.parser import parse_message
        parse_message(text, find_groups=False)
        return True
    except Exception:
        return False


def _fields(segment: str) -> list[str]:
    return segment.split("|")


def _comp(field: str, idx: int) -> str:
    """1-based component access within a field."""
    parts = field.split("^")
    return parts[idx - 1] if 0 < idx <= len(parts) else ""


def parse_ref_range(raw: str | None) -> tuple[float | None, float | None]:
    if not raw:
        return None, None
    s = raw.strip()
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*$", s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.match(r"^\s*<=?\s*(-?\d+(?:\.\d+)?)\s*$", s)
    if m:
        return None, float(m.group(1))
    m = re.match(r"^\s*>=?\s*(-?\d+(?:\.\d+)?)\s*$", s)
    if m:
        return float(m.group(1)), None
    return None, None


def _parse_numeric(raw: str) -> float | None:
    try:
        return float(raw.strip())
    except (ValueError, AttributeError):
        return None


def _parse_sn(raw: str) -> tuple[str, float | None]:
    """SN: comparator^num1^separator^num2 → display string + best numeric."""
    comparator = _comp(raw, 1)
    num1 = _parse_numeric(_comp(raw, 2))
    sep = _comp(raw, 3)
    num2 = _parse_numeric(_comp(raw, 4))
    display = f"{comparator}{_comp(raw, 2)}"
    if sep and num2 is not None:
        display += f"{sep}{_comp(raw, 4)}"
    return display, num1


def _decode_ed(value: str) -> bytes | None:
    """ED field: source^type^subtype-or-encoding^encoding^data (AU labs vary
    between 4- and 5-component forms). Accept Base64 in comp 4 or 5."""
    comps = value.split("^")
    for enc_idx in (3, 4):
        if enc_idx < len(comps) and comps[enc_idx].strip().upper() == "BASE64":
            data = "^".join(comps[enc_idx + 1:])
            try:
                return base64.b64decode(data, validate=False)
            except Exception:
                return None
    return None


_PIT_MARKER = re.compile(r"^\d{3} ", re.M)


def _looks_like_embedded_pit(identifier: str, text: str) -> bool:
    if "PIT" in identifier.upper():
        return True
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return len(lines) >= 3 and sum(bool(_PIT_MARKER.match(ln)) for ln in lines) >= 3


def parse_oru(text: str) -> ParsedMessage:
    text = text.replace("\r\n", "\r").replace("\n", "\r")
    segments = [s for s in text.split("\r") if s.strip()]
    if not segments or not segments[0].startswith("MSH|"):
        raise ParseFailure("no MSH segment")

    msh = _fields(segments[0])
    if len(msh) < 9 or "^~" not in msh[1]:
        raise ParseFailure("MSH encoding characters malformed")
    control_id = msh[9] if len(msh) > 9 else None

    conformant = _try_hl7apy("\r".join(segments))

    msg = ParsedMessage(control_id=control_id or None, patient=None)
    if not conformant:
        msg.notes.append("hl7apy strict parse failed; permissive tokeniser used")

    current_order: OrderInfo | None = None
    obr_index = 0
    obx_index = 0
    last_result: ExtractedResult | None = None
    malformed: list[str] = []

    for seg in segments[1:]:
        seg_id = seg[:3]
        f = _fields(seg)

        if seg_id == "PID":
            mrn = _comp(f[3], 1) if len(f) > 3 else ""
            name = f[5] if len(f) > 5 else ""
            msg.patient = PatientInfo(
                source_key=mrn or (name + "|" + (f[7] if len(f) > 7 else "")),
                family_name=_comp(name, 1) or None,
                given_names=" ".join(x for x in (_comp(name, 2), _comp(name, 3)) if x) or None,
                dob=(f[7] if len(f) > 7 else "") or None,
                sex=(f[8] if len(f) > 8 else "") or None,
            )

        elif seg_id == "OBR":
            obr_index += 1
            obx_index = 0
            current_order = OrderInfo(
                obr_set_id=(f[1] if len(f) > 1 else "") or str(obr_index),
                filler_order_number=_comp(f[3], 1) if len(f) > 3 else None,
                panel_code=_comp(f[4], 1) if len(f) > 4 else None,
                panel_name=_comp(f[4], 2) if len(f) > 4 else None,
                collected_at=(f[7] if len(f) > 7 else "") or None,
                ordering_provider=(f[16] if len(f) > 16 else "") or None,
                reported_at=(f[22] if len(f) > 22 else "") or None,
                order_status=(f[25] if len(f) > 25 else "") or None,
            )
            msg.orders.append(current_order)

        elif seg_id == "OBX":
            if current_order is None:
                obr_index = obr_index or 1
                current_order = OrderInfo(obr_set_id="implicit")
                msg.orders.append(current_order)
                msg.notes.append("OBX before any OBR — implicit order group created")
            obx_index += 1

            if len(f) < 6:
                malformed.append(f"OBX[{obx_index}] too short: {seg[:60]}")
                continue

            value_type = f[2].strip().upper() if len(f) > 2 else ""
            identifier = f[3] if len(f) > 3 else ""
            sub_id = (f[4] if len(f) > 4 else "") or None
            value = f[5] if len(f) > 5 else ""
            units = _comp(f[6], 1) if len(f) > 6 else ""
            ref_range = f[7] if len(f) > 7 else ""
            flags_raw = f[8] if len(f) > 8 else ""
            status = (f[11] if len(f) > 11 else "").strip() or None

            analyte_text = _comp(identifier, 2) or _comp(identifier, 1)
            loinc = None
            if _comp(identifier, 3).upper() == "LN":
                loinc = _comp(identifier, 1)

            prov = Provenance(
                tier=Tier.HL7, engine="hl7-tier1",
                segment_path=f"OBR[{obr_index}]/OBX[{obx_index}]-5",
            )
            res = ExtractedResult(
                analyte_raw=analyte_text or identifier or "UNKNOWN",
                loinc=loinc,
                obx_value_type=value_type or None,
                obx_result_status=status,
                obx_sub_id=sub_id,
                obx_identifier=identifier or None,
                unit_raw=units or None,
                ref_range_raw=ref_range or None,
                extraction_tier=1,
                confidence=1.0,
                provenance=prov,
            )
            res.ref_low, res.ref_high = parse_ref_range(ref_range)
            # OBX-8 is REPEATING: parse all repetitions, preserve unknown codes verbatim.
            reps = [r.strip() for r in flags_raw.split("~") if r.strip()]
            res.lab_abnormal_flag = "~".join(reps) if reps else None

            if value_type == "NM":
                res.value_raw = value
                res.value_num = _parse_numeric(value)
                if res.value_num is None:
                    res.abstain(f"OBX-2=NM but value '{value}' is not numeric")
            elif value_type == "SN":
                res.value_raw, res.value_num = _parse_sn(value)
            elif value_type in ("ST", "TX", "FT"):
                cleaned = value.replace("\\.br\\", "\n")
                if _looks_like_embedded_pit(identifier, cleaned):
                    current_order.embedded_pit.append(cleaned)
                    res.notes.append("embedded PIT payload routed to PIT parser")
                    res.value_raw = "(embedded PIT report)"
                else:
                    res.value_raw = cleaned
                res.value_num = None
            elif value_type in ("CE", "CWE"):
                res.value_raw = _comp(value, 2) or _comp(value, 1)
            elif value_type == "ED":
                doc = _decode_ed(value)
                if doc is None:
                    res.abstain("ED segment present but payload not decodable Base64")
                else:
                    current_order.embedded_documents.append(doc)
                    res.value_raw = "(embedded document)"
                    res.notes.append("embedded document extracted for Tier-2 reading")
            elif value_type == "RP":
                res.value_raw = value
                res.notes.append("RP reference pointer — external document not fetched (air-gap)")
            else:
                res.value_raw = value
                res.notes.append(f"unhandled OBX-2 value type '{value_type}' kept verbatim")

            current_order.results.append(res)
            last_result = res

        elif seg_id == "NTE":
            note = f[3] if len(f) > 3 else ""
            if note:
                if last_result is not None:
                    last_result.notes.append(note)
                else:
                    msg.notes.append(note)

        elif seg_id in ("ORC", "MSA", "EVN", "PV1"):
            continue
        else:
            malformed.append(f"unrecognised segment {seg_id}")

    usable = any(o.results or o.embedded_documents or o.embedded_pit for o in msg.orders)
    if not usable:
        raise ParseFailure(
            "no usable OBX content: " + ("; ".join(malformed) or "message empty")
        )
    msg.notes.extend(malformed)
    return msg
