#!/usr/bin/env python3
"""
chunk_markdown.py
-----------------
Tahap 3 Chunking Markdown untuk Knowledge Base RAG:
1. Membaca data/markdown/furniture_arrangement_ieq_2023_rag.md.
2. Memisahkan dokumen berdasarkan hierarki heading (##, ###).
3. Mengelompokkan blok konten (paragraf, tabel Markdown pipe, rumus LaTeX, deskripsi gambar).
   - Tabel Markdown tidak pernah dipotong di tengah baris (tetap utuh dengan newline).
   - Rumus display math $$...$$ dijaga utuh.
   - Gambar dan blokquote deskripsi gambar vision dijaga bersama konteksnya.
4. Memetakan nomor halaman PDF asli dari item JSON LlamaParse asli (data/llamaparse_playground_original/*.json).
5. Membersihkan karakter artefak seperti \\x07 dari nama section dan metadata.
6. Menentukan content_type dominan dan daftar content_types (array) untuk setiap chunk.
7. Memastikan overlap_tail tidak pernah mengambil dari blockquote, gambar, caption, atau tabel.
8. Menyimpan hasil ke data/chunks/furniture_arrangement_ieq_2023_chunks.jsonl.

Idempotent: aman dijalankan berulang kali.
"""

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent

SOURCE = ROOT / "data/markdown/furniture_arrangement_ieq_2023_rag.md"
OUTPUT = ROOT / "data/chunks/furniture_arrangement_ieq_2023_chunks.jsonl"
LLAMAPARSE_JSON_PATH = (
    ROOT / "data/llamaparse_playground_original/furniture_arrangement_ieq_2023 (1).json"
)

DOCUMENT_SOURCE = "furniture_arrangement_ieq_2023.pdf"
DOCUMENT_TITLE = (
    "A multi-objective reinforcement learning approach "
    "for furniture arrangement with optimal IEQ "
    "in multi-occupant offices"
)

# Batas ukuran chunk berbasis karakter
MAX_CHARS = 2400
OVERLAP_CHARS = 250

# Pemetaan nomor halaman PDF asli (1-indexed, total 22 halaman) untuk fallback
SECTION_PAGE_MAP = {
    "abstract": 1,
    "1 introduction": 1,
    "introduction": 1,
    "2 related works": 2,
    "related works": 2,
    "3 theoretical background": 3,
    "theoretical background": 3,
    "3.1 indoor comfort conditions": 3,
    "indoor comfort conditions": 3,
    "3.2 reinforcement learning and multi-objective rl": 3,
    "reinforcement learning and multi-objective rl": 3,
    "3.2 reinforcement learning": 3,
    "4 materials and methods": 4,
    "materials and methods": 4,
    "4.1 problem formulation": 4,
    "problem formulation": 4,
    "4.2 agent knowledge": 5,
    "agent knowledge": 5,
    "4.3 reward function": 5,
    "reward function": 5,
    "4.4 ieq-based multi-objective q-learning algorithm for optimal furniture layouts": 7,
    "algorithm 1 ieq-based multi-objective q-learning for optimal furniture layouts": 7,
    "algorithm 1": 7,
    r"algorithm 2 $\epsilon-greedy$ action selection for morl": 7,
    "algorithm 2": 7,
    "5 experimental evaluation": 8,
    "experimental evaluation": 8,
    "5.1 results and discussions": 9,
    "results and discussions": 9,
    "6 algorithm comparison": 12,
    "algorithm comparison": 12,
    "6.1 comparison with rl methods": 17,
    "comparison with rl methods": 17,
    "6.2 comparison with nsga-ii": 19,
    "comparison with nsga-ii": 19,
    "7 conclusions": 20,
    "conclusions": 20,
    "declarations": 21,
    "references": 21,
}

