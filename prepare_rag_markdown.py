#!/usr/bin/env python3
"""
prepare_rag_markdown.py
-----------------------
Tahap 2 Persiapan Markdown untuk RAG:
1. Membaca data/markdown/furniture_arrangement_ieq_2023_clean.md.
2. Menyisipkan tabel illuminance (Fig. 1 & Fig. 2) dalam format Markdown pipe table.
3. Mendeteksi dan memecah tabel yang tergabung (header berulang, reset penomoran baris 1..20, perubahan kolom).
4. Menambahkan caption yang hilang untuk Table 4 dan Table 5.
5. Mengonversi semua elemen HTML <table> menjadi Markdown pipe table standar.
6. Memvalidasi konsistensi jumlah kolom di setiap baris tabel.
7. Menyisipkan referensi gambar dan deskripsi teks hasil vision LLM:
     ![alt](path)
     > **Deskripsi gambar:** ...
8. Membersihkan artefak angka soliter (seperti angka '3' artefak).
9. Menyimpan hasil ke data/markdown/furniture_arrangement_ieq_2023_rag.md
   (dan memperbarui data/markdown/furniture_arrangement_ieq_2023_rebuilt.md).

Idempotent: aman dijalankan berulang kali.
"""

import json
import re
import sys
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent

SOURCE = ROOT / "data/markdown/furniture_arrangement_ieq_2023_clean.md"
OUTPUT_RAG = ROOT / "data/markdown/furniture_arrangement_ieq_2023_rag.md"
OUTPUT_REBUILT = ROOT / "data/markdown/furniture_arrangement_ieq_2023_rebuilt.md"
FIGURE_CACHE_PATH = ROOT / "data/processed/assets/figure_descriptions.json"

# ── Tabel Illuminance ─────────────────────────────────────────────────────────

ILLUMINANCE_TABLE_1 = """
| y\\x | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 80 | 50 | 130 | 130 | 130 | 110 | 100 | 90 | 90 |
| 2 | 80 | 50 | 130 | 130 | 130 | 110 | 100 | 90 | 90 |
| 3 | 440 | 350 | 350 | 300 | 300 | 300 | 100 | 90 | 90 |
| 4 | 540 | 350 | 350 | 300 | 300 | 200 | 200 | 150 | 90 |
| 5 | 800 | 350 | 300 | 300 | 300 | 200 | 200 | 150 | 125 |
| 6 | 700 | 350 | 370 | 300 | 300 | 200 | 200 | 150 | 110 |
| 7 | 300 | 350 | 370 | 330 | 200 | 190 | 190 | 180 | 200 |

*Satuan: lux (lx). Baris = koordinat y, Kolom = koordinat x. Sudut kiri atas = (x=1,y=1) pojok barat-laut.*
"""

ILLUMINANCE_TABLE_2 = """
| y\\x | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 400 | 580 | 550 | 550 | 250 | 200 | 200 | 0 | 0 |
| 2 | 350 | 550 | 530 | 500 | 330 | 330 | 340 | 0 | 0 |
| 3 | 250 | 350 | 350 | 300 | 300 | 300 | 300 | 90 | 90 |
| 4 | 250 | 350 | 350 | 300 | 300 | 300 | 450 | 580 | 700 |
| 5 | 250 | 300 | 300 | 300 | 300 | 330 | 430 | 550 | 680 |
| 6 | 200 | 300 | 300 | 300 | 300 | 330 | 430 | 530 | 650 |
| 7 | 190 | 250 | 250 | 330 | 200 | 190 | 400 | 500 | 630 |

*Satuan: lux (lx). Nilai 0 = area di luar bentuk ruangan tidak beraturan Office #2.*
"""


def to_markdown_pipe_table(header: list[str], rows: list[list[str]]) -> str:
    """Mengonversi baris tabel ke Markdown pipe table dengan validasi kolom."""
    max_cols = max(len(header), max((len(r) for r in rows), default=0))
    header_padded = header + [""] * (max_cols - len(header))
    rows_padded = [r + [""] * (max_cols - len(r)) for r in rows]

    # Validasi konsistensi kolom
    for r in rows_padded:
        if len(r) != max_cols:
            raise ValueError(f"Inconsistent column count: {len(r)} vs {max_cols}")

    lines = [
        "| " + " | ".join(header_padded) + " |",
        "| " + " | ".join(["---"] * max_cols) + " |",
    ]
    for r in rows_padded:
        lines.append("| " + " | ".join(r) + " |")

    return "\n".join(lines)


