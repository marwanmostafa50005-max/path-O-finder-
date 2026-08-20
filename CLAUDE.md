# CLAUDE.md — path-O-finder project memory

Living project memory. Read this + TASKS.md first on every session. On "continue":
read both files, find the NEXT unchecked task in TASKS.md, resume exactly there.

## What this is

path-O-finder: locally-installed, air-gapped, doctor-in-the-loop pathology-results
safety net for Australian general practice. Reads the practice's inbound pathology
feed (HL7 v2 ORU / PIT / PDF), flags abnormal results that appear UNACTIONED, and
presents a ranked morning queue with one-tap disposition and pointer-only guideline
citations. Safety net, not auditor. "The system dropped this", never "you missed this".

## Inviolable constraints (Section 2 of the build brief — these always win)

1. Air-gapped at runtime: zero outbound network calls; automated no-socket test.
2. Initials sign-on before any analysis run; full immutable hash-chained audit log.
3. TGA red lines: no dose calc; no patient-specific guideline filtering; never
   assert a trend is abnormal (show serial values only); VLM = grounded READING
   only, never interpretation; surface the LAB'S OWN OBX-8 flag, compute no
   clinical interpretation of our own.
4. Practice is data custodian; no phone-home ever.
5. NO demo/sample-data mode in the shipped UI (synthetic fixtures live in tests only).
6. Licence safety: MIT/BSD/Apache-2.0/LGPL-dynamic only. NO PyMuPDF (AGPL), NO
   Surya OCR (revenue-capped weights), Qwen2.5-VL **7B-Instruct only** (Apache-2.0).
   THIRD_PARTY_LICENSES.md must list everything; scripts/license_check.py fails the
   build on AGPL/GPL/revenue-capped deps.

## Settled tech stack

Python 3.11 (pinned) · PySide6 (LGPL, dynamic) · hl7apy + python-hl7 fallback ·
pdfplumber (native PDF text+bboxes) · pypdfium2 (rasterise) · pytesseract+Tesseract
(OCR, bundled on Windows) · Pillow · Qwen2.5-VL-7B-Instruct GGUF via bundled
llama.cpp llama-server (Tier 3, offline, JSON-constrained, graceful disable) ·
SQLite + SQLCipher via sqlcipher3 wheels (key via keyring/Windows DPAPI) ·
APScheduler · ruamel.yaml · PyInstaller + Inno Setup · pytest · bundled Poppins font.

## Architecture (six stages, source-agnostic core, thin adapters)

```
pathofinder/
  db/          connection (SQLCipher), schema+migrations, audit (hash chain), repository
  ingestion/   sniffer (HL7|MLLP|batch|PIT|PDF), watcher (copy-only, sha256, idempotent),
               adapters (MedicalObjects/HealthLink/Argus/ReferralNet), quarantine
  extraction/  records (canonical dataclasses), hl7_tier1, pit, pdf_tier2 (pdfplumber→OCR),
               vlm_tier3 (llama-server client + hardware detect), coherence, normalize
  detection/   severity (from OBX-8), grace (YAML matrix), flags
  actionstate/ closedloop (INBOX/RECALL × STRICT/LENIENT), dispositions, suppression
  presentation/queue (ranking: severity × time-vs-grace, check-yourself sunk), scheduler
  guidelines/  citations (pointer-only YAML map, review cadence)
  ui/          PySide6: signon, queue, detail+provenance, dispositions, settings,
               audit viewer, about (EXACT copy from brief §12)
  config/      versioned YAML loader (config_versions + audit on every edit)
  resources/   grace_matrix.yaml (DRAFT), citation_map.yaml (DRAFT),
               plausibility_bounds.yaml, spia_aliases.yaml, fonts/Poppins
```

Abstention is first-class: any uncertainty → "check-yourself", bottom of queue,
never a possibly-wrong value. Suppression only ever records an explicit human
disposition. Every value carries provenance (Tier 1: segment/field path; Tier 2/3:
page + pixel bbox).

## Design decisions log

- 2026-08-18 Brand asset files arrived named `pathofinder_ui.svg` / `pathofinder_ui.png`
  (no `-1` suffix as the brief said). Kept real names, moved to /brand.
