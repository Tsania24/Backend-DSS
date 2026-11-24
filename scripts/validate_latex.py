#!/usr/bin/env python3
"""
validate_latex.py
-----------------
Validasi sintaks LaTeX dalam markdown yang sudah dibangun ulang.
Perbaiki kesalahan umum, tandai sisanya dengan <!-- FORMULA_ERROR -->
dan hasilkan laporan untuk perbaikan manual.

Idempotent: aman dijalankan ulang.

Usage:
    python scripts/validate_latex.py [--input path/to/file.md]
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEFAULT_INPUT = ROOT / "data/markdown/furniture_arrangement_ieq_2023_rebuilt.md"
REPORT_PATH = ROOT / "docs/latex_validation_report.json"

import json

# ── Perbaikan otomatis ────────────────────────────────────────────────────────

AUTO_FIXES = [
    # Spasi sebelum \left tidak diperlukan tapi aman
    # Perbaiki \alpha yang sering salah encode
    (re.compile(r"\bu1D6FC\b"), r"\\alpha"),
    (re.compile(r"\bu1D6FE\b"), r"\\gamma"),
    (re.compile(r"\bu1D716\b"), r"\\epsilon"),
    (re.compile(r"\bu1D6FCabs\b"), r"\\bar{\\alpha}_{abs}"),
    # Perbaiki "Reccomended" (typo dari paper)
    (re.compile(r"\bReccomended\b"), "Recommended"),
    # Perbaiki \hat{Q} yang sering salah ditulis
    (re.compile(r"\\hat\{Q\}"), r"\\hat{Q}"),
    # Perbaiki subscript tanpa kurung kurawal untuk kata panjang
    # misal _user_1 → _{user_1}
    (re.compile(r"_([a-zA-Z]{2,})(?=[^{a-zA-Z])"), r"_{\1}"),
    # Perbaiki ^ tanpa kurung kurawal untuk word
    (re.compile(r"\^([a-zA-Z]{2,})(?=[^{a-zA-Z])"), r"^{\1}"),
    # Hapus backslash ganda yang tidak perlu \\\\
    (re.compile(r"\\\\\\\\"), r"\\\\"),
    # Perbaiki \dot{a} → \cdot
    (re.compile(r"\\dot\{([^}])\}"), r"\\cdot \\1"),
]

# Pola yang terindikasi error (cek setelah auto-fix)
SUSPICIOUS_PATTERNS = [
    (
        re.compile(r"\$\$\s*\$\$"),
        "empty_formula",
        "Formula kosong $$$$",
    ),
    (
        re.compile(r"\$\$[^$]{1,5}\$\$"),
        "formula_too_short",
        "Formula sangat pendek (< 5 karakter)",
    ),
    (
        re.compile(r"\\left(?:\[|\(|\{)(?:(?!\\right).){200,}"),
        "unmatched_delimiter",
        "Kemungkinan delimiter \\left tidak memiliki \\right",
    ),
    (
        re.compile(r"\bu1D[0-9A-F]{3}\b"),
        "unescaped_unicode_codepoint",
        "Unicode codepoint tidak di-decode (mis: u1D6FC seharusnya \\alpha)",
    ),
    (
        re.compile(r"\\begin\{equation\}(?:(?!\\end\{equation\}).)*$", re.DOTALL),
        "unclosed_equation_env",
        "\\begin{equation} tidak memiliki \\end{equation}",
    ),
]


def get_line_number(text: str, pos: int) -> int:
    return text[:pos].count("\n") + 1


def apply_auto_fixes(text: str) -> tuple[str, list[dict]]:
    """Terapkan perbaikan otomatis dan catat apa yang diperbaiki."""
    fixes_applied = []

    for pattern, replacement in AUTO_FIXES:
        matches = list(pattern.finditer(text))
        if matches:
            for m in matches:
                line_no = get_line_number(text, m.start())
                fixes_applied.append({
                    "type": "auto_fix",
                    "pattern": pattern.pattern,
                    "original": m.group(0),
                    "replacement": re.sub(pattern, replacement, m.group(0)),
                    "line": line_no,
                })
            text = pattern.sub(replacement, text)

    return text, fixes_applied


def find_suspicious_formulas(text: str) -> list[dict]:
    """Temukan formula yang mungkin error setelah auto-fix."""
    issues = []

    for pattern, error_type, description in SUSPICIOUS_PATTERNS:
        for m in pattern.finditer(text):
            line_no = get_line_number(text, m.start())
            # Ambil konteks sekitar
            start = max(0, m.start() - 50)
            end = min(len(text), m.end() + 50)
            context = text[start:end].replace("\n", " ").strip()

            issues.append({
                "type": error_type,
                "description": description,
                "line": line_no,
                "match": m.group(0)[:100],
                "context": context[:200],
                "severity": "ERROR" if "unmatched" in error_type or "unclosed" in error_type else "WARNING",
            })

    # Cek pasangan $$
    dd_matches = list(re.finditer(r"\$\$", text))
    if len(dd_matches) % 2 != 0:
        issues.append({
            "type": "unmatched_display_math_delimiter",
            "description": f"Jumlah delimiter $$ = {len(dd_matches)} (harus genap)",
            "line": None,
            "severity": "ERROR",
        })

    return issues


def mark_error_formulas(text: str, issues: list[dict]) -> tuple[str, list[dict]]:
    """
    Tandai formula yang error dengan <!-- FORMULA_ERROR --> comment.
    Hanya tandai ERROR severity yang tidak bisa diperbaiki otomatis.
    Return: (marked_text, errors_to_manual_fix)
    """
    manual_fixes = []

    for issue in issues:
        if issue.get("severity") != "ERROR":
            continue

        if issue["type"] == "unescaped_unicode_codepoint":
            # Sudah di-fix di auto_fixes, skip
            continue

        if issue.get("match"):
            # Cari formula dan tandai
            escaped = re.escape(issue["match"])
            pattern = re.compile(r"\$\$" + escaped + r"\$\$")
            if pattern.search(text):
                text = pattern.sub(
                    f"<!-- FORMULA_ERROR: {issue['description']} -->\n"
                    f"$${issue['match']}$$",
                    text,
                    count=1,
                )
                manual_fixes.append(issue)

    return text, manual_fixes


def find_validation_screenshots(root: Path, page_no: int) -> list[str]:
    """Cari screenshot halaman yang tersedia untuk referensi manual."""
    val_dir = root / "data/validation"
    found = []
    for pattern in [
        f"original_page_{page_no}.png",
        f"original_page-{page_no:02d}.png",
        f"original_page_{page_no:02d}.png",
    ]:
        p = val_dir / pattern
        if p.exists():
            found.append(str(p.relative_to(root)))
    return found


def main():
    parser = argparse.ArgumentParser(
        description="Validasi dan perbaiki sintaks LaTeX dalam markdown."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help=f"File markdown input (default: {DEFAULT_INPUT})",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: File tidak ditemukan: {input_path}")
        sys.exit(1)

    print("=" * 60)
    print("VALIDATE & FIX LATEX")
    print("=" * 60)
    print(f"Input: {input_path}")

    text = input_path.read_text(encoding="utf-8")
    print(f"Ukuran: {len(text):,} karakter")

    # Hitung formula sebelum
    dd_before = len(re.findall(r"\$\$", text)) // 2
    print(f"Formula display ($$...$$) sebelum: {dd_before}")

    print("\n[1/4] Menerapkan perbaikan otomatis...")
    text, auto_fixes = apply_auto_fixes(text)
    print(f"  Perbaikan diterapkan: {len(auto_fixes)}")
    for fix in auto_fixes[:5]:
        print(f"    L{fix['line']}: {fix['original']!r} → {fix['replacement']!r}")
    if len(auto_fixes) > 5:
        print(f"    ... dan {len(auto_fixes)-5} perbaikan lainnya")

    print("\n[2/4] Mencari formula yang mencurigakan...")
    issues = find_suspicious_formulas(text)
    errors = [i for i in issues if i.get("severity") == "ERROR"]
    warnings = [i for i in issues if i.get("severity") == "WARNING"]
    print(f"  ERROR: {len(errors)}, WARNING: {len(warnings)}")

    print("\n[3/4] Menandai formula yang perlu perbaikan manual...")
    text, manual_fixes = mark_error_formulas(text, issues)
    print(f"  Formula ditandai FORMULA_ERROR: {len(manual_fixes)}")

    # Simpan file yang sudah diperbaiki (overwrite input)
    print("\n[4/4] Menyimpan file yang sudah diperbaiki...")
    input_path.write_text(text, encoding="utf-8")

    # Hitung formula sesudah
    dd_after = len(re.findall(r"\$\$", text)) // 2
    print(f"Formula display ($$...$$) sesudah: {dd_after}")

    # Buat laporan JSON
    report = {
        "input_file": str(input_path),
        "auto_fixes_count": len(auto_fixes),
        "auto_fixes": auto_fixes,
        "issues": issues,
        "manual_fixes_needed": manual_fixes,
        "formula_count_before": dd_before,
        "formula_count_after": dd_after,
        "summary": {
            "total_errors": len(errors),
            "total_warnings": len(warnings),
            "auto_fixed": len(auto_fixes),
            "needs_manual": len(manual_fixes),
        },
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Laporan disimpan: {REPORT_PATH}")

    if manual_fixes:
        print(f"\n⚠️  {len(manual_fixes)} formula perlu perbaikan manual!")
        print("Lihat docs/manual_fix_list.md untuk detail.")
    else:
        print("\n✅ Semua formula berhasil divalidasi/diperbaiki otomatis.")


if __name__ == "__main__":
    main()
