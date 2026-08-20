"""INVARIANT: ENCODING DISCIPLINE — byte-identical behaviour on Windows.

Windows' locale default encoding is cp1252 (not UTF-8), so any text-mode
open()/read_text()/write_text() without an explicit encoding decodes/encodes
differently there than on Linux. That is exactly how the Windows build gate
once mis-read a UTF-8 golden file (em dash → 'â€'-style mojibake) and
reported extraction drift that did not exist.

This test walks the AST of EVERY Python file in the shipped package, the
scripts, and the test harness itself, and fails on:

  - builtin open(...) in text mode without encoding=...
  - Path.read_text()/write_text() without encoding=...
  - subprocess.run/check_output/Popen with text=True/universal_newlines=True
    but no encoding=...

It also pins the golden files themselves: strict UTF-8, LF-only, no BOM, and
the non-ASCII canary (the em dash in the platelets-note fixture) present, so
the suite keeps exercising non-ASCII content on every platform.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = [ROOT / "pathofinder", ROOT / "scripts", ROOT / "tests"]


def _mode_of(call: ast.Call) -> str:
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant) \
            and isinstance(call.args[1].value, str):
        return call.args[1].value
    return "r"


def _has_kw(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords)


def _kw_true(call: ast.Call, name: str) -> bool:
    for kw in call.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant):
            return bool(kw.value.value)
    return False


def _violations_in(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[str] = []
    rel = path.relative_to(ROOT)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func

        # builtin open(...) — text mode needs encoding
        if isinstance(func, ast.Name) and func.id == "open":
            if "b" not in _mode_of(node) and not _has_kw(node, "encoding"):
                out.append(f"{rel}:{node.lineno}: open() in text mode without encoding=")

        # Path.read_text()/write_text() need encoding
        if isinstance(func, ast.Attribute) and func.attr in ("read_text", "write_text"):
            if not _has_kw(node, "encoding"):
                out.append(f"{rel}:{node.lineno}: .{func.attr}() without encoding=")

        # subprocess text capture needs encoding
        if isinstance(func, ast.Attribute) \
                and func.attr in ("run", "check_output", "Popen", "call", "check_call") \
                and isinstance(func.value, ast.Name) and func.value.id == "subprocess":
            if (_kw_true(node, "text") or _kw_true(node, "universal_newlines")) \
                    and not _has_kw(node, "encoding"):
                out.append(f"{rel}:{node.lineno}: subprocess text mode without encoding=")
    return out


def test_invariant_no_locale_dependent_text_io():
    violations: list[str] = []
    for base in SCAN_DIRS:
        for src in sorted(base.rglob("*.py")):
            if "generated" in src.parts or "__pycache__" in src.parts:
                continue
            violations.extend(_violations_in(src))
    assert not violations, (
        "locale-dependent text I/O (breaks on Windows/cp1252):\n" + "\n".join(violations))


def test_invariant_golden_files_are_strict_utf8_lf():
    goldens = sorted((ROOT / "tests" / "golden").glob("*.json"))
    assert goldens, "golden files missing"
    for g in goldens:
        raw = g.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"{g.name}: BOM present"
        assert b"\r" not in raw, f"{g.name}: CR found — goldens must be LF-only"
        raw.decode("utf-8", errors="strict")     # raises on invalid UTF-8


def test_invariant_non_ascii_canary_survives():
    """The em dash in the platelets-note fixture is the canary that keeps the
    suite exercising non-ASCII round-tripping on every platform. cp1252 would
    decode its UTF-8 bytes to 'â€”'-style mojibake — assert the canary is
    intact and the mojibake absent."""
    g = ROOT / "tests" / "golden" / "golden_multi_obr_all_types.json"
    raw = g.read_bytes()
    assert "—".encode("utf-8") in raw            # \xe2\x80\x94
    text = raw.decode("utf-8")
    assert "Clumped — recollect" in text
    assert "â€" not in text                       # cp1252 mis-decode signature

    from tests.fixtures import generator
    assert "Clumped — recollect" in generator.hl7_multi_obr_all_types()