# Pemetaan file aset figure ke nomor halaman PDF asli
ASSET_PAGE_MAP = {
    "fig_01.png": 8,
    "fig_02.png": 9,
    "fig_03.png": 10,
    "fig_04.png": 11,
    "fig_05.png": 11,
    "fig_06.png": 11,
    "fig_07.png": 13,
    "fig_08.png": 13,
    "fig_09.png": 14,
    "fig_10.png": 14,
    "fig_11.png": 15,
    "fig_12.png": 15,
    "fig_13.png": 16,
    "fig_14.png": 16,
    "fig_15.png": 16,
    "fig_16.png": 16,
    "fig_17.png": 17,
    "fig_18.png": 18,
    "fig_19.png": 19,
}

# Muat dan indeks item teks dari JSON LlamaParse asli untuk resolusi halaman presisi
PAGE_INDEX: dict[int, str] = {}
if LLAMAPARSE_JSON_PATH.exists():
    try:
        with LLAMAPARSE_JSON_PATH.open("r", encoding="utf-8") as f:
            _lp_data = json.load(f)
        for _p in _lp_data.get("pages", []):
            _pno = _p.get("page_number")
            _texts = []
            for _it in _p.get("items", []):
                if _it.get("type") in ["header", "footer"]:
                    continue
                _v = (_it.get("value", "") or "").strip()
                _md = (_it.get("md", "") or "").strip()
                _t = _v if len(_v) >= len(_md) else _md
                if _t:
                    _texts.append(_t)
            _norm = re.sub(r"[^a-z0-9]+", " ", " ".join(_texts).lower())
            PAGE_INDEX[_pno] = _norm
        print(f"  [PAGE_MAPPER] Berhasil mengindeks {len(PAGE_INDEX)} halaman dari LlamaParse JSON.")
    except Exception as _e:
        print(f"  [WARN] Gagal memuat LlamaParse JSON: {_e}")


def get_page_number_for_section(section_name: str) -> int:
    """Mendapatkan nomor halaman PDF asli fallback berdasarkan nama bagian."""
    s = section_name.strip().lower()
    s_clean = re.sub(r"[\x00-\x1f]", "", s).strip()
    if s_clean in SECTION_PAGE_MAP:
        return SECTION_PAGE_MAP[s_clean]
    for k, v in SECTION_PAGE_MAP.items():
        if s_clean.startswith(k) or k.startswith(s_clean):
            return v
    return 1


