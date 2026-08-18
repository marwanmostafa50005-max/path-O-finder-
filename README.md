<p align="center">
  <img src="brand/pathofinder_ui.png" alt="path-O-finder" width="420"/>
</p>

# path-O-finder

**Every result finds its path, and every path is one a clinician chose.**

path-O-finder is a locally-installed, **air-gapped**, doctor-in-the-loop
**pathology-results safety net** for Australian general practice. It reads the
practice's own inbound pathology feed (HL7 v2 ORU, legacy PIT, and PDF
reports), flags abnormal results that appear **unactioned**, and presents them
to the treating doctor each morning with a one-tap disposition and a
**pointer** to the relevant Australian guideline.

It is a **safety net, not an auditor**: the framing is always "the system
dropped this", never "you missed this". It is private to the practice — no
scorekeeping across doctors, no league tables, **no cloud**.

---

## What it does — the six stages

1. **Ingestion** — watches a read-only copy of the secure-messaging drop
   folder (Medical-Objects, HealthLink, Argus, ReferralNet). Copies, never
   moves; never ACKs; never touches the lab's or PMS's files. Files that
   cannot be parsed with confidence are **quarantined and surfaced**, never
   silently dropped. Reprocessing the same feed never duplicates a flag.
2. **Extraction** — deterministic-first, three tiers, **abstain-when-unsure**:
   - *Tier 1:* atomic HL7 OBX parse (all value types; repeating OBX-8 flags;
     OBX-11 preliminary/correction handling). Provenance = segment/field path.
   - *Tier 2:* PDF native text layer (pdfplumber, per-value bounding boxes),
     then confidence-gated Tesseract OCR for scans. Provenance = page + pixel
     bounding box.
   - *Tier 3 (optional):* a **local** Qwen2.5-VL-7B vision model via a bundled
     llama.cpp server on 127.0.0.1 — grounded transcription only, two-pass
     agreement, JSON-constrained. Reading, never interpretation. Disabled
     gracefully on modest hardware.
   Every value passes coherence cross-checks (value-vs-range-vs-lab-flag,
   physiological hard bounds, unit sanity); any conflict → **check-yourself**,
   bottom of the queue, no value emitted.
3. **Detection** — surfaces the **lab's own abnormal flag (OBX-8)**; the
   software computes no clinical interpretation of its own. A clinician-
   editable **grace matrix** (DRAFT defaults shipped) decides when a flag is
   overdue.
4. **Action-state** — manual closed-loop confirmation: a doctor/RN, looking at
   the practice software, confirms whether the loop is closed (INBOX and/or
   RECALL mode, STRICT or LENIENT). **Nothing is ever marked handled by the
   machine** — suppression is only ever the memory of an explicit human
   disposition, optionally scoped and time-boxed.
5. **Presentation** — a single overnight-built morning queue ranked by
   severity × time-elapsed-vs-grace, grouped per patient; check-yourself items
   always sink to the bottom. Each flag carries a "why flagged" panel with the
   value, the lab's range and flag, the open-loop evidence, and the **source
   region** (HL7 field path, or a page thumbnail with the bounding box drawn).
   Serial values are **shown**, never interpreted (no trend assertions).
6. **Guideline layer** — pointer/citation-only: guideline name, publisher,
   **edition/date**, section, and URL as display text, for high-confidence
   abnormal findings only. No reproduced guideline text, no dose, no
   patient-specific tailoring. Free Australian references; clinician-editable
   map with a review-cadence reminder.

## Regulatory posture (TGA)

path-O-finder is designed to sit **inside the Clinical Decision Support
Software exemption** (Therapeutic Goods (Medical Devices) Regulations 2002):

- It never calculates a dose.
- It never filters or tailors guidance to a specific patient.
- It never asserts that a trend is abnormal — serial values are displayed for
  the clinician to interpret.
- Its only abnormality signal is **the lab's own flag**; it adds no clinical
  interpretation.
- The optional vision model performs grounded *reading* of printed characters
  (with the pixel region it read from), never interpretation, diagnosis, or
  advice.

## Air-gap & privacy posture

- **Zero outbound network calls at runtime** — no telemetry, no update checks,
  no license callbacks, no CDN fonts. An automated invariant test denies all
  sockets and runs the full pipeline to prove it.
- All data stays in an **SQLCipher AES-256 encrypted** local database; the key
  is created at first run and held in the Windows credential store (DPAPI) —
  never hard-coded.
- The practice is the data custodian. The developer never receives identified
  patient data. There is no phone-home.
- Every analysis run begins with **initials sign-on**; runs, flags,
  dispositions, quarantines, and config edits are written to an **immutable,
  hash-chained audit log** (UPDATE/DELETE blocked by trigger; chain verifiable
  in-app).

