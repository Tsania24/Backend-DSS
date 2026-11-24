#!/usr/bin/env python3
"""
clean_markdown.py
-----------------
Tahap 1 Pembersihan Markdown:
1. Membaca sumber Markdown LlamaParse yang memiliki rumus LaTeX lengkap.
2. Membersihkan artefak ekstraksi (header jurnal, footer, nomor halaman, logo, email, afiliasi).
3. Menormalkan hierarki heading (# Judul, ## Bagian, ### Sub-bagian) dan menghapus heading palsu.
4. Memvalidasi dan memperbaiki sintaks LaTeX secara otomatis.
5. Menandai rumus yang gagal divalidasi dengan <!-- FORMULA_ERROR -->.
6. Menyimpan hasil ke data/markdown/furniture_arrangement_ieq_2023_clean.md.

Idempotent: aman dijalankan berulang kali.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent

# Sumber utama: LlamaParse playground original yang memiliki rumus lengkap
SOURCE_PRIMARY = ROOT / "data/llamaparse_playground_original/furniture_arrangement_ieq_2023.md"
SOURCE_FALLBACK = ROOT / "data/markdown/furniture_arrangement_ieq_2023.md"
OUTPUT = ROOT / "data/markdown/furniture_arrangement_ieq_2023_clean.md"
LATEX_REPORT = ROOT / "docs/latex_validation_report.json"

# ── Pola artefak ekstraksi ───────────────────────────────────────────────────

ARTIFACT_PATTERNS = [
    # Logo / drawing / icon markers
    re.compile(r"^icon:\s*.+$", re.MULTILINE),
    re.compile(r"^logo:\s*.+$", re.MULTILINE),
    re.compile(r"^drawing:\s*.+$", re.MULTILINE),
    # Header jurnal Springer
    re.compile(
        r"^(?:Journal of Ambient Intelligence.*|"
        r"A multi-objective reinforcement learning approach for furniture.*16\d{3}|"
        r"\d{5}\s+P\. Ribino.*|"
        r"16\d{3}\s+P\. Ribino.*)\s*$",
        re.MULTILINE,
    ),
    # Footer / page range referensi jurnal
    re.compile(r"^\s*\d{5}[-–]\d{5}\s*$", re.MULTILINE),
    # Springer logo marker inline
    re.compile(r"logo:\s*Springer(?: logo Springer)?", re.IGNORECASE),
    re.compile(r"\b1675\d\s+P\.\s+Ribino[^.]*\.", re.IGNORECASE),
    # Email penulis
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    # Afiliasi penulis baris tunggal
    re.compile(
        r"(?im)^[✉*]\s*Patrizia Ribino\s*$|"
        r"^\*\s*Patrizia Ribino\s*$|"
        r"^Marina Bonomolo\s*$|"
        r"^<[^>]+>\s*$|"
        r"^<sup>\d+</sup>\s*(?:Istituto|Dipartimento).*$"
    ),
    # HTML superscript tags
    re.compile(r"</?sup>", re.IGNORECASE),
    # Referensi footnote afiliasi
    re.compile(
        r"(?im)^\d\s+(?:Istituto di Calcolo|Dipartimento di Ingegneria).*$"
    ),
    # URL berdiri sendiri (bukan markdown link)
    re.compile(r"^https?://\S+\s*$", re.MULTILINE),
    # Titik soliter akibat patahan baris URL
    re.compile(r"^\.\s*$", re.MULTILINE),
    # Karakter kontrol BEL (\x07)
    re.compile(r"\x07"),
    # Heading / baris palsu yang hanya nomor atau '1 3' (nomor halaman jurnal)
    re.compile(r"^#{1,6}\s*1\s+3\s*$", re.MULTILINE),
    re.compile(r"^1\s+3\s*$", re.MULTILINE),
    # Artefak '#Test' atau '#Test seconds...'
    re.compile(r"^#{1,6}\s*Test\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^Test\s*$", re.MULTILINE),
    re.compile(r"^Test\s+OFFICE\s+#\d+\s*$", re.MULTILINE | re.IGNORECASE),
]

REPLACEMENTS = [
    # Sambung kembali kalimat yang terputus oleh floating table Fig. 1 di Section 4
    (
        re.compile(
            r"into the direction of the\s+<table>.*?</table>\s*\*{0,2}Fig\. 1\*{0,2}[^\n]*\s*best-scalarized action",
            re.DOTALL,
        ),
        "into the direction of the best-scalarized action",
    ),
    # Sambung kembali kalimat yang terputus oleh floating table Fig. 2 di Section 5
    (
        re.compile(
            r"Moreover, the\s+<table>.*?</table>\s*\*{0,2}Fig\. 2\*{0,2}[^\n]*\s*coordinates of each cell room",
            re.DOTALL,
        ),
        "Moreover, the coordinates of each cell room",
    ),
    # Perbaiki sitasi yang terpotong akibat ekstraksi halaman
    (re.compile(r"Colenberg\s*\n\s*et al\."), "Colenberg et al."),
    # Ubah heading '#Test seconds...' menjadi teks biasa
    (re.compile(r"^#{1,4}Test\s+(seconds\b.*)", re.MULTILINE), r"\1"),
    # Hapus bold markers dari heading (akan dinormalisasi)
    (re.compile(r"^(#{1,6})\s+\*\*([^*]+)\*\*", re.MULTILINE), r"\1 \2"),
]

# ── Perbaikan LaTeX otomatis ──────────────────────────────────────────────────

AUTO_LATEX_FIXES = [
    (re.compile(r"\bu1D6FC\b"), r"\\alpha"),
    (re.compile(r"\bu1D6FE\b"), r"\\gamma"),
    (re.compile(r"\bu1D716\b"), r"\\epsilon"),
    (re.compile(r"\bu1D6FCabs\b"), r"\\bar{\\alpha}_{abs}"),
    (re.compile(r"\bReccomended\b"), "Recommended"),
    (re.compile(r"\\hat\{Q\}"), r"\\hat{Q}"),
    (re.compile(r"_([a-zA-Z]{2,})(?=[^{a-zA-Z])"), r"_{\1}"),
    (re.compile(r"\^([a-zA-Z]{2,})(?=[^{a-zA-Z])"), r"^{\1}"),
    (re.compile(r"\\\\\\\\"), r"\\\\"),
    (re.compile(r"\\dot\{([^}])\}"), r"\\cdot \\1"),
]


def clean_text_artifacts(text: str) -> str:
    """Membersihkan artefak teks umum."""
    for pattern in ARTIFACT_PATTERNS:
        text = pattern.sub("", text)

    for pattern, replacement in REPLACEMENTS:
        text = pattern.sub(replacement, text)

    # Rapikan baris kosong berlebihan
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def normalize_heading_level(heading_text: str) -> int:
    """Menentukan level heading (# untuk judul, ## untuk section, ### untuk subsection)."""
    text_lower = heading_text.strip().lower()

    # Judul paper utama -> level 1 (#)
    if "multi-objective reinforcement learning approach for furniture" in text_lower:
        return 1

    # Subsection bernomor: 3.1, 4.2, 5.1.1 -> level 3 atau 4
    if re.match(r"^\d+\.\d+\.\d+", text_lower):
        return 4
    if re.match(r"^\d+\.\d+", text_lower):
        return 3

    # Section bernomor: 1 Introduction, 2 Related works, dll. -> level 2 (##)
    if re.match(r"^\d+\s+\w", text_lower):
        return 2

    # Bagian algoritma
    if re.match(r"^algorithm \d+", text_lower):
        return 3

    # Top-level sections bernama
    named_top_sections = {
        "abstract", "introduction", "related works", "theoretical background",
        "materials and methods", "experimental evaluation",
        "algorithm comparison", "conclusions", "declarations", "references",
        "funding", "acknowledgements"
    }
    if text_lower in named_top_sections:
        return 2

    # Default heading level
    return 2


def normalize_all_headings(text: str) -> str:
    """Normalisasi semua heading dalam dokumen markdown."""
    lines = text.splitlines()
    result = []

    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.+?)$", line)
        if m:
            heading_text = m.group(2).strip()
            # Hapus bold markers bila tersisa di heading
            heading_text = re.sub(r"\*\*([^*]+)\*\*", r"\1", heading_text).strip()

            # Skip heading kosong atau hanya angka
            if not heading_text or re.fullmatch(r"[\d\s]+", heading_text):
                continue

            level = normalize_heading_level(heading_text)
            result.append(f"{'#' * level} {heading_text}")
        else:
            result.append(line)

    return "\n".join(result)