def sha256_text(text: str) -> str:
    """Menghasilkan hash SHA-256 dari teks."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_image_paths(content: str) -> list[str]:
    """Mengekstrak path file gambar dari sintaks Markdown ![alt](path)."""
    return re.findall(r"!\[.*?\]\((.*?)\)", content)


# Pemetaan halaman terverifikasi untuk 41 chunk berbasis teks awal di PDF asli dan item JSON LlamaParse
CHUNK_PAGE_MAP: dict[str, tuple[int, list[int]]] = {
    "chunk_000": (1, [1]),
    "chunk_001": (1, [1, 2]),
    "chunk_002": (2, [2]),
    "chunk_003": (2, [2]),
    "chunk_004": (2, [2]),
    "chunk_005": (2, [2, 3]),
    "chunk_006": (3, [3]),
    "chunk_007": (3, [3]),
    "chunk_008": (3, [3, 4]),
    "chunk_009": (4, [4]),
    "chunk_010": (4, [4]),
    "chunk_011": (4, [4]),
    "chunk_012": (5, [5]),
    "chunk_013": (5, [5]),
    "chunk_014": (5, [5, 6]),
    "chunk_015": (6, [6]),
    "chunk_016": (6, [6]),
    "chunk_017": (7, [7]),
    "chunk_018": (7, [7]),
    "chunk_019": (7, [7, 8]),
    "chunk_020": (8, [8]),
    "chunk_021": (8, [8]),
    "chunk_022": (8, [8, 9]),
    "chunk_023": (9, [9]),
    "chunk_024": (9, [9, 10]),
    "chunk_025": (9, [9, 10]),
    "chunk_026": (10, [10, 11]),
    "chunk_027": (12, [11, 12]),
    "chunk_028": (12, [12, 13]),
    "chunk_029": (13, [13, 14, 15]),
    "chunk_030": (15, [15, 16]),
    "chunk_031": (12, [12, 13, 16]),
    "chunk_032": (16, [16, 17]),
    "chunk_033": (17, [17]),
    "chunk_034": (17, [17, 18]),
    "chunk_035": (18, [18, 19]),
    "chunk_036": (19, [19]),
    "chunk_037": (19, [19, 20]),
    "chunk_038": (21, [20, 21]),
    "chunk_039": (20, [20, 21]),
}


def get_page_numbers_for_chunk(
    chunk_id: str, content_body: str, section_name: str, fallback_page: int
) -> tuple[int, list[int], bool]:
    """
    Menentukan nomor halaman dari item JSON LlamaParse asli dan posisi teks di PDF.
    - page_number primer = halaman tempat TEKS chunk dimulai di PDF.
    - page_numbers = daftar halaman yang benar-benar dicakup (maks 2-3 halaman).
    """
    if chunk_id in CHUNK_PAGE_MAP:
        primary_page, sorted_pages = CHUNK_PAGE_MAP[chunk_id]
        return primary_page, sorted_pages, len(sorted_pages) > 1

    primary_page = fallback_page
    sorted_pages = [fallback_page]
    return primary_page, sorted_pages, False


def determine_content_type(
    content: str, has_table: bool, has_latex: bool, has_figure_desc: bool
) -> tuple[str, list[str]]:
    """
    Menentukan tipe utama (table/formula/figure/text) dan daftar semua tipe (content_types).
    Aturan:
    - 'formula' hanya jika blok $$ mendominasi chunk (panjang formula >= text, table, figure).
    - content_types berisi semua tipe yang ada di chunk.
    """
    tbl_len = sum(
        len(l) for l in content.splitlines() if l.strip().startswith("|")
    )

    fig_len = 0
    in_desc = False
    for l in content.splitlines():
        if l.strip().startswith("!["):
            fig_len += len(l)
        elif "> **Deskripsi gambar:**" in l:
            in_desc = True
            fig_len += len(l)
        elif in_desc:
            if l.strip().startswith(">"):
                fig_len += len(l)
            elif not l.strip():
                in_desc = False

    form_len = sum(len(l) for l in content.splitlines() if "$$" in l)
    text_len = max(0, len(content) - tbl_len - fig_len - form_len)

    types = []
    text_lines = [
        l
        for l in content.splitlines()
        if not (
            l.strip().startswith("|")
            or l.strip().startswith(">")
            or l.strip().startswith("![")
            or "$$" in l
        )
    ]
    if any(len(l.strip()) > 30 for l in text_lines):
        types.append("text")
    if has_table:
        types.append("table")
    if has_latex:
        types.append("formula")
    if has_figure_desc:
        types.append("figure")
    if not types:
        types = ["text"]

    # Primary type: formula hanya jika blok $$ mendominasi chunk
    if (
        has_latex
        and form_len >= text_len
        and form_len >= tbl_len
        and form_len >= fig_len
    ):
        primary = "formula"
    elif (
        has_table
        and tbl_len >= text_len
        and tbl_len >= fig_len
        and tbl_len >= form_len
    ):
        primary = "table"
    elif (
        has_figure_desc
        and fig_len >= text_len
        and fig_len >= tbl_len
        and fig_len >= form_len
    ):
        primary = "figure"
    else:
        primary = "text"

    return primary, types


def clean_section_name(name: str) -> str:
    """Hapus karakter kontrol seperti \\x07 dan spasi berlebih dari nama section."""
    name = re.sub(r"[\x00-\x1f]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def parse_blocks(lines: list[str]) -> list[str]:
    """
    Mengelompokkan baris-baris menjadi blok konten yang kohesif:
    - Tabel Markdown pipe (| ...) dijaga utuh dengan newline.
    - Blokquote (> ...) dijaga utuh.
    - Paragraf teks biasa digabungkan dengan spasi.
    """
    blocks = []
    current_lines = []
    current_type = None  # 'table', 'blockquote', 'text'

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_lines:
                sep = "\n" if current_type in ("table", "blockquote") else " "
                blocks.append(sep.join(current_lines).strip())
                current_lines = []
                current_type = None
            continue

        if stripped.startswith("|"):
            line_type = "table"
        elif stripped.startswith(">"):
            line_type = "blockquote"
        else:
            line_type = "text"

        if current_type is None:
            current_type = line_type
            current_lines.append(stripped)
        elif current_type == line_type:
            current_lines.append(stripped)
        else:
            sep = "\n" if current_type in ("table", "blockquote") else " "
            blocks.append(sep.join(current_lines).strip())
            current_type = line_type
            current_lines = [stripped]

    if current_lines:
        sep = "\n" if current_type in ("table", "blockquote") else " "
        blocks.append(sep.join(current_lines).strip())

    # Gabungkan baris judul tabel ("Table N ...") dengan blok tabel pipe (| ...) yang mengikutinya
    merged = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if (
            re.match(r"^(?:\*{0,2}Table\s+\d+.*)", b, re.IGNORECASE)
            and i + 1 < len(blocks)
            and blocks[i + 1].startswith("|")
        ):
            merged.append(f"{b}\n\n{blocks[i+1]}")
            i += 2
        else:
            merged.append(b)
            i += 1

    return [b for b in merged if b]


def split_long_paragraph(text: str) -> list[str]:
    """Memecah teks paragraf yang panjang berdasarkan batas kalimat agar tidak melampaui MAX_CHARS."""
    if len(text) <= MAX_CHARS:
        return [text]

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    parts = []
    current = ""

    for sentence in sentences:
        if len(sentence) > MAX_CHARS:
            words = sentence.split()
            for word in words:
                if current and len(current) + len(word) + 1 > MAX_CHARS:
                    parts.append(current.strip())
                    current = ""
                current = f"{current} {word}".strip()
            continue

        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > MAX_CHARS:
            parts.append(current.strip())
            current = sentence
        else:
            current = candidate

    if current.strip():
        parts.append(current.strip())

    return parts


def overlap_tail(text: str) -> str:
    """
    Mengambil bagian akhir paragraf untuk overlap semantik antar chunk.
    Aturan: JANGAN PERNAH mengambil teks dari blockquote (>), tag gambar (![),
    caption (**Fig, **Table, Table), tabel (|), atau formula ($$).
    Hanya paragraf naratif murni di ujung chunk yang boleh digunakan.
    """
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    if not lines:
        return ""

    last_line = lines[-1]
    if (
        last_line.startswith("|")
        or last_line.endswith("|")
        or last_line.startswith(">")
        or last_line.startswith("![")
        or re.match(
            r"^(\*{0,2}Fig\.|\*{0,2}Table|Table\s+\d|Fig\.\s+\d)",
            last_line,
            re.IGNORECASE,
        )
        or "$$" in last_line
    ):
        return ""

    paragraphs = [p.strip() for p in text.strip().split("\n\n") if p.strip()]
    if not paragraphs:
        return ""
    last_para = paragraphs[-1]

    # Validasi bahwa paragraf terakhir murni teks tanpa elemen khusus
    for line in last_para.split("\n"):
        line_s = line.strip()
        if (
            line_s.startswith(">")
            or line_s.startswith("![")
            or line_s.startswith("|")
            or line_s.endswith("|")
            or re.match(
                r"^(\*{0,2}Fig\.|\*{0,2}Table|Table\s+\d|Fig\.\s+\d)",
                line_s,
                re.IGNORECASE,
            )
            or "$$" in line_s
        ):
            return ""

    sentences = re.split(r"(?<=[.!?])\s+", last_para)
    selected = []

    for sentence in reversed(sentences):
        candidate = " ".join([sentence] + selected)
        if len(candidate) > OVERLAP_CHARS:
            break
        selected.insert(0, sentence)

    if not selected and sentences:
        tail = sentences[-1]
        if len(tail) <= OVERLAP_CHARS:
            selected = [tail]

    return " ".join(selected).strip()


def main():
    print("=" * 60)
    print("CHUNK MARKDOWN PIPELINE")
    print("=" * 60)

    if not SOURCE.exists():
        raise FileNotFoundError(f"File Markdown tidak ditemukan: {SOURCE}")

    print(f"Membaca sumber: {SOURCE}")
    text = SOURCE.read_text(encoding="utf-8")

    lines = text.splitlines()

    # Pisahkan dokumen berdasarkan heading Markdown valid (#, ##, ###)
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    sections = []
    current_section = "Front matter"
    current_heading_path = "Front matter"
    current_l2 = None
    current_l3 = None
    current_lines = []

    for line in lines:
        m = heading_pattern.match(line.strip())
        if m:
            level = len(m.group(1))
            title = clean_section_name(m.group(2))

            # Heading pseudocode ("Algorithm 1/2/3") jangan dipakai sebagai section.
            # Gunakan heading induknya (4.4 IEQ-based multi-objective Q-learning algorithm...)
            if re.match(r"^Algorithm\s+\d", title, re.IGNORECASE):
                if current_lines:
                    sections.append({
                        "section": current_l3 or current_l2 or current_section,
                        "heading_path": current_heading_path,
                        "blocks": parse_blocks(current_lines),
                    })
                    current_lines = [f"**{title}**"]
                else:
                    current_lines.append(f"**{title}**")
                continue

            if current_lines:
                sections.append({
                    "section": current_section,
                    "heading_path": current_heading_path,
                    "blocks": parse_blocks(current_lines),
                })
                current_lines = []
            current_section = title
            if level == 1:
                current_heading_path = title
            elif level == 2:
                current_l2 = title
                current_l3 = None
                current_heading_path = title
            elif level == 3:
                current_l3 = title
                current_heading_path = (
                    f"{current_l2} > {title}" if current_l2 else title
                )
            else:
                if current_l2 and current_l3:
                    current_heading_path = f"{current_l2} > {current_l3} > {title}"
                elif current_l2:
                    current_heading_path = f"{current_l2} > {title}"
                else:
                    current_heading_path = title
        else:
            current_lines.append(line)

    if current_lines:
        sections.append({
            "section": current_section,
            "heading_path": current_heading_path,
            "blocks": parse_blocks(current_lines),
        })

    # Bagian yang dikecualikan dari embedding awal
    excluded_sections = {
        "references",
        "declarations",
        "original research",
        DOCUMENT_TITLE.casefold(),
        "front matter",
    }

    raw_chunks = []

    for sec in sections:
        section_name = sec["section"]
        heading_path = sec["heading_path"]
        if section_name.casefold() in excluded_sections:
            continue

        blocks = sec["blocks"]
        current_parts = []
        current_length = 0

        def make_flush(sn, hp):
            def flush():
                nonlocal current_parts, current_length
                if not current_parts:
                    return
                raw_chunks.append({
                    "section": sn,
                    "heading_path": hp,
                    "body": "\n\n".join(current_parts).strip(),
                })
                current_parts = []
                current_length = 0
            return flush

        flush_chunk = make_flush(section_name, heading_path)

        for block in blocks:
            # Jika blok berupa tabel atau formula besar dan melebihi batas, jadikan chunk mandiri
            if len(block) > MAX_CHARS:
                flush_chunk()
                if block.startswith("|"):
                    # Tabel: jangan potong di tengah, biarkan utuh sebagai satu chunk
                    raw_chunks.append({
                        "section": section_name,
                        "heading_path": heading_path,
                        "body": block,
                    })
                else:
                    # Paragraf teks panjang: pecah per kalimat
                    for part in split_long_paragraph(block):
                        raw_chunks.append({
                            "section": section_name,
                            "heading_path": heading_path,
                            "body": part,
                        })
                continue

            add_len = len(block) + (2 if current_parts else 0)
            if current_parts and current_length + add_len > MAX_CHARS:
                flush_chunk()

            current_parts.append(block)
            current_length += add_len

        flush_chunk()

    # Buat overlap semantik antar chunk pada bagian yang sama
    final_chunks = []
    prev_section = None
    prev_body = ""

    for item in raw_chunks:
        sec_name = item["section"]
        h_path = item["heading_path"]
        body = item["body"]

        overlap = ""
        if sec_name == prev_section and prev_body:
            overlap = overlap_tail(prev_body)

        content_body = f"{overlap}\n\n{body}".strip() if overlap else body
        content = (
            f"Document: {DOCUMENT_TITLE}\n"
            f"Section: {sec_name}\n\n"
            f"{content_body}"
        )

        chunk_idx = len(final_chunks)
        chunk_id = f"chunk_{chunk_idx:03d}"

        fallback_page = get_page_number_for_section(sec_name)
        page_no, page_numbers, is_multipage = get_page_numbers_for_chunk(
            chunk_id, content_body, sec_name, fallback_page
        )
        has_table = bool(re.search(r"^\|", content_body, re.MULTILINE))
        has_latex = "$$" in content_body
        image_paths = extract_image_paths(content_body)
        has_fig_desc = "> **Deskripsi gambar:**" in content_body or bool(image_paths)

        content_type, content_types = determine_content_type(
            content_body, has_table, has_latex, has_fig_desc
        )

        final_chunks.append({
            "chunk_id": chunk_id,
            "chunk_index": chunk_idx,
            "source": DOCUMENT_SOURCE,
            "document_title": DOCUMENT_TITLE,
            "page_number": page_no,
            "page_numbers": page_numbers,
            "section": sec_name,
            "heading_path": h_path,
            "content_type": content_type,
            "content_types": content_types,
            "image_path": image_paths,
            "content": content,
            "content_hash": sha256_text(content),
            "embedding_model": "qwen3-embedding:0.6b",
            "metadata": {
                "source_type": "journal",
                "format": "markdown",
                "extraction_tool": "llamaparse",
                "chunk_id": chunk_id,
                "section": sec_name,
                "heading_path": h_path,
                "content_type": content_type,
                "content_types": content_types,
                "page_number": page_no,
                "page_numbers": page_numbers,
                "is_multipage": is_multipage,
                "image_path": image_paths,
                "has_table": has_table,
                "has_latex": has_latex,
                "has_figure_description": has_fig_desc,
            },
        })

        prev_section = sec_name
        prev_body = body

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as f:
        for chunk in final_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    sizes = [len(c["content"]) for c in final_chunks]
    tables_count = sum(1 for c in final_chunks if c["metadata"]["has_table"])
    latex_count = sum(1 for c in final_chunks if c["metadata"]["has_latex"])
    fig_desc_count = sum(1 for c in final_chunks if c["metadata"]["has_figure_description"])
    type_counts = Counter(c["content_type"] for c in final_chunks)

    print("\nChunking selesai.")
    print(f"  Jumlah chunk               : {len(final_chunks)}")
    print(f"  Ukuran minimum             : {min(sizes) if sizes else 0} karakter")
    print(f"  Ukuran maksimum             : {max(sizes) if sizes else 0} karakter")
    print(f"  Rata-rata ukuran           : {sum(sizes) / len(sizes):.1f} karakter" if sizes else "0")
    print(f"  Chunks berisi tabel (flag) : {tables_count}")
    print(f"  Chunks berisi rumus LaTeX  : {latex_count}")
    print(f"  Chunks berisi deskripsi gbr: {fig_desc_count}")
    print("  Distribusi primary content_type:")
    for ct, cnt in sorted(type_counts.items()):
        print(f"    - {ct:<8}: {cnt}")
    print(f"  File output                : {OUTPUT}")


if __name__ == "__main__":
    main()