def split_and_convert_html_table(html_str: str, table_idx: int) -> list[tuple[str, str]]:
    """
    Mendeteksi dan memecah tabel tergabung, lalu mengonversi ke Markdown pipe table.
    Return list of (caption_or_label, markdown_table).
    """
    soup = BeautifulSoup(html_str, "html.parser")
    raw_rows = []
    for tr in soup.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if any(cells):
            raw_rows.append(cells)

    if not raw_rows:
        return []

    # Deteksi titik pemecahan (split points)
    splits = []
    prev_num = None

    for r_idx in range(1, len(raw_rows)):
        row = raw_rows[r_idx]
        # Lewati baris kosong / artefak baris '21' kosong
        if not any(row) or (len(row) >= 1 and row[0] == "21" and not any(row[1:])):
            continue

        first_cell = row[0]
        # Reset penomoran tes (misal kembali ke '1' setelah '20' atau '5')
        if first_cell == "1" and prev_num in ["20", "5"]:
            splits.append(r_idx)
        elif len(row) > 1 and row[0] == "" and row[1] == "1" and prev_num in ["5"]:
            splits.append(r_idx)

        num_str = row[0] if row[0] != "" else (row[1] if len(row) > 1 else "")
        if num_str.isdigit():
            prev_num = num_str

    header = raw_rows[0]

    # Kasus 1: Tabel tunggal normal tanpa penggabungan
    if not splits:
        # Penyesuaian nama tabel untuk Table 4 dan Table 5 bila diperlukan
        return [("", to_markdown_pipe_table(header, raw_rows[1:]))]

    # Kasus 2: Tabel tergabung yang perlu dipecah
    results = []
    start = 0

    for split_idx in splits:
        sub_data = [
            r for r in raw_rows[start + 1 : split_idx]
            if any(r) and not (r[0] == "21" and not any(r[1:]))
        ]
        results.append(("", to_markdown_pipe_table(header, sub_data)))
        start = split_idx

    # Bagian terakhir setelah split
    last_rows = [r for r in raw_rows[start:] if any(r)]
    if last_rows and last_rows[0][0] == "" and len(last_rows[0]) > 2 and last_rows[0][1] == "1":
        # Kasus Tabel 11: Baris bergeser ['', '1', '610.24', '', '616.69']
        # Header yang benar untuk perbandingan NSGA-II vs MORL
        new_header = ["#Test", "NSGA-II", "MORL"]
        new_data = []
        for r in last_rows:
            cleaned_r = [c for c in r if c != ""]
            if len(cleaned_r) >= 3:
                new_data.append(cleaned_r[:3])
        results.append(("", to_markdown_pipe_table(new_header, new_data)))
    else:
        results.append(("", to_markdown_pipe_table(header, last_rows)))

    return results