def validate_and_fix_latex(text: str) -> tuple[str, list[dict], list[dict]]:
    """Memperbaiki sintaks LaTeX umum dan memvalidasi pasangan delimiter."""
    fixes_applied = []
    issues = []

    # Terapkan perbaikan otomatis
    for pattern, replacement in AUTO_LATEX_FIXES:
        matches = list(pattern.finditer(text))
        for m in matches:
            line_no = text[:m.start()].count("\n") + 1
            fixes_applied.append({
                "type": "auto_fix",
                "original": m.group(0),
                "replacement": pattern.sub(replacement, m.group(0)),
                "line": line_no,
            })
        text = pattern.sub(replacement, text)

    # Validasi display math delimiters ($$)
    dd_matches = list(re.finditer(r"\$\$", text))
    if len(dd_matches) % 2 != 0:
        issues.append({
            "type": "unmatched_display_math",
            "description": f"Jumlah delimiter $$ = {len(dd_matches)} (harus genap)",
            "severity": "ERROR",
        })

    # Cek setiap display formula
    for m in re.finditer(r"\$\$(.+?)\$\$", text, re.DOTALL):
        formula = m.group(1).strip()
        line_no = text[:m.start()].count("\n") + 1

        if len(formula) < 2:
            issues.append({
                "type": "empty_formula",
                "line": line_no,
                "description": "Rumus kosong di dalam delimiter $$",
                "severity": "ERROR",
            })

    # Tandai rumus yang bermasalah dengan FORMULA_ERROR
    for issue in issues:
        if issue.get("severity") == "ERROR" and "formula" in issue:
            formula_text = issue.get("formula", "")
            if formula_text:
                target = f"$${formula_text}$$"
                replacement = f"<!-- FORMULA_ERROR: {issue['description']} -->\n{target}"
                text = text.replace(target, replacement, 1)

    return text, fixes_applied, issues


