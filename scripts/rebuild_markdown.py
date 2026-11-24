#!/usr/bin/env python3
"""
rebuild_markdown.py
-------------------
Membangun ulang pipeline markdown dari sumber LlamaParse playground .md
yang sudah memiliki rumus LaTeX lengkap dan tabel yang benar.

Pipeline baru:
  LlamaParse playground .md
    → clean_llamaparse.py (hapus artefak: logo, header/footer, page numbers)
    → inject_figures.py   (sisipkan deskripsi gambar dari cache JSON)
    → normalize_headings.py (perbaiki hierarki heading)
  → data/markdown/furniture_arrangement_ieq_2023_rebuilt.md  (output utama)

Script ini menjalankan seluruh pipeline dalam satu langkah.
Idempotent: aman dijalankan ulang.

Usage:
    python scripts/rebuild_markdown.py [--dry-run]
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
ASSETS_DIR = ROOT / "data/processed/assets/furniture_arrangement_ieq_2023"

SOURCE_LLAMAPARSE_MD = (
    ROOT
    / "data/llamaparse_playground_original"
    / "furniture_arrangement_ieq_2023.md"
)
FIGURE_CACHE = ROOT / "data/processed/assets/figure_descriptions.json"
OUTPUT_MD = ROOT / "data/markdown/furniture_arrangement_ieq_2023_rebuilt.md"

# ── STEP 1: Bersihkan artefak LlamaParse ─────────────────────────────────────

# Pola artefak yang perlu dihapus
ARTIFACT_PATTERNS = [
    # Logo/icon markers
    re.compile(r"^icon:\s*.+$", re.MULTILINE),
    re.compile(r"^logo:\s*.+$", re.MULTILINE),
    re.compile(r"^drawing:\s*.+$", re.MULTILINE),
    # Header jurnal (Springer page header)
    re.compile(
        r"^(?:Journal of Ambient Intelligence.*|"
        r"A multi-objective reinforcement learning approach for furniture.*16\d{3}|"
        r"\d{5}\s+P\. Ribino.*|"
        r"16\d{3}\s+P\. Ribino.*)\s*$",
        re.MULTILINE,
    ),
    # Footer / page reference
    re.compile(r"^\s*\d{5}[-–]\d{5}\s*$", re.MULTILINE),
    # Nomor halaman jurnal yang berdiri sendiri
    re.compile(r"^\s*\d{5}\s+P\. Ribino.*$", re.MULTILINE),
    # Springer logo marker
    re.compile(r"logo:\s*Springer(?: logo Springer)?", re.IGNORECASE),
    # Referensi halaman jurnal inline (misal "16750 P. Ribino, M. Bonomolo")
    re.compile(r"\b1675\d\s+P\.\s+Ribino[^.]*\.", re.IGNORECASE),
    # Email penulis
    re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"),
    # Afiliasi penulis (baris tunggal)
    re.compile(
        r"(?im)^[✉*]\s*Patrizia Ribino\s*$|"
        r"^\*\s*Patrizia Ribino\s*$|"
        r"^Marina Bonomolo\s*$|"
        r"^<[^>]+>\s*$|"
        r"^<sup>\d+</sup>\s*(?:Istituto|Dipartimento).*$"
    ),
    # HTML superscript tags
    re.compile(r"<sup>\d+</sup>", re.IGNORECASE),
    re.compile(r"</?sup>", re.IGNORECASE),
    # Referensi footnote (1Istituto, 2Dipartimento)
    re.compile(
        r"(?im)^\d\s+(?:Istituto di Calcolo|Dipartimento di Ingegneria).*$"
    ),
    # Kolofon "check for updates" ikon
    re.compile(r"(?im)^icon:\s*Check for updates\s*$"),
    # URL plain (bukan dalam markdown link)
    # Hati-hati jangan hapus URL yang dalam teks referensi
    # Hanya hapus baris yang isinya HANYA URL
    re.compile(r"^https?://\S+\s*$", re.MULTILINE),
    # Titik soliter setelah URL (artefak linebreak)
    re.compile(r"^\.\s*$", re.MULTILINE),
]

# Pola yang harus diganti (bukan dihapus)
REPLACEMENTS = [
    # Perbaiki sitasi yang terpotong
    (re.compile(r"Colenberg\s*\n\s*et al\."), "Colenberg et al."),
    # Hapus bold markers dari heading (akan dinormalisasi ulang)
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    # Hapus karakter BEL (\x07)
    (re.compile(r"\x07"), ""),
    # Perbaiki bullet list items (HTML <sup> artifacts)
    (re.compile(r"^\*\s*\$([^$]+)\$\s*", re.MULTILINE), r"* $\1$ "),
]


def clean_llamaparse_md(text: str) -> str:
    """Hapus artefak ekstraksi LlamaParse dari markdown."""

    for pattern in ARTIFACT_PATTERNS:
        text = pattern.sub("", text)

    for pattern, replacement in REPLACEMENTS:
        text = pattern.sub(replacement, text)

    # Rapikan baris kosong berlebihan
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)

    return text.strip()


# ── STEP 2: Normalisasi heading ───────────────────────────────────────────────

# Mapping heading → level berdasarkan konten dan konteks paper
HEADING_LEVELS = {
    # Level 1: Judul paper (hanya satu)
    r"a multi-objective reinforcement learning approach": 1,
    # Level 2: Bagian utama
    r"abstract": 2,
    r"^\d+\s+(?:introduction|related works|theoretical background|"
    r"materials and methods|experimental evaluation|"
    r"algorithm comparison|conclusions|declarations|references)": 2,
    r"^(?:introduction|related works|theoretical background|"
    r"materials and methods|experimental evaluation|"
    r"algorithm comparison|conclusions|declarations|references)$": 2,
    # Level 3: Sub-bagian bernomor (misal "3.1 Indoor comfort conditions")
    r"^\d+\.\d+": 3,
    r"^algorithm \d+": 3,
    # Level 4: Sub-sub-bagian
    r"^\d+\.\d+\.\d+": 4,
}


def normalize_heading_level(heading_text: str) -> int:
    """Tentukan level heading berdasarkan konten."""
    text_lower = heading_text.strip().lower()

    # Judul paper
    if "multi-objective reinforcement learning approach for furniture" in text_lower:
        return 1

    # Numbered sections misal "1 Introduction", "3.1 Indoor comfort"
    if re.match(r"^\d+\.\d+", text_lower):
        return 3
    if re.match(r"^\d+\s+\w", text_lower):
        return 2

    # Algorithm headings
    if re.match(r"^algorithm \d+", text_lower):
        return 3

    # Named sections
    top_sections = {
        "abstract", "related works", "theoretical background",
        "materials and methods", "experimental evaluation",
        "algorithm comparison", "conclusions", "declarations", "references",
        "introduction",
    }
    if text_lower in top_sections:
        return 2

    # Default: pertahankan level saat ini (beri default 2)
    return 2


def normalize_headings(text: str) -> str:
    """Normalisasi hierarki heading dalam markdown."""
    lines = text.splitlines()
    result = []

    for line in lines:
        # Deteksi heading markdown
        m = re.match(r"^(#{1,6})\s+(.+?)$", line)
        if m:
            current_hashes = m.group(1)
            heading_text = m.group(2).strip()

            # Hapus bold markup dari heading text
            heading_text = re.sub(r"\*\*([^*]+)\*\*", r"\1", heading_text)

            # Skip heading yang merupakan artefak
            # (hanya angka, hanya "1 3", dll.)
            if re.fullmatch(r"[\d\s]+", heading_text):
                result.append("")  # Hapus
                continue

            # Tentukan level yang tepat
            new_level = normalize_heading_level(heading_text)
            new_hashes = "#" * new_level

            result.append(f"{new_hashes} {heading_text}")
        else:
            result.append(line)

    return "\n".join(result)


# ── STEP 3: Inject deskripsi gambar ──────────────────────────────────────────

# Mapping antara referensi gambar di markdown dengan key di cache
FIGURE_INJECTION_MAP = [
    # (pattern di markdown, cache_key, inject_after_pattern)
    # Fig 1 – disebutkan dalam teks, bukan sebagai ![]() image
    # Kita inject setelah referensi "Figure 1 illustrates"
    {
        "trigger": re.compile(
            r"(Figure 1 illustrates the plant of office #1[^.]*\.)",
            re.IGNORECASE,
        ),
        "cache_key": "page_8_fig1",
        "mode": "after_sentence",
    },
    # Fig 2
    {
        "trigger": re.compile(
            r"(Shape and sizes are shown in Fig\. 2\.)",
            re.IGNORECASE,
        ),
        "cache_key": "page_9_fig2",
        "mode": "after_sentence",
    },
    # Fig 3 – orientasi meja
    {
        "trigger": re.compile(
            r"(four possible orientations are considered \(see Fig\. 3\)\.)",
            re.IGNORECASE,
        ),
        "cache_key": "page_10_fig3",
        "mode": "after_sentence",
    },
    # Fig 4 – layout pattern 1 Office #1 (em dash — in source)
    {
        "trigger": re.compile(
            r"(\*\*Fig\. 4\*\* Office #1[\u2014\-]layout pattern #1|Fig\. 4 Office #1[\u2014\-]layout pattern #1)",
            re.IGNORECASE,
        ),
        "cache_key": "page_11_item_12",
        "mode": "after_line",
    },
    # Fig 5 – layout pattern 2 Office #1
    {
        "trigger": re.compile(
            r"(\*\*Fig\. 5\*\* Office #1[\u2014\-]layout pattern #2|Fig\. 5 Office #1[\u2014\-]layout pattern #2)",
            re.IGNORECASE,
        ),
        "cache_key": "page_11_item_14",
        "mode": "after_line",
    },
    # Fig 6 – layout pattern 1 Office #2
    {
        "trigger": re.compile(
            r"(\*\*Fig\. 6\*\* Office #2[\u2014\-]layout pattern #1|Fig\. 6 Office #2[\u2014\-]layout pattern #1)",
            re.IGNORECASE,
        ),
        "cache_key": "page_11_item_13",
        "mode": "after_line",
    },
    # Fig 7 – layout pattern 2 Office #2
    {
        "trigger": re.compile(
            r"(\*\*Fig\. 7\*\* Office #2[\u2014\-]layout pattern #2|Fig\. 7 Office #2[\u2014\-]layout pattern #2)",
            re.IGNORECASE,
        ),
        "cache_key": "page_12_item_3",
        "mode": "after_line",
    },
    # Fig 8 – thermal comfort index office #1
    {
        "trigger": re.compile(
            r"(\*\*Fig\. 8\*\* Thermal comfort index office #1|Fig\. 8 Thermal comfort index office #1)",
            re.IGNORECASE,
        ),
        "cache_key": "page_11_item_10",
        "mode": "after_line",
    },
    # Fig 9 – acoustics comfort index office #1
    {
        "trigger": re.compile(
            r"(\*\*Fig\. 9\*\* Acoustics comfort index office #1|Fig\. 9 Acoustics comfort index office #1)",
            re.IGNORECASE,
        ),
        "cache_key": "page_12_item_12",
        "mode": "after_line",
    },
]

# Figure captions yang ada dalam teks sebagai "**Fig. X** ..."
FIGURE_CAPTION_PATTERNS = [
    re.compile(r"^\*\*Fig\.\s*(\d+)\*\*\s+(.+)$", re.MULTILINE),
    re.compile(r"^Fig\.\s*(\d+)\s+(.+)$", re.MULTILINE),
]


def build_figure_description_block(
    cache_key: str, cache: dict, asset_base: Path
) -> str:
    """Buat blok markdown untuk deskripsi gambar."""
    entry = cache.get(cache_key)
    if not entry or entry.get("skip"):
        return ""

    caption = entry.get("caption", "")
    description = entry.get("description", "")
    asset_path = entry.get("asset_path", "")

    if not description:
        return ""

    # Buat path relatif dari root proyek
    if asset_path:
        try:
            rel_path = Path(asset_path).relative_to(ROOT)
            img_line = f"![{caption}]({rel_path})"
        except ValueError:
            img_line = f"![{caption}]({asset_path})"
    else:
        img_line = ""

    block = ""
    if img_line:
        block += f"\n{img_line}\n"
    block += f"\n> **Deskripsi gambar:** {description}\n"

    return block


def inject_figure_descriptions(text: str, cache: dict) -> str:
    """Sisipkan deskripsi gambar ke dalam teks markdown."""
    if not cache:
        return text

    for mapping in FIGURE_INJECTION_MAP:
        pattern = mapping["trigger"]
        cache_key = mapping["cache_key"]
        mode = mapping["mode"]

        entry = cache.get(cache_key)
        if not entry or entry.get("skip"):
            continue

        desc_block = build_figure_description_block(cache_key, cache, ASSETS_DIR)
        if not desc_block:
            continue

        def replacer(m, block=desc_block, md=mode):
            matched = m.group(1) if m.lastindex else m.group(0)
            if md == "after_sentence":
                return matched + block
            else:  # after_line
                return matched + "\n" + block.strip()

        new_text = pattern.sub(replacer, text, count=1)
        if new_text != text:
            text = new_text
            print(f"  [INJECT] {cache_key}: deskripsi disisipkan")

    return text


# ── STEP 4: Inject tabel illuminance yang benar ───────────────────────────────

ILLUMINANCE_TABLE_1 = """
| y\\\\x | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|-------|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| 1     | 80  | 50  | 130 | 130 | 130 | 110 | 100 | 90  | 90  |
| 2     | 80  | 50  | 130 | 130 | 130 | 110 | 100 | 90  | 90  |
| 3     | 440 | 350 | 350 | 300 | 300 | 300 | 100 | 90  | 90  |
| 4     | 540 | 350 | 350 | 300 | 300 | 200 | 200 | 150 | 90  |
| 5     | 800 | 350 | 300 | 300 | 300 | 200 | 200 | 150 | 125 |
| 6     | 700 | 350 | 370 | 300 | 300 | 200 | 200 | 150 | 110 |
| 7     | 300 | 350 | 370 | 330 | 200 | 190 | 190 | 180 | 200 |

