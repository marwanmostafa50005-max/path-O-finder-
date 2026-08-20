# path-O-finder - Windows build script (run on the Windows 10/11 x64 build host).
# Produces installer\output\path-O-finder-setup-<version>.exe, a fully offline
# installer. All downloads below happen at BUILD time only; the shipped app
# makes zero network calls.
#
# Prerequisites on the build host:
#   - Python 3.11 x64 on PATH
#   - Inno Setup 6 (auto-located: PATH, then the standard install folders)
#
# Usage:  powershell -ExecutionPolicy Bypass -File installer\build_windows.ps1
#         (add -AllowNoOcr to deliberately ship without bundled Tier-2 OCR)

param([switch]$AllowNoOcr)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "== 1. Build venv =="
if (-not (Test-Path ".venv-build")) { py -3.11 -m venv .venv-build }
& .\.venv-build\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[sqlcipher,dev]"
pip install pyinstaller

Write-Host "== 2. Licence gate (fails on AGPL/GPL/revenue-capped) =="
python scripts\license_check.py
if ($LASTEXITCODE -ne 0) { throw "licence check failed" }

Write-Host "== 3. Tests =="
python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "tests failed" }

Write-Host "== 4. Icon =="
python scripts\generate_icon.py

Write-Host "== 5. Vendor: Tesseract (Apache-2.0) =="
# Portable Tesseract: place a portable build under installer\vendor\tesseract
# (tesseract.exe + tessdata\eng.traineddata + its LICENSE file).
# HARD GATE: a build without it would silently ship with Tier-2 OCR dead -
# every scanned report would dead-end in check-yourself while the Linux-
# validated OCR tests were skipped. Fail loudly unless explicitly overridden.
if (-not (Test-Path "installer\vendor\tesseract\tesseract.exe")) {
    if ($AllowNoOcr) {
        Write-Warning "Building WITHOUT bundled Tesseract (-AllowNoOcr): scanned/image-only reports will all go to check-yourself unless Tesseract is installed on the practice machine."
    } else {
        throw "installer\vendor\tesseract\tesseract.exe missing - the shipped build would silently lack OCR. Place a portable Apache-2.0 Tesseract there (tesseract.exe + tessdata\eng.traineddata + LICENSE), or re-run with -AllowNoOcr to ship without Tier-2 OCR."
    }
}

Write-Host "== 6. Vendor: llama.cpp llama-server (MIT) + Qwen2.5-VL-7B GGUF (Apache-2.0) =="
# Optional Tier-3. If absent the app disables Tier 3 gracefully.
if (-not (Test-Path "installer\vendor\llama\llama-server.exe")) {
    Write-Warning "installer\vendor\llama not found - Tier-3 VLM will be disabled in the shipped build unless the practice installs the model later."
}
# Model weights are NEVER bundled into the repo; fetch at build time if wanted:
#   python scripts\fetch_vlm_model.py --dest installer\vendor\llama\models

Write-Host "== 7. PyInstaller =="
pyinstaller installer\pathofinder.spec --noconfirm

Write-Host "== 7b. Frozen-app self-check =="
# Launch the packaged exe in headless self-test mode: proves the frozen app
# can import its full stack, find its bundled resources, and initialise Qt.
# A packaging regression must fail the BUILD, never a practice machine.
$app = Start-Process -FilePath "dist\path-O-finder\path-O-finder.exe" -ArgumentList "--selfcheck" -Wait -PassThru
if ($app.ExitCode -ne 0) { throw "frozen app self-check failed (exit $($app.ExitCode)) - the packaged exe cannot start" }
Write-Host "Frozen app self-check passed."

Write-Host "== 8. Inno Setup =="
# The Inno Setup installer does not add iscc to PATH; locate it ourselves.
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $roots = @(${env:ProgramFiles(x86)}, $env:ProgramFiles) | Where-Object { $_ }
    foreach ($root in $roots) {
        $cand = Join-Path $root "Inno Setup 6\iscc.exe"
        if (Test-Path $cand) { $iscc = $cand; break }
    }
}
if (-not $iscc) {
    throw "Inno Setup 6 not found (no iscc on PATH and not in Program Files). Install it from jrsoftware.org/isdl.php, then re-run this script."
}
& $iscc installer\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

Write-Host "== DONE =="
Get-ChildItem installer\output
Write-Host "Verify manually: install on a clean offline VM; check the desktop"
Write-Host "shortcut carries the icon and launches; run the no-network posture"
Write-Host "check (firewall audit) documented in README."