- 2026-08-18 GitHub repo already existed (marwanmostafa50005-max/path-o-finder-) with
  origin configured; work happens on branch `claude/pathofinder-build-a0xefx` per the
  harness instruction (overrides brief §14's gh repo create).
- 2026-08-18 DB layer: `sqlcipher3` required in production (`PATHOFINDER_ALLOW_PLAIN_SQLITE`
  escape hatch exists ONLY for dev/test where the wheel is unavailable; app refuses
  plain sqlite unless that env var is set, and marks the DB accordingly).
- 2026-08-18 Tier-3 VLM: client + hardware detection + JSON-schema-constrained
  llama-server protocol implemented; model weights are NEVER committed. A build-time
  script (scripts/fetch_vlm_model.py) downloads the Apache-2.0 7B GGUF for packaging.
  Tests mock the server. App fully functional with Tier 3 absent (per brief).
- 2026-08-18 Windows-only pieces (DPAPI keyring backend, Inno Setup, bundled
  Tesseract) are scripted for the Windows build host; Linux CI runs the same code
  with keyring fallback + system tesseract. Documented in README + installer/.
- 2026-08-18 Audit immutability: SQLite triggers raising on UPDATE/DELETE + code-level
  guard + SHA-256 hash chain (hash_self = sha256(hash_prev || canonical row JSON)).

- 2026-08-20 Windows gate failure root-caused: `read_text()` without encoding in
  the golden test decoded UTF-8 goldens as cp1252 on Windows (em dash → mojibake
  in the EXPECTED record; engine output was identical). Fixed encoding='utf-8'
  at every text-IO site (app + scripts + tests); goldens NOT re-pinned (byte-
  identical). Added tests/invariants/test_encoding_discipline.py: AST scan
  failing on any text-mode open/read_text/write_text/subprocess-text without
  explicit encoding, golden strict-UTF-8/LF checks, and an em-dash canary.
  Added .gitattributes (eol=lf for compared text; ps1/iss crlf; binaries marked)
  so Windows autocrlf checkouts can't corrupt byte-compared files. Remaining
  EncodingWarnings under PYTHONWARNDEFAULTENCODING=1 come only from third-party
  pypdfium2_raw/version.py (its own ASCII file — harmless, not gated).

- 2026-08-20 Windows-divergence audit (multi-agent sweep) fixed, all regression-
  tested in tests/unit/test_windows_robustness.py:
  (1) fixture font: hard-coded Linux DejaVu path → bundled Poppins-SemiBold 48px
      (deterministic everywhere); OCR line grouping in pdf_tier2 rewritten to
      vertical-midpoint + height-proportional tolerance (top-based grouping split
      'g/L' tokens onto phantom lines with proportional fonts — recall loss);
  (2) settings save: hand-built YAML broke on backslash Windows paths
      (ScannerError) → ruamel dump;
  (3) watcher: per-file OSError handling — a Windows sharing violation (SM client/
      AV holding a file) skips that file this pass and retries next scan instead
      of aborting the run; OS shell metadata (desktop.ini/Thumbs.db/~$*/.DS_Store)
      ignored; inbox copy names capped for MAX_PATH;
  (4) DB key: per-user keyring + machine-wide %PROGRAMDATA% DB locked out the
      2nd Windows account → machine-scope DPAPI blob (CryptProtectData
      LOCAL_MACHINE, ctypes) stored beside the DB, with legacy keyring migration;
      keyring remains the dev/CI path off-Windows;
  (5) installer.iss [Dirs] grants users-modify on {commonappdata}\path-O-finder
      (default ProgramData ACLs make one user's files read-only to others);
  (6) vlm_tier3._model_path filters mmproj-* (Windows case-insensitive glob
      matched/sorted the mmproj companion first).

- 2026-08-20 Audit round 3 (adversarial verify pass, 27 agents, 2 confirmed):
  (7) serial_values gains `ORDER BY created_at DESC, result_id DESC` — Windows
      CPython <=3.12 clock granularity (~15.6ms) makes one-pass inserts share
      byte-identical created_at, and SQLite tie order is unspecified (the
      display-only serial panel could render out of chronological order);
  (8) Tier-2 OCR can no longer silently vanish from a shipped build:
      _tesseract_cmd also probes conventional Windows install roots
      (Program Files / LOCALAPPDATA\Programs Tesseract-OCR — the standard
      installer does not add PATH), build_windows.ps1 HARD-FAILS on a missing
      vendor bundle unless -AllowNoOcr, and Settings surfaces live OCR engine
      status. Regression tests in test_windows_robustness.py (99 total green).

## Environment notes (this build container)

- venv at .venv (Python 3.11.15). Tesseract via apt. PySide6 pip-installed for
  import-level tests; full GUI tests run offscreen (QT_QPA_PLATFORM=offscreen).
- No `gh` CLI here; pushes go via `git push -u origin claude/pathofinder-build-a0xefx`.
- PyInstaller/Inno run on the Windows build host via installer/build_windows.ps1;
  spec + iss are validated files in repo.

## Current state (2026-08-18)

BUILD COMPLETE. All 87 tests green (unit + integration + invariants + golden),
licence gate green, UI smoke-tested offscreen. Definition of Done met with two
Windows-host caveats recorded honestly:
  - PyInstaller/Inno Setup run on a Windows build host via
    installer/build_windows.ps1 (this Linux container validated the spec/iss
    files and the icon, and ships the scripts; the binary installer itself
    must be produced on Windows).
  - The desktop-shortcut launch is verified by the installer script's
    post-install run step + the shipping-posture invariants; final manual
    confirmation happens on the Windows host per README.

Remaining founder work (clinical, not engineering):
  - Review/replace DRAFT grace_matrix.yaml values.
  - Verify citation_map.yaml editions/URLs (cadence reminder is built in).
  - Build the installer on a Windows host; validate on an offline VM.

## How to resume

1. `source .venv/bin/activate` (or create: `python3.11 -m venv .venv && pip install -e .[dev]`)
2. Read TASKS.md → find "NEXT TASK" pointer.
3. Run `python -m pytest -q` to confirm green before continuing.
4. Commit with conventional commits; push to `claude/pathofinder-build-a0xefx` after
   each milestone.