def process_all_tables(text: str) -> str:
    """Mendeteksi semua tabel HTML, memecah tabel tergabung, dan mengonversi ke Markdown."""
    # 1. Hapus tabel HTML bawaan yang berisi matriks illuminance kasar jika ada
    text = re.sub(
        r"<table>(?:<tr><td>\d+</td>)+.*?</table>\n?",
        "",
        text,
        flags=re.DOTALL,
    )

    # 2. Inject tabel illuminance 1 & 2 di Section 5 pada lokasi yang tepat
    fig1_pat = re.compile(
        r"(coordinates of each cell room are taken according to the reference system, as shown in Fig\. 1\.)",
        re.IGNORECASE,
    )
    if fig1_pat.search(text):
        text = fig1_pat.sub(
            lambda m: m.group(1)
            + "\n\n**Fig. 1** Office #1 and illuminance values on its surface\n"
            + ILLUMINANCE_TABLE_1.strip(),
            text,
            count=1,
        )
        print("  [TABLE] Tabel illuminance Office #1 disisipkan di Section 5.")

    fig2_pat = re.compile(
        r"(Shape and sizes are shown in Fig\. 2\.)",
        re.IGNORECASE,
    )
    if fig2_pat.search(text):
        text = fig2_pat.sub(
            lambda m: m.group(1)
            + "\n\n**Fig. 2** Office #2 and illuminance values on its surface\n"
            + ILLUMINANCE_TABLE_2.strip(),
            text,
            count=1,
        )
        print("  [TABLE] Tabel illuminance Office #2 disisipkan di Section 5.")

    # 3. Cari dan proses setiap <table> HTML
    table_matches = list(re.finditer(r"<table.*?</table>", text, re.DOTALL))
    print(f"  [TABLE] Ditemukan {len(table_matches)} elemen <table> HTML untuk diproses.")

    # Ganti dari akhir ke awal agar indeks posisi teks tidak bergeser
    for idx in reversed(range(len(table_matches))):
        m = table_matches[idx]
        html_str = m.group(0)
        split_tables = split_and_convert_html_table(html_str, idx)

        # Beri label/caption kontekstual untuk tabel yang dipecah
        replacement_parts = []
        if idx in (5, 6, 7):
            # Tabel 20 test Fig. 8-13 dihapus sepenuhnya sesuai keputusan user
            # Nilai grafik cukup direpresentasikan melalui deskripsi gambar vision
            replacement_parts = []
        elif idx == 10:  # Table 11 (Execution times RL + Mean IEQ_Tot NSGA-II)
            if len(split_tables) == 2:
                replacement_parts.append(f"**Table: Execution times (seconds) for RL algorithms**\n\n{split_tables[0][1]}")
                replacement_parts.append(f"**Table: Mean values of IEQ_Tot (NSGA-II vs MORL)**\n\n{split_tables[1][1]}")
            else:
                replacement_parts.extend([t[1] for t in split_tables])
        elif idx == 3:  # Table 4 (missing caption)
            replacement_parts.append(f"Table 4 Office #2—layout pattern #1 features\n\n{split_tables[0][1]}")
        elif idx == 4:  # Table 5 (missing caption)
            replacement_parts.append(f"Table 5 Office #2—layout pattern #2 features\n\n{split_tables[0][1]}")
        else:
            replacement_parts.extend([t[1] for t in split_tables])

        replacement_str = "\n\n".join(replacement_parts)
        text = text[: m.start()] + replacement_str + text[m.end() :]

    # 4. Hapus artefak angka soliter (seperti baris hanya berisi '3' setelah Fig. 16)
    text = re.sub(r"\n+3\n+(?=Fig\. 17)", "\n\n", text)

    return text


# ── Injeksi Figure dan Deskripsi Vision ────────────────────────────────────────

FIGURE_MAPPINGS = [
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 1\*{0,2}\s+Office #1 and illuminance values on its surface)", re.IGNORECASE),
        "key": "page_8_fig1",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 2\*{0,2}\s+Office #2 and illuminance values on its surface)", re.IGNORECASE),
        "key": "page_9_fig2",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(four possible orientations are considered \(see Fig\. 3\)\.)", re.IGNORECASE),
        "key": "page_10_fig3",
        "mode": "after_sentence",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 4\*{0,2}\s+Office #1[\u2014\-]layout pattern #1)", re.IGNORECASE),
        "key": "page_11_item_12",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 5\*{0,2}\s+Office #1[\u2014\-]layout pattern #2)", re.IGNORECASE),
        "key": "page_11_item_14",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 6\*{0,2}\s+Office #2[\u2014\-]layout pattern #1)", re.IGNORECASE),
        "key": "page_11_item_13",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 7\*{0,2}\s+Office #2[\u2014\-]layout pattern #2)", re.IGNORECASE),
        "key": "page_12_item_3",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 8\*{0,2}\s+Thermal comfort index office #1)", re.IGNORECASE),
        "key": "page_11_item_10",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 9\*{0,2}\s+Acoustics comfort index office #1)", re.IGNORECASE),
        "key": "page_12_item_12",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 10\*{0,2}\s+Visual comfort index office #1)", re.IGNORECASE),
        "key": "page_13_fig10",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 11\*{0,2}\s+Thermal comfort index office #2)", re.IGNORECASE),
        "key": "page_14_fig11",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 12\*{0,2}\s+Acoustics comfort index office #2)", re.IGNORECASE),
        "key": "page_15_fig12",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 13\*{0,2}\s+Visual comfort index office #2)", re.IGNORECASE),
        "key": "page_15_fig13",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 14\*{0,2}\s+Mean values of \*IEQ<sub>Tot</sub>\* related to the optimal layout configurations)", re.IGNORECASE),
        "key": "page_16_fig14",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 15\*{0,2}\s+Standard deviation of \*IEQ<sub>Tot</sub>\* related to the optimal layout configurations)", re.IGNORECASE),
        "key": "page_16_fig15",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 16\*{0,2}\s+Execution times)", re.IGNORECASE),
        "key": "page_16_fig16",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 17\*{0,2}\s+Mean values of \*IEQ<sub>Tot</sub>\* related to the optimal layout configurations)", re.IGNORECASE),
        "key": "page_17_fig17",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 18\*{0,2}\s+Standard deviation of \*IEQ<sub>Tot</sub>\* related to the optimal layout configurations)", re.IGNORECASE),
        "key": "page_18_fig18",
        "mode": "after_line",
    },
    {
        "trigger": re.compile(r"(\*{0,2}Fig\. 19\*{0,2}\s+Execution times)", re.IGNORECASE),
        "key": "page_19_fig19",
        "mode": "after_line",
    },
]


