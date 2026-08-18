# Third-party licences — path-O-finder

path-O-finder itself is proprietary (see LICENSE). It bundles or depends on the
following third-party components, each under its own permissive licence. No
AGPL, viral-copyleft, revenue-capped, or MAU-capped component is permitted;
`scripts/license_check.py` enforces this at build time.

## Python runtime dependencies

| Component | Version policy | Licence | Notes |
|---|---|---|---|
| Python | 3.11.x (pinned) | PSF-2.0 | Embedded interpreter via PyInstaller |
| PySide6 / shiboken6 | >=6.6 | LGPL-3.0 | **Dynamically linked** (Qt for Python); unmodified Qt libraries shipped as separate DLLs, satisfying LGPL §4d |
| hl7apy | >=1.3 | MIT | Primary HL7 v2 parser |
| hl7 (python-hl7) | >=0.4 | BSD-3-Clause | Tolerant fallback tokeniser |
| pdfplumber | >=0.11 | MIT | Native PDF text + bounding boxes |
| pdfminer.six | (via pdfplumber) | MIT | |
| pypdfium2 | >=4.28 | Apache-2.0 OR BSD-3-Clause | Bundles PDFium (BSD-3-Clause); PDFium's own licence text shipped in installer (`installer/licenses/PDFium-LICENSE.txt`) |
| pytesseract | >=0.3.10 | Apache-2.0 | Wrapper over Tesseract |
| Tesseract OCR engine | 5.x (bundled on Windows) | Apache-2.0 | Engine + eng traineddata shipped with installer, licence text shipped |
| Pillow | >=10 | MIT-CMU | |
| APScheduler | >=3.10 | MIT | In-process scheduler |
| ruamel.yaml | >=0.18 | MIT | Clinician-editable configs |
| keyring | >=24 | MIT | Windows DPAPI-backed credential store for DB passphrase |
| sqlcipher3-wheels | >=0.5 | BSD / Zetetic BSD-style | Self-contained SQLCipher (AES-256) binary wheel; SQLCipher licence text shipped |
| llama.cpp (llama-server) | pinned release binary | MIT | Bundled offline inference server for Tier 3 |
| Qwen2.5-VL-**7B-Instruct** (GGUF) | pinned quant | Apache-2.0 | Downloaded at BUILD time only, never committed. 3B (research-only) and 72B (MAU-capped) variants are FORBIDDEN |

## Build/dev-only tools (not shipped)

| Component | Licence | Notes |
|---|---|---|
| PyInstaller | GPL-2.0-with-bundling-exception | Exception explicitly permits packaging proprietary apps |
| Inno Setup | Inno Setup licence (free, permissive) | Installer builder, not distributed inside the app |
| pytest | MIT | Test suite only |
| pip-licenses | MIT | Licence gate only |

## Fonts

| Font | Licence | Notes |
|---|---|---|
| Poppins | SIL Open Font License 1.1 | Bundled in `pathofinder/resources/fonts/`; `OFL.txt` shipped alongside |

## Explicitly excluded (do not add)

- **PyMuPDF / fitz** — AGPL-3.0 (Artifex dual licence). Replaced by pdfplumber + pypdfium2.
- **Surya OCR** — model weights under revenue-capped AI-Pubs Open-RAIL-M. Replaced by Tesseract.
- **Qwen2.5-VL 3B** (research-only) and **72B** (MAU-capped) variants.
- Any AGPL/SSPL/Commons-Clause/RAIL/NC-licensed dependency.

This file is regenerated/verified against the build venv by `scripts/license_check.py`;
update the table when adding any dependency.