*Satuan: lux (lx). Baris = koordinat y, Kolom = koordinat x. Sudut kiri atas = (x=1,y=1) pojok barat-laut.*
"""

ILLUMINANCE_TABLE_2 = """
| y\\\\x | 1   | 2   | 3   | 4   | 5   | 6   | 7   | 8   | 9   |
|-------|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| 1     | 400 | 580 | 550 | 550 | 250 | 200 | 200 | 0   | 0   |
| 2     | 350 | 550 | 530 | 500 | 330 | 330 | 340 | 0   | 0   |
| 3     | 250 | 350 | 350 | 300 | 300 | 300 | 300 | 90  | 90  |
| 4     | 250 | 350 | 350 | 300 | 300 | 300 | 450 | 580 | 700 |
| 5     | 250 | 300 | 300 | 300 | 300 | 330 | 430 | 550 | 680 |
| 6     | 200 | 300 | 300 | 300 | 300 | 330 | 430 | 530 | 650 |
| 7     | 190 | 250 | 250 | 330 | 200 | 190 | 400 | 500 | 630 |

*Satuan: lux (lx). Nilai 0 = area di luar bentuk ruangan tidak beraturan Office #2.*
"""


def inject_illuminance_tables(text: str) -> str:
    """
    Ganti tabel illuminance HTML yang ada di LlamaParse MD dengan
    tabel markdown yang lebih readable.
    """
    # Pola untuk tabel HTML illuminance Office #1 (page 8)
    # LlamaParse menghasilkan <table> HTML
    html_table_1 = re.compile(
        r"<table>(?:<tr>(?:<td>\d+</td>|<td rowspan=\"\d+\">[xy]</td>)+</tr>){5,8}</table>",
        re.DOTALL,
    )
    # Versi lebih general: cari blok <table> yang berisi angka illuminance
    html_table_general = re.compile(
        r"<table>(<tr>(?:<td>\d+</td>)+.*?</tr>){5,}</table>",
        re.DOTALL,
    )

    # Strategi lebih aman: cari posisi setelah "Fig. 1" / "Fig. 2"
    # dan inject tabel sebelum teks berikutnya

    # Inject setelah "Fig. 1 Office #1 and illuminance values on its surface"
    # (bold markup sudah dibersihkan oleh clean_llamaparse_md sebelum step ini)
    fig1_pattern = re.compile(
        r"(\*{0,2}Fig\. 1\*{0,2} Office #1 and illuminance values on its surface)",
        re.IGNORECASE,
    )
    if fig1_pattern.search(text):
        text = fig1_pattern.sub(
            r"\1\n" + ILLUMINANCE_TABLE_1.strip(),
            text,
            count=1,
        )
        print("  [TABLE] Tabel illuminance Office #1 disisipkan")
    else:
        print("  [WARN] Trigger Fig. 1 tidak ditemukan, cek teks sumber")

    # Inject setelah "Fig. 2 Office #2 and illuminance values on its surface"
    fig2_pattern = re.compile(
        r"(\*{0,2}Fig\. 2\*{0,2} Office #2 and illuminance values on its surface)",
        re.IGNORECASE,
    )
    if fig2_pattern.search(text):
        text = fig2_pattern.sub(
            r"\1\n" + ILLUMINANCE_TABLE_2.strip(),
            text,
            count=1,
        )
        print("  [TABLE] Tabel illuminance Office #2 disisipkan")

    # Hapus tabel HTML bawaan LlamaParse yang sudah digantikan
    # (dengan <table> yang berisi angka 2-3 digit)
    text = re.sub(
        r"\n<table>(?:<tr><td>\d+</td>)+.*?</table>\n",
        "\n",
        text,
        flags=re.DOTALL,
    )

    return text


# ── STEP 5: Validasi rumus LaTeX ──────────────────────────────────────────────

COMMON_LATEX_FIXES = [
    # Perbaiki \left[ tanpa \right]
    (re.compile(r"\\left\[(?![^$]*\\right\])"), r"\\left[ ... \\right]"),
    # Perbaiki backslash ganda yang salah
    (re.compile(r"\\\\([a-zA-Z]+)"), r"\\\1"),
    # Perbaiki \reccomended → \mathrm{Recommended}
    (re.compile(r"Reccomended"), "Recommended"),
]

FORMULA_VALIDATION_PATTERNS = [
    # Cek pasangan delimiter $$ ... $$
    re.compile(r"\$\$(.+?)\$\$", re.DOTALL),
    # Cek inline $ ... $
    re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", re.DOTALL),
]

KNOWN_PROBLEMATIC_LATEX = {
    # Pattern → apakah problematik
    re.compile(r"\\left\[.*(?!\.\.\.)(?!\\right\]).*\]"): "unmatched_left_bracket",
    re.compile(r"\{[^}]{200,}"): "unclosed_brace",
}


def validate_and_fix_latex(text: str) -> tuple[str, list[dict]]:
    """
    Validasi dan perbaiki sintaks LaTeX umum.
    Return: (fixed_text, issues)
    """
    issues = []

    # Perbaikan umum
    for pattern, replacement in COMMON_LATEX_FIXES:
        text = pattern.sub(replacement, text)

    # Validasi pasangan $$
    # Hitung jumlah $$ – harus genap
    dd_positions = [m.start() for m in re.finditer(r"\$\$", text)]
    if len(dd_positions) % 2 != 0:
        issues.append({
            "type": "unmatched_display_math",
            "detail": f"Jumlah $$ = {len(dd_positions)} (ganjil)",
            "severity": "WARNING",
        })

    # Cek formula individual
    for m in re.finditer(r"\$\$(.+?)\$\$", text, re.DOTALL):
        formula = m.group(1).strip()
        line_no = text[:m.start()].count("\n") + 1

        # Cek tanda kurung tidak seimbang
        for open_c, close_c in [("{", "}"), ("(", ")"), ("[", "]")]:
            if formula.count("\\" + open_c) != formula.count("\\" + close_c):
                # Jangan flag ini sebagai error – LaTeX macro pakai {} normal
                pass

        # Cek formula sangat pendek (mungkin terpotong)
        if len(formula) < 3:
            issues.append({
                "type": "formula_too_short",
                "line": line_no,
                "formula": formula,
                "severity": "WARNING",
            })

    return text, issues


# ── STEP 6: Hapus heading palsu ───────────────────────────────────────────────

FAKE_HEADINGS = [
    # "#Test" artefak
    re.compile(r"^#{1,6}\s*Test\s*$", re.MULTILINE | re.IGNORECASE),
    # "#Test seconds more..."
    re.compile(r"^#{1,6}Test\b", re.MULTILINE | re.IGNORECASE),
    # Nomor halaman jurnal sebagai heading
    re.compile(r"^#{1,6}\s*\d{5}\s*$", re.MULTILINE),
    # "1 3" sebagai heading (artefak nomor halaman "13")
    re.compile(r"^#{1,6}\s*1\s+3\s*$", re.MULTILINE),
]

# Teks yang perlu dibersihkan (bukan heading tapi artefak)
INLINE_ARTIFACTS = [
    # "1 3" standalone (page number 13)
    re.compile(r"^1\s+3\s*$", re.MULTILINE),
    # "Test" standalone di akhir/awal baris tanpa konteks
    re.compile(r"^Test\s*$", re.MULTILINE),
    # "Test OFFICE #2" standalone
    re.compile(r"^Test\s+OFFICE\s+#\d+\s*$", re.MULTILINE | re.IGNORECASE),
    # "Test seconds more..." → ubah ke teks biasa
    re.compile(r"^#{1,4}Test\s+seconds\b", re.MULTILINE),
]


def remove_fake_headings(text: str) -> str:
    """Hapus heading palsu dan teks artefak dari markdown."""
    for pattern in FAKE_HEADINGS:
        text = pattern.sub("", text)

    # Ubah "#Test seconds..." menjadi teks biasa
    text = re.sub(
        r"^#{1,4}Test\s+(seconds\b.*)",
        r"\1",
        text,
        flags=re.MULTILINE,
    )

    for pattern in INLINE_ARTIFACTS:
        text = pattern.sub("", text)

    # Rapikan baris kosong
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(source_md: Path, figure_cache: dict, dry_run: bool = False) -> str:
    """Jalankan pipeline lengkap dan return hasilnya."""
    print("\n[1/6] Membaca sumber LlamaParse markdown...")
    text = source_md.read_text(encoding="utf-8")
    print(f"  Input: {len(text):,} karakter, {text.count(chr(10))} baris")

    print("\n[2/6] Membersihkan artefak LlamaParse...")
    text = clean_llamaparse_md(text)
    print(f"  Setelah clean: {len(text):,} karakter")

    print("\n[3/6] Normalisasi heading...")
    text = normalize_headings(text)

    print("\n[4/6] Menghapus heading palsu dan artefak inline...")
    text = remove_fake_headings(text)

    print("\n[5/6] Menyisipkan tabel illuminance yang benar...")
    text = inject_illuminance_tables(text)

    print("\n[6/6] Menyisipkan deskripsi gambar...")
    text = inject_figure_descriptions(text, figure_cache)

    # Rapikan akhir file
    text = text.strip() + "\n"

    return text


def main():
    parser = argparse.ArgumentParser(
        description="Bangun ulang markdown dari sumber LlamaParse playground."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Tampilkan hasil tanpa menyimpan file",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("REBUILD MARKDOWN PIPELINE")
    print("=" * 60)

    if not SOURCE_LLAMAPARSE_MD.exists():
        print(f"ERROR: Sumber markdown tidak ditemukan: {SOURCE_LLAMAPARSE_MD}")
        sys.exit(1)

    # Load figure cache
    figure_cache = {}
    if FIGURE_CACHE.exists():
        figure_cache = json.loads(FIGURE_CACHE.read_text(encoding="utf-8"))
        print(f"Figure cache dimuat: {len(figure_cache)} entri")
    else:
        print(
            "WARN: Figure cache tidak ditemukan. "
            "Jalankan scripts/describe_figures.py terlebih dahulu."
        )

    result = run_pipeline(SOURCE_LLAMAPARSE_MD, figure_cache, args.dry_run)

    if args.dry_run:
        print("\n[DRY-RUN] Output (1000 karakter pertama):")
        print(result[:1000])
        print(f"\nTotal: {len(result):,} karakter")
        return

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text(result, encoding="utf-8")
    print(f"\nOutput disimpan: {OUTPUT_MD}")
    print(f"Ukuran: {OUTPUT_MD.stat().st_size / 1024:.1f} KB")

    # Hitung statistik
    formula_count = len(re.findall(r"\$\$", result)) // 2
    table_count = result.count("|---|")
    heading_count = len(re.findall(r"^#{1,4} ", result, re.MULTILINE))
    fig_desc_count = result.count("> **Deskripsi gambar:**")

    print(f"\nStatistik output:")
    print(f"  Rumus LaTeX ($$...$$): {formula_count}")
    print(f"  Tabel markdown: {table_count}")
    print(f"  Heading: {heading_count}")
    print(f"  Deskripsi gambar: {fig_desc_count}")


if __name__ == "__main__":
    main()