def build_figure_block(key: str, cache: dict) -> str:
    """Membangun blok Markdown deskripsi gambar sesuai format yang diminta."""
    entry = cache.get(key)
    if not entry or entry.get("skip"):
        return ""

    caption = entry.get("caption", "")
    description = entry.get("description", "")
    asset_path = entry.get("asset_path", "")

    if not description:
        return ""

    img_line = ""
    if asset_path:
        try:
            rel = Path(asset_path).relative_to(ROOT)
            img_line = f"![{caption}]({rel})"
        except ValueError:
            img_line = f"![{caption}]({asset_path})"

    block = ""
    if img_line:
        block += f"\n{img_line}\n"
    block += f"\n> **Deskripsi gambar:** {description}\n"
    return block


def inject_figures_and_descriptions(text: str, cache: dict) -> str:
    """Menyisipkan gambar dan deskripsi teks hasil vision ke Markdown."""
    for mapping in FIGURE_MAPPINGS:
        pattern = mapping["trigger"]
        key = mapping["key"]
        mode = mapping["mode"]

        desc_block = build_figure_block(key, cache)
        if not desc_block:
            continue

        def replacer(m, b=desc_block, md=mode):
            matched = m.group(1) if m.lastindex else m.group(0)
            if md == "after_sentence":
                return matched + b
            return matched + "\n" + b.strip()

        new_text = pattern.sub(replacer, text, count=1)
        if new_text != text:
            text = new_text
            print(f"  [FIGURE] Deskripsi disisipkan: {key}")

    return text


# ── Restrukturisasi Section 6 & Section 5.1 ──────────────────────────────────

