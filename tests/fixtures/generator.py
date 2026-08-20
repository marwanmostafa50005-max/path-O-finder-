"""Synthetic Australian-profile fixture generator (test suite ONLY — never shipped).

All patient identities are fake. Files are generated deterministically into
tests/fixtures/generated/ at test-session start.

Covers (build brief §11): HL7AU ORU^R01 with multi-OBR/multi-OBX, every OBX-2
value type, repeating OBX-8, OBX-11 P and C, batch FHS/BHS…BTS/FTS incl. a
truncated batch, NTE lines, embedded base64 PDF in an ED segment, malformed
segments; PIT standalone and embedded-in-OBX; PDFs native / scanned /
low-quality; coherence-conflict messages.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

GENERATED = Path(__file__).parent / "generated"

CR = "\r"

# -- synthetic patients (fake identities only) -------------------------------

PATIENTS = {
    "P1": ("CITIZEN^Janet^A", "19800214", "F", "MRN000101"),
    "P2": ("FAKEMAN^Robert^J", "19551103", "M", "MRN000202"),
    "P3": ("TESTPERSON^Ngaire^K", "19921230", "F", "MRN000303"),
}


def _msh(control_id: str, dt: str = "20260810093000") -> str:
    # HL7AU localisation of version id (MSH-12)
    return (f"MSH|^~\\&|LAB^SynthPath^AUSNATA|SynthPath|BP^BestPractice|Clinic|"
            f"{dt}||ORU^R01^ORU_R01|{control_id}|P|2.4^AUS&&ISO3166_1^HL7AU.ONO.1&&HL7AU")


def _pid(key: str) -> str:
    name, dob, sex, mrn = PATIENTS[key]
    return f"PID|1||{mrn}^^^SynthPath^MR||{name}||{dob}|{sex}"


def _obr(set_id: int, filler: str, panel_code: str, panel_name: str,
         collected: str = "20260809083000", reported: str = "20260810091500") -> str:
    return (f"OBR|{set_id}||{filler}|{panel_code}^{panel_name}^SynthPath|||{collected}|||||||"
            f"|||DR^Referrer^Rita||||||{reported}|||F")


def hl7_simple_abnormal() -> str:
    """UEC panel: one high potassium flagged H by the lab, plus a normal sodium."""
    segs = [
        _msh("SYNTH-0001"),
        _pid("P1"),
        _obr(1, "FIL-1001", "UEC", "Urea Electrolytes Creatinine"),
        "OBX|1|NM|2823-3^Potassium^LN||6.1|mmol/L|3.5-5.2|H|||F",
        "OBX|2|NM|2951-2^Sodium^LN||140|mmol/L|135-145|N|||F",
        "NTE|1|L|Specimen slightly haemolysed.",
    ]
    return CR.join(segs)


def hl7_multi_obr_all_types() -> str:
    """Two OBR groups exercising every OBX-2 value type + repeating OBX-8."""
    segs = [
        _msh("SYNTH-0002"),
        _pid("P2"),
        _obr(1, "FIL-2001", "FBC", "Full Blood Count"),
        "OBX|1|NM|718-7^Haemoglobin^LN||72|g/L|130-180|LL~A|||F",       # repeating flags
        "OBX|2|SN|6690-2^WCC^LN||<^0.5|10*9/L|4.0-11.0|LL|||F",         # structured numeric
        "OBX|3|ST|777-3^Platelets note^LN||Clumped — recollect||||||F",
        "NTE|1|L|Film reviewed by haematologist.",
        _obr(2, "FIL-2002", "MISC", "Miscellaneous"),
        "OBX|1|TX|55752-0^Clinical comment^LN||Long free text comment line.||||||F",
        "OBX|2|FT|55752-0^Formatted^LN||\\H\\Bold\\N\\ formatted text||||||F",
        "OBX|3|CE|600-7^Culture^LN||POS^Positive^L|||POS~A|||F",       # coded + qual flags
        "OBX|4|CWE|6463-4^Organism^LN||EColi^Escherichia coli^L|||A|||F",
        "OBX|5|RP|11502-2^Report link^LN||RP-123^^PDF||||||F",
    ]
    return CR.join(segs)


def hl7_preliminary_then_correction() -> tuple[str, str]:
    """Same filler order: preliminary K 5.9, then correction to 4.9 (OBX-11=C)."""
    prelim = CR.join([
        _msh("SYNTH-0003"),
        _pid("P1"),
        _obr(1, "FIL-3001", "UEC", "Urea Electrolytes Creatinine"),
        "OBX|1|NM|2823-3^Potassium^LN|1|5.9|mmol/L|3.5-5.2|H|||P",
    ])
    correction = CR.join([
        _msh("SYNTH-0004", dt="20260810120000"),
        _pid("P1"),
        _obr(1, "FIL-3001", "UEC", "Urea Electrolytes Creatinine"),
        "OBX|1|NM|2823-3^Potassium^LN|1|4.9|mmol/L|3.5-5.2|N|||C",
    ])
    return prelim, correction


def _minimal_pdf_bytes(lines: list[str]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 780
    for ln in lines:
        c.drawString(72, y, ln)
        y -= 24
    c.showPage()
    c.save()
    return buf.getvalue()


def hl7_embedded_pdf() -> str:
    """ORU carrying a base64 PDF in an ED segment (OBX-2=ED)."""
    pdf = _minimal_pdf_bytes([
        "SynthPath Pathology — Final Report",
        "Patient: TESTPERSON, Ngaire   DOB: 30/12/1992",
        "Ferritin    8 ug/L    (30 - 300)    LOW",
        "CRP         2 mg/L    (< 5)",
    ])
    b64 = base64.b64encode(pdf).decode("ascii")
    segs = [
        _msh("SYNTH-0005"),
        _pid("P3"),
        _obr(1, "FIL-5001", "FERR", "Ferritin"),
        f"OBX|1|ED|PDF^Report^L||SynthPath^APPLICATION^PDF^Base64^{b64}||||||F",
    ]
    return CR.join(segs)


def hl7_batch(truncated: bool = False) -> str:
    """FHS/BHS…BTS/FTS batch with two messages; truncated variant omits trailers."""
    m1 = hl7_simple_abnormal().replace("SYNTH-0001", "SYNTH-0006")
    m2 = CR.join([
        _msh("SYNTH-0007"),
        _pid("P2"),
        _obr(1, "FIL-7001", "TSH", "Thyroid Stimulating Hormone"),
        "OBX|1|NM|3016-3^TSH^LN||11.2|mIU/L|0.4-4.0|H|||F",
    ])
    parts = [
        "FHS|^~\\&|LAB|SynthPath|BP|Clinic|20260810093000",
        "BHS|^~\\&|LAB|SynthPath|BP|Clinic|20260810093000",
        m1, m2,
    ]
    if not truncated:
        parts += ["BTS|2", "FTS|1"]
    return CR.join(parts)


def hl7_malformed() -> str:
    """Structurally broken message: mangled MSH-2, truncated OBX — must quarantine."""
    return CR.join([
        "MSH|^~\\&|GARBLED",
        "PID|1||X",
        "OBX|1|NM|2823-3^Potassium",   # missing value/units/range — unusable
        "OBX|banana",
    ])


# -- coherence-conflict fixtures --------------------------------------------

def hl7_conflict_flag_vs_range() -> str:
    """Value inside the stated range but lab flagged H → conflict → abstain."""
    return CR.join([
        _msh("SYNTH-0010"),
        _pid("P1"),
        _obr(1, "FIL-8001", "UEC", "Urea Electrolytes Creatinine"),
        "OBX|1|NM|2823-3^Potassium^LN||4.4|mmol/L|3.5-5.2|H|||F",
    ])


def hl7_conflict_impossible_value() -> str:
    """Physiologically impossible potassium (450 mmol/L) → abstain."""
    return CR.join([
        _msh("SYNTH-0011"),
        _pid("P2"),
        _obr(1, "FIL-8002", "UEC", "Urea Electrolytes Creatinine"),
        "OBX|1|NM|2823-3^Potassium^LN||450|mmol/L|3.5-5.2|HH|||F",
    ])


def hl7_conflict_unit_mismatch() -> str:
    """Potassium reported in g/L — unit incompatible with analyte → abstain."""
    return CR.join([
        _msh("SYNTH-0012"),
        _pid("P3"),
        _obr(1, "FIL-8003", "UEC", "Urea Electrolytes Creatinine"),
        "OBX|1|NM|2823-3^Potassium^LN||6.1|g/L|3.5-5.2|H|||F",
    ])


def hl7_conflict_misplaced_decimal() -> str:
    """Haemoglobin 1400 g/L (plausible ×10 slip) → outside hard bounds → abstain."""
    return CR.join([
        _msh("SYNTH-0013"),
        _pid("P1"),
        _obr(1, "FIL-8004", "FBC", "Full Blood Count"),
        "OBX|1|NM|718-7^Haemoglobin^LN||1400|g/L|130-180|HH|||F",
    ])


# -- PIT fixtures ------------------------------------------------------------

def pit_standalone() -> str:
    """Legacy PIT report: 3-digit line codes; x19/x99 separators; ~FG control codes."""
    lines = [
        "001 SynthPath Pathology",
        "019 ",
        "100 TESTPERSON, NGAIRE                DOB: 30/12/1992",
        "101 MRN000303",
        "119 ",
        "200 ~FG02~POTASSIUM          6.1     mmol/L   (3.5-5.2)   H",
        "201 SODIUM                 140     mmol/L   (135-145)",
        "219 ",
        "300 Comment: specimen received in good condition.",
        "999 END OF REPORT",
    ]
    return "\r\n".join(lines)


def hl7_with_embedded_pit() -> str:
    """PIT payload carried inside an OBX (FT) — both forms occur in the wild."""
    pit = pit_standalone().replace("\r\n", "\\.br\\")
    return CR.join([
        _msh("SYNTH-0014"),
        _pid("P3"),
        _obr(1, "FIL-9001", "MISC", "Legacy Report"),
        f"OBX|1|FT|PIT^Legacy report^L||{pit}||||||F",
    ])


# -- PDF fixtures -------------------------------------------------------------

def pdf_native() -> bytes:
    return _minimal_pdf_bytes([
        "SynthPath Pathology — Final Report",
        "Patient: CITIZEN, Janet   DOB: 14/02/1980   MRN000101",
        "Test        Result   Units    Reference    Flag",
        "Potassium   6.1      mmol/L   3.5-5.2      H",
        "Sodium      140      mmol/L   135-145",
    ])


def pdf_scanned(quality: str = "good") -> bytes:
    """Image-only PDF for the OCR path. quality='low' must fail the OCR gate."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    W, H = (1654, 2339)  # ~A4 at 200dpi
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    # Render with the repo's own bundled Poppins so the fixture is
    # byte-deterministic on every platform. A hard-coded system font path
    # broke Windows: Pillow's ~10px bitmap fallback made the "good" scan
    # unreadable and failed the OCR test on the build host.
    # SemiBold at 48px: a genuinely clean "scan" that clears the OCR gate;
    # the low-quality variant below degrades it far past the gate.
    font_path = (Path(__file__).resolve().parents[2] / "pathofinder"
                 / "resources" / "fonts" / "Poppins-SemiBold.ttf")
    font = ImageFont.truetype(str(font_path), 48)
    rows = [
        "SynthPath Pathology - Final Report",
        "Patient: FAKEMAN, Robert  DOB: 03/11/1955",
        "",
        "Test        Result   Units    Range       Flag",
        "Haemoglobin   72     g/L      130-180     LL",
        "Ferritin       8     ug/L     30-300      L",
    ]
    y = 200
    for r in rows:
        d.text((150, y), r, font=font, fill=0)
        y += 80

    if quality == "low":
        img = img.resize((W // 6, H // 6)).resize((W, H))
        img = img.filter(ImageFilter.GaussianBlur(6))
        import random
        rnd = random.Random(42)
        px = img.load()
        for _ in range(140000):
            x, yy = rnd.randrange(W), rnd.randrange(H)
            px[x, yy] = rnd.randrange(256)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PDF", resolution=200)
    return buf.getvalue()


# -- writer -------------------------------------------------------------------

def write_all(target: Path = GENERATED) -> Path:
    target.mkdir(parents=True, exist_ok=True)
    prelim, corr = hl7_preliminary_then_correction()
    files: dict[str, bytes | str] = {
        "oru_simple_abnormal.hl7": hl7_simple_abnormal(),
        "oru_multi_obr_all_types.hl7": hl7_multi_obr_all_types(),
        "oru_preliminary.hl7": prelim,
        "oru_correction.hl7": corr,
        "oru_embedded_pdf.hl7": hl7_embedded_pdf(),
        "oru_batch.hl7": hl7_batch(),
        "oru_batch_truncated.hl7": hl7_batch(truncated=True),
        "oru_malformed.hl7": hl7_malformed(),
        "oru_conflict_flag_vs_range.hl7": hl7_conflict_flag_vs_range(),
        "oru_conflict_impossible_value.hl7": hl7_conflict_impossible_value(),
        "oru_conflict_unit_mismatch.hl7": hl7_conflict_unit_mismatch(),
        "oru_conflict_misplaced_decimal.hl7": hl7_conflict_misplaced_decimal(),
        "report_legacy.pit": pit_standalone(),
        "oru_embedded_pit.hl7": hl7_with_embedded_pit(),
        "report_native.pdf": pdf_native(),
        "report_scanned.pdf": pdf_scanned("good"),
        "report_scanned_low_quality.pdf": pdf_scanned("low"),
        "mllp_wrapped.hl7": b"\x0b" + hl7_simple_abnormal().replace(
            "SYNTH-0001", "SYNTH-0015").encode() + b"\x1c\x0d",
        "not_a_report.xyz": b"\x00\x01\x02 random junk that matches nothing",
    }
    for name, content in files.items():
        p = target / name
        if isinstance(content, str):
            p.write_bytes(content.encode("utf-8"))
        else:
            p.write_bytes(content)
    return target


if __name__ == "__main__":
    print("fixtures written to", write_all())