## Install (Windows 10/11 x64)

1. Build or obtain `path-O-finder-setup-<version>.exe` (see *Building the
   installer* below). The installer is fully offline.
2. Run it; it installs to Program Files, creates a Start-menu entry and a
   desktop shortcut with the path-O-finder icon.
3. First launch: enter your initials, then open **Settings → Practice** and
   set the **watched feed folder** — point it at a **read-only copy** of the
   secure-messaging client's inbound folder (Medical-Objects Capricorn,
   HealthLink HMS, Argus, or ReferralNet drop directory). Choose your
   closed-loop mode (inbox/recall) and strictness (strict/lenient).
4. Review the two DRAFT configs before clinical use (see below).
5. Use **Build queue now** for the first run; the overnight scheduler then
   rebuilds the queue each morning.

### Running from source (dev)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[sqlcipher,dev]"
python -m pytest -q                    # full suite incl. invariants
python scripts/license_check.py        # licence gate
python -m pathofinder                  # launch the app
```

Tesseract must be on PATH for the OCR tier in dev (the Windows installer
bundles it). Without SQLCipher, the app refuses to start unless
`PATHOFINDER_ALLOW_PLAIN_SQLITE=1` (development only — never with patient
data).

## Building the installer

On a Windows 10/11 x64 build host with Python 3.11 and Inno Setup 6:

```powershell
powershell -ExecutionPolicy Bypass -File installer\build_windows.ps1
```

The script: creates the build venv → runs the **licence gate** → runs the full
test suite → generates the multi-resolution `.ico` from `brand/icon_1024.png`
→ checks for the vendored Tesseract/llama-server payloads → runs PyInstaller
(`installer/pathofinder.spec`) → runs Inno Setup (`installer/installer.iss`).
Output lands in `installer/output/`.

Model weights for the optional Tier-3 reader are fetched at **build time
only** by `scripts/fetch_vlm_model.py` (Qwen2.5-VL-**7B-Instruct**, Apache-2.0
— the 3B and 72B variants are licence-excluded) and are never committed to
this repository.

### Verifying the air-gap after install

- The application makes no network calls; verify with an outbound firewall
  rule (block all for the app) — every feature keeps working, or
- Windows Resource Monitor / `netstat` while using the app: no connections
  beyond the optional local `127.0.0.1` inference server.

## Configuration files (clinician-editable, versioned, audited)

| Config | Ships as | Status |
|---|---|---|
| Grace matrix | `pathofinder/resources/grace_matrix.yaml` | **DRAFT — requires clinician review before clinical use** |
| Citation map | `pathofinder/resources/citation_map.yaml` | **DRAFT — verify editions/URLs; review cadence 180 days** |
| Test aliases | Settings → Test aliases (DB table over the RCPA SPIA seed) | practice-maintained |

All three are edited in-app; every save is validated, versioned
(`config_versions`) and written to the audit log. Invalid edits never replace
the live config.

## Licence posture

path-O-finder is **proprietary** (see `LICENSE`; © Marwan Morsy, all rights
reserved). Third-party components are permissively licensed only — MIT / BSD /
Apache-2.0 / LGPL-dynamic; see `THIRD_PARTY_LICENSES.md`. The build fails if
any AGPL / copyleft / revenue-capped dependency appears
(`scripts/license_check.py`). PyMuPDF and Surya OCR are explicitly excluded.
Licence texts for bundled binaries (PDFium, Tesseract, SQLCipher, llama.cpp,
Qt/LGPL notice, Poppins OFL) ship with the installer under `licenses/`.

## Repository layout

```
pathofinder/          application package (six-stage architecture)
  db/                 SQLCipher connection, schema, hash-chained audit, repository
  ingestion/          sniffer, watcher, adapters, quarantine
  extraction/         records, hl7_tier1, pit, pdf_tier2, vlm_tier3, coherence, normalize
  detection/          severity, grace, flags
  actionstate/        closedloop, dispositions
  presentation/       queue ranking, overnight scheduler
  guidelines/         pointer-only citations
  ui/                 PySide6 screens (sign-on, queue, detail, settings, audit, about)
  resources/          DRAFT YAML configs, SPIA seed, plausibility bounds, fonts, brand
tests/                unit + integration + invariants + golden files + fixture generator
scripts/              licence gate, icon generator, build-time model fetcher
installer/            PyInstaller spec, Inno Setup script, Windows build script, licences
brand/                brand assets (logo, desktop icon source)
CLAUDE.md, TASKS.md   living project memory + task ledger (resumable build)
```