def fix_section_6_placement(text: str) -> str:
    """
    Memindahkan heading '6 Algorithm comparison' ke posisi yang benar (setelah Fig. 7-13 dan tabel Section 5.1)
    dan menyatukan 3 pecahan paragraf pembukanya yang tersebar di antara Fig. 7-13.
    """
    frag1_target = (
        "## 6 Algorithm comparison\n\n"
        "To demonstrate the effectiveness of the proposed approach for a multi-objective layout optimization "
        "in terms of indoor environmental quality, we first compare the proposed method with three mainstream "
        "single-objective RL methods, including Deep Q-Learning (DQN), Actor-Critic (A2C) and Proximal Policy "
        "Optimization (PPO). Then, we compare the proposed method with the Non-Dominated Sorting Genetic "
        "Algorithm II (NSGA-II), one of the most popular multi-objective optimization algorithms. In particular, "
        "DQNs (Arulkumaran et al. 2017) are Q-learning methods where Q-tables are replaced with Neural Networks "
        "for approximating Q-values for each action-state pair. A2Cs (Gondman et al. 2012) belong to a hybrid "
        "class of RL approaches that combine value estimation and policy gradient methods. An actor-critic "
        "method generally consists of an actor\n\n"
    )

    frag2_target = (
        "\n\nthat changes the policy to maximize its value, as estimated by the critic. "
        "The critic uses an approximation architecture to learn a value function, which is then used to update the\n\n"
        "actor’s policy parameters in the direction of performance improvement. PPO (Schulman et al. 2017) "
        "is a family of policy optimization methods that use multiple epochs of"
    )

    frag3_target = (
        "stochastic gradient ascent to perform each policy update by also using the actor-critic method. "
        "Conversely, NSGA-II (Deb et al. 2002) is a space exploration engine based on genetic algorithms. "
        "It is a multi-objective algorithm based on non-dominated sorting, fast crowded distance estimation "
        "procedure and simple crowded comparison operator. An NSGA-II solves a multi-objective optimization "
        "problem by generating a population of candidate solutions that evolve toward a near-optimal solution "
        "through a number of generations. As a result, it is able to find a set of optimal solutions called "
        "non-dominated solutions, which provide a suitable compromise between all objectives without degrading them."
    )

    unified_p = (
        "## 6 Algorithm comparison\n\n"
        "To demonstrate the effectiveness of the proposed approach for a multi-objective layout optimization "
        "in terms of indoor environmental quality, we first compare the proposed method with three mainstream "
        "single-objective RL methods, including Deep Q-Learning (DQN), Actor-Critic (A2C) and Proximal Policy "
        "Optimization (PPO). Then, we compare the proposed method with the Non-Dominated Sorting Genetic "
        "Algorithm II (NSGA-II), one of the most popular multi-objective optimization algorithms. In particular, "
        "DQNs (Arulkumaran et al. 2017) are Q-learning methods where Q-tables are replaced with Neural Networks "
        "for approximating Q-values for each action-state pair. A2Cs (Gondman et al. 2012) belong to a hybrid "
        "class of RL approaches that combine value estimation and policy gradient methods. An actor-critic "
        "method generally consists of an actor that changes the policy to maximize its value, as estimated by "
        "the critic. The critic uses an approximation architecture to learn a value function, which is then used "
        "to update the actor’s policy parameters in the direction of performance improvement. PPO (Schulman et "
        "al. 2017) is a family of policy optimization methods that use multiple epochs of stochastic gradient "
        "ascent to perform each policy update by also using the actor-critic method. Conversely, NSGA-II (Deb et "
        "al. 2002) is a space exploration engine based on genetic algorithms. It is a multi-objective algorithm "
        "based on non-dominated sorting, fast crowded distance estimation procedure and simple crowded comparison "
        "operator. An NSGA-II solves a multi-objective optimization problem by generating a population of candidate "
        "solutions that evolve toward a near-optimal solution through a number of generations. As a result, it is "
        "able to find a set of optimal solutions called non-dominated solutions, which provide a suitable "
        "compromise between all objectives without degrading them."
    )

    if frag1_target in text:
        text = text.replace(frag1_target, "")
        print("  [SECTION 6] Menghapus heading premature dan fragmen 1 dari Section 5.1.")
    else:
        print("  [WARN] frag1_target tidak ditemukan.")

    if frag2_target in text:
        text = text.replace(frag2_target, "")
        print("  [SECTION 6] Menghapus fragmen 2 dari antara Fig. 8 dan Fig. 9.")
    else:
        print("  [WARN] frag2_target tidak ditemukan.")

    if frag3_target in text:
        text = text.replace(frag3_target, unified_p)
        print("  [SECTION 6] Menempatkan heading ## 6 Algorithm comparison dan menyatukan paragraf pembuka.")
    else:
        print("  [WARN] frag3_target tidak ditemukan.")

    return text


