# TASKS.md — ordered build ledger

Mark [x] with commit hash when done. **NEXT TASK** pointer below is authoritative
for resuming.

## Phase 0 — scaffold
- [x] T00 venv + deps installed; tesseract installed (env only, not committed)
- [x] T01 Repo scaffold: CLAUDE.md, TASKS.md, .gitignore, LICENSE (proprietary),
      pyproject.toml, brand/ move, package skeleton — commit `chore: scaffold`
- [x] T02 THIRD_PARTY_LICENSES.md initial + scripts/license_check.py

## Phase 1 — data layer
- [x] T10 db/connection.py (SQLCipher, keyring passphrase, plain-sqlite dev escape)
- [x] T11 db/schema.py full schema §5 + migrations + audit triggers
- [x] T12 db/audit.py hash-chained append-only log + verify
- [x] T13 db/repository.py typed CRUD for all tables
- [x] T14 tests: schema, audit immutability invariant, hash chain verify

## Phase 2 — ingestion
- [x] T20 ingestion/sniffer.py (HL7 | MLLP | batch FHS/BHS/BTS/FTS + truncation |
      PIT | PDF; never trust extensions)
- [x] T21 ingestion/watcher.py (copy-only, sha256, idempotent, read-only source)
- [x] T22 ingestion/quarantine.py + adapters.py (4 thin adapters)
- [x] T23 tests: sniffing, idempotency invariant, never-drop invariant, truncated batch

## Phase 3 — extraction
- [x] T30 extraction/records.py canonical record + provenance dataclasses
- [x] T31 extraction/hl7_tier1.py (all OBX-2 types, repeating OBX-8, OBX-11 P/C
      supersession, ED base64 PDF extraction, NTE)
- [x] T32 extraction/pit.py (standalone + embedded-in-OBX)
- [x] T33 extraction/pdf_tier2.py (pdfplumber bboxes → pypdfium2+tesseract OCR,
      confidence gate 80 default)
- [x] T34 extraction/vlm_tier3.py (hardware detect, llama-server JSON-constrained,
      grounded bbox required, multi-pass agreement, graceful disable)
- [x] T35 extraction/coherence.py (value-vs-range-vs-flag, plausibility bounds,
      unit/decimal sanity) + resources/plausibility_bounds.yaml
- [x] T36 extraction/normalize.py (SPIA seed + test_aliases table)
- [x] T37 tests: tier1 golden files, PIT, coherence-abstain invariant,
      zero-false-abnormal invariant, correction supersession

## Phase 4 — detection & action-state
- [ ] T40 detection/severity.py + grace.py + flags.py + resources/grace_matrix.yaml (DRAFT)
- [ ] T41 actionstate/closedloop.py + dispositions.py + suppression.py
- [ ] T42 tests: grace deadlines, suppression-only-by-human invariant

## Phase 5 — presentation & guidelines
- [ ] T50 presentation/queue.py ranking (check-yourself sunk) + scheduler.py
- [ ] T51 guidelines/citations.py + resources/citation_map.yaml (DRAFT §10 content)
- [ ] T52 config/loader.py versioned YAML editing
- [ ] T53 tests: ranking invariant (abstained never outranks confident), citation
      gating (no citation for low-confidence)

## Phase 6 — pipeline & no-network
- [ ] T60 pipeline.py: run orchestration (initials-gated), runs table, end-to-end
- [ ] T61 tests: integration end-to-end on fixtures; NO-NETWORK invariant test

## Phase 7 — UI
- [ ] T70 ui/theme.py (palette §12, Poppins bundled) + app.py entry
- [ ] T71 ui/signon + main window + queue view
- [ ] T72 ui/detail (why-flagged + provenance viewer) + disposition bar
- [ ] T73 ui/settings (folder, closed-loop mode, grace/citation/alias editors, VLM)
- [ ] T74 ui/audit viewer + about page (EXACT §12 copy)
- [ ] T75 ui smoke tests (offscreen)

## Phase 8 — packaging & docs
- [ ] T80 scripts/generate_icon.py multi-res .ico from brand/icon_1024.png
- [ ] T81 installer/pathofinder.spec + installer.iss + build_windows.ps1 +
      fetch_vlm_model.py + fetch_fonts (Poppins bundled)
- [ ] T82 README.md full; THIRD_PARTY_LICENSES.md complete; licence texts shipped
- [ ] T83 Final: full test run green, license check green, Definition-of-Done
      self-review, final push

**NEXT TASK: T40**