def main():
    print("=" * 60)
    print("CLEAN MARKDOWN PIPELINE")
    print("=" * 60)

    # Pilih sumber yang tersedia
    source_path = SOURCE_PRIMARY if SOURCE_PRIMARY.exists() else SOURCE_FALLBACK
    if not source_path.exists():
        print(f"ERROR: Sumber markdown tidak ditemukan: {source_path}")
        sys.exit(1)

    print(f"Membaca sumber: {source_path}")
    text = source_path.read_text(encoding="utf-8")
    original_size = len(text.encode("utf-8"))

    # 1. Bersihkan artefak
    print("[1/3] Membersihkan artefak ekstraksi...")
    text = clean_text_artifacts(text)

    # 2. Normalisasi heading
    print("[2/3] Menormalkan hierarki heading...")
    text = normalize_all_headings(text)

    # 3. Validasi dan auto-fix LaTeX
    print("[3/3] Memvalidasi dan memperbaiki LaTeX...")
    text, fixes_applied, issues = validate_and_fix_latex(text)
    print(f"  Perbaikan LaTeX diterapkan : {len(fixes_applied)}")
    print(f"  Masalah LaTeX ditemukan    : {len(issues)}")

    # Simpan laporan validasi LaTeX
    LATEX_REPORT.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "source": str(source_path),
        "output": str(OUTPUT),
        "fixes_applied_count": len(fixes_applied),
        "issues_count": len(issues),
        "issues": issues,
    }
    LATEX_REPORT.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Tulis output
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text.strip() + "\n", encoding="utf-8")

    clean_size = len(OUTPUT.read_bytes())
    display_formulas = len(re.findall(r"\$\$", text)) // 2

    print(f"\nPembersihan selesai.")
    print(f"Ukuran asli    : {original_size / 1024:.1f} KB")
    print(f"Ukuran bersih  : {clean_size / 1024:.1f} KB")
    print(f"Rumus display  : {display_formulas}")
    print(f"Output         : {OUTPUT}")


if __name__ == "__main__":
    main()