def fix_section_6_2_and_7_placement(text: str) -> str:
    """
    Memindahkan Fig. 19 (Execution times) beserta tabel data NSGA-II vs MORL
    dari Section 7 Conclusions ke akhir Section 6.2 Comparison with NSGA-II,
    serta menyatukan kembali paragraf pembuka Section 7 Conclusions yang sempat terpotong.
    """
    start_frag = "reinforcement learning. Mainly, since RL algorithms rely on a mathematical MDP framework"
    end_frag = "quality factor and other elements that influence visual comfort for spaces with different end-use."

    pos_start = text.find(start_frag)
    if pos_start == -1:
        print("  [WARN] start_frag Section 7 tidak ditemukan.")
        return text

    pos_end = text.find(end_frag)
    if pos_end == -1:
        print("  [WARN] end_frag Section 7 tidak ditemukan.")
        return text
    pos_end += len(end_frag)

    table_fig19 = (
        "<table><thead><tr><th>#Test</th><th>NSGA-II</th><th>MORL</th></tr></thead>"
        "<tbody><tr><th>1</th><td>4.40</td><td>4.00</td></tr>"
        "<tr><th>2</th><td>8.52</td><td>7.82</td></tr>"
        "<tr><th>3</th><td>12.61</td><td>11.58</td></tr>"
        "<tr><th>4</th><td>16.37</td><td>15.68</td></tr>"
        "<tr><th>5</th><td>20.52</td><td>19.39</td></tr></tbody></table>\n\n"
        "**Fig. 19** Execution times"
    )

    unified_conclusions = (
        "## 7 Conclusions\n\n"
        "The paper presents an approach for finding furniture arrangements patterns in multi-occupant offices "
        "that maximize user satisfaction in terms of indoor environmental quality and functional requirements. "
        "The approach is based on multi-objective reinforcement learning that allows an agent to learn optimal "
        "solutions that reach a trade-off between office occupants. There are several advantages to applying "
        "reinforcement learning. Mainly, since RL algorithms rely on a mathematical MDP framework, they can "
        "theoretically guarantee convergence toward an optimal solution. Moreover, an RL agent learns optimal "
        "policies directly from interactions with the unknown environment without model definition. It may execute "
        "an intensified search by exploitation and a diversified search by exploration, making it an efficient method "
        "for various NP-hard problems. An RL agent gradually learns the best (or near-best) strategy based on trial "
        "and error through interactions with the environment to improve overall performance. Moreover, the analysis "
        "of the results gives evidence that the proposed approach provides advantages not only for finding the best "
        "arrangement for multi-occupant offices but also for highlighting possible corrections to improve indoor "
        "environmental quality (e.g., reducing noise from devices or improving lighting design). The current prototype "
        "is developed to find optimal room configurations with office end-use. However, it can be extended as a generalized "
        "tool for dealing with different functional environments and furniture. Finally, we are working on extending "
        "the proposed work to address a more complex optimization problem which incorporates the air quality factor and "
        "other elements that influence visual comfort for spaces with different end-use."
    )

    replacement = f"{table_fig19}\n\n{unified_conclusions}"
    text = text[:pos_start] + replacement + text[pos_end:]
    print("  [SECTION 6.2 & 7] Fig. 19 & tabel dipindahkan ke Section 6.2, Section 7 disatukan.")
    return text


def main():
    print("=" * 60)
    print("PREPARE RAG MARKDOWN PIPELINE")
    print("=" * 60)

    if not SOURCE.exists():
        print(f"ERROR: File sumber tidak ditemukan: {SOURCE}")
        sys.exit(1)

    print(f"Membaca sumber: {SOURCE}")
    text = SOURCE.read_text(encoding="utf-8")

    # 0. Restrukturisasi Section 6, 6.2 & Section 7
    print("\n[0/3] Menyelaraskan heading Section 6 dan Section 6.2 / 7...")
    text = fix_section_6_placement(text)
    text = fix_section_6_2_and_7_placement(text)

    # 1. Muat cache deskripsi gambar
    figure_cache = {}
    if FIGURE_CACHE_PATH.exists():
        figure_cache = json.loads(FIGURE_CACHE_PATH.read_text(encoding="utf-8"))
        print(f"Cache deskripsi gambar dimuat: {len(figure_cache)} entri")
    else:
        print("WARN: Cache deskripsi gambar tidak ditemukan.")

    # 2. Proses semua tabel (deteksi split, konversi pipe table, konsistensi kolom)
    print("\n[1/3] Memproses tabel & memecah tabel tergabung...")
    text = process_all_tables(text)

    # 3. Sisipkan figure dan deskripsi vision
    print("\n[2/3] Menyisipkan gambar dan deskripsi teks...")
    text = inject_figures_and_descriptions(text, figure_cache)

    # 4. Simpan output ke RAG markdown dan rebuilt markdown
    text = text.strip() + "\n"
    OUTPUT_RAG.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_RAG.write_text(text, encoding="utf-8")

    OUTPUT_REBUILT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_REBUILT.write_text(text, encoding="utf-8")

    pipe_table_count = len(re.findall(r"^\| ---", text, re.MULTILINE))
    formula_count = len(re.findall(r"\$\$", text)) // 2
    desc_count = text.count("> **Deskripsi gambar:**")

    print(f"\nPersiapan RAG Markdown selesai.")
    print(f"  Ukuran output           : {OUTPUT_RAG.stat().st_size / 1024:.1f} KB")
    print(f"  Tabel Markdown pipe     : {pipe_table_count}")
    print(f"  Rumus LaTeX ($$...$$)   : {formula_count}")
    print(f"  Deskripsi gambar vision : {desc_count}")
    print(f"  Output RAG              : {OUTPUT_RAG}")
    print(f"  Output Rebuilt          : {OUTPUT_REBUILT}")


if __name__ == "__main__":
    main()
