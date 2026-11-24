#!/usr/bin/env python3
"""
generate_manual_fix_list.py
---------------------------
Hasilkan docs/manual_fix_list.md berisi daftar item yang perlu
diperbaiki manual: formula error, gambar tanpa deskripsi, dll.

Idempotent: aman dijalankan ulang.

Usage:
    python scripts/generate_manual_fix_list.py
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
REBUILT_MD = ROOT / "data/markdown/furniture_arrangement_ieq_2023_rebuilt.md"
LATEX_REPORT = ROOT / "docs/latex_validation_report.json"
FIGURE_CACHE = ROOT / "data/processed/assets/figure_descriptions.json"
OUTPUT = ROOT / "docs/manual_fix_list.md"
VALIDATION_DIR = ROOT / "data/validation"

# Mapping halaman PDF ke screenshot yang ada
def find_screenshots_for_page(page_no: int) -> list[str]:
    found = []
    for pattern in [
        f"original_page_{page_no}.png",
        f"original_page-{page_no:02d}.png",
        f"original_page_{page_no:02d}.png",
    ]:
        p = VALIDATION_DIR / pattern
        if p.exists():
            found.append(str(p.relative_to(ROOT)))
    return found


# Semua halaman yang memiliki formula (berdasarkan audit)
FORMULA_PAGES = {
    # (formula_key, page_pdf, eq_number, description)
    "bellman_equation": (3, 1, "Eq. (1) – Bellman Q-learning equation"),
    "q_vector": (3, 2, "Eq. (2) – Q̂-vector definition"),
    "weighted_sum_sq": (3, 3, "Eq. (3) – Scalarized Q-value SQ(s,a)"),
    "q_update_multi": (3, 4, "Eq. (4) – Multi-objective Q-update rule"),
    "momdp_tuple": (4, 5, "Eq. (5) – MOMDP tuple definition"),
    "reward_vector": (4, 6, "Eq. (6) – Reward vector R(s'|s,a)"),
    "sound_pressure": (5, 7, "Eq. (7) – Sound pressure level L_Receiver"),
    "room_constant": (5, 8, "Eq. (8) – Room constant Ac_R"),
    "mean_absorption": (5, 9, "Eq. (9) – Mean absorption coefficient"),
    "total_sound": (5, 10, "Eq. (10) – Total receiver sound level"),
    "mean_radiant_temp": (5, 11, "Eq. (11) – Mean radiant temperature T_mr"),
    "reward_function": (6, 12, "Eq. (12) – Reward function R"),
    "dist_users": (6, 13, "Eq. (13) – R_dist-users definition"),
    "distance_dij": (6, 14, "Eq. (14) – Distance D_ij"),
    "reward_user": (6, 15, "Eq. (15) – R_user_i"),
    "reward_ieq": (6, 16, "Eq. (16) – R_IEQ weighted sum"),
    "tc_index": (6, 17, "Eq. (17) – TC_index thermal comfort"),
    "pd_tc": (6, 18, "Eq. (18) – PD_TC predicted percentage dissatisfied"),
    "ac_index": (6, 19, "Eq. (19) – AC_index acoustic comfort"),
    "pd_acc": (6, 20, "Eq. (20) – PD_Acc acoustic dissatisfied"),
    "vc_index": (7, 21, "Eq. (21) – VC_index visual comfort"),
    "pd_l": (7, 22, "Eq. (22) – PD_L daylight dissatisfied"),
    "normalization": (7, 23, "Eq. (23) – Normalization formula"),
    "ieq_tot": (16, 24, "Eq. (24) – IEQ_Tot evaluation criterion"),
}


def load_json_safe(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def check_formula_in_rebuilt_md(text: str, eq_number: int) -> bool:
    """Cek apakah formula Eq. N ada dalam text sebagai $$ ... $$ (bisa format (N) di luar atau \tag{N} di dalam)."""
    # Format 1: \tag{N} di dalam $$
    pat1 = re.compile(rf"\$\$[^$]*\\tag\{{{eq_number}\}}[^$]*\$\$", re.DOTALL)
    if pat1.search(text):
        return True
    # Format 2: (N) di luar $$
    pat2 = re.compile(rf"\$\$[^$]+\$\$\s*\({eq_number}\)", re.DOTALL)
    if pat2.search(text):
        return True
    # Format 3: Eq. (N) di paragraf berikutnya
    pat3 = re.compile(rf"Eqs?\.\s*\({eq_number}\)", re.IGNORECASE)
    return bool(pat3.search(text))


def check_formula_placeholder_in_rebuilt(text: str) -> list[int]:
    """Cari sisa placeholder rumus yang belum diperbaiki."""
    placeholders = []
    for m in re.finditer(r"\[Rumus tidak berhasil[^\]]*\]", text):
        line_no = text[:m.start()].count("\n") + 1
        placeholders.append(line_no)
    return placeholders


def check_formula_errors_in_rebuilt(text: str) -> list[dict]:
    """Cari marker FORMULA_ERROR dalam teks."""
    errors = []
    for m in re.finditer(r"<!-- FORMULA_ERROR: ([^>]+) -->", text):
        line_no = text[:m.start()].count("\n") + 1
        errors.append({
            "line": line_no,
            "description": m.group(1),
        })
    return errors


def main():
    print("=" * 60)
    print("GENERATE MANUAL FIX LIST")
    print("=" * 60)

    items = []

    # ── 1. Cek formula dalam rebuilt markdown ──────────────────────────────
    rebuilt_text = ""
    if REBUILT_MD.exists():
        rebuilt_text = REBUILT_MD.read_text(encoding="utf-8")

    # Sisa placeholder
    placeholders = check_formula_placeholder_in_rebuilt(rebuilt_text)
    for line_no in placeholders:
        # Ambil konteks
        lines = rebuilt_text.splitlines()
        context = lines[line_no-1] if line_no <= len(lines) else ""
        items.append({
            "category": "formula_placeholder",
            "severity": "HIGH",
            "description": "Placeholder rumus masih ada (belum diperbaiki dari Docling)",
            "line_in_rebuilt_md": line_no,
            "context": context[:100],
            "reference_screenshots": [],
            "action": "Ganti dengan rumus LaTeX yang benar dari PDF asli",
        })

    # FORMULA_ERROR markers
    formula_errors = check_formula_errors_in_rebuilt(rebuilt_text)
    for err in formula_errors:
        items.append({
            "category": "formula_error",
            "severity": "HIGH",
            "description": f"Formula error: {err['description']}",
            "line_in_rebuilt_md": err["line"],
            "action": "Perbaiki sintaks LaTeX dan hapus marker <!-- FORMULA_ERROR -->",
        })

    # ── 2. Cek semua formula dari paper sudah ada ──────────────────────────
    if rebuilt_text:
        for key, (page_no, eq_num, description) in FORMULA_PAGES.items():
            has_formula = check_formula_in_rebuilt_md(rebuilt_text, eq_num)
            if not has_formula:
                screenshots = find_screenshots_for_page(page_no)
                items.append({
                    "category": "formula_missing",
                    "severity": "HIGH",
                    "description": f"Formula tidak ditemukan: {description}",
                    "pdf_page": page_no,
                    "equation_number": eq_num,
                    "reference_screenshots": screenshots,
                    "action": (
                        f"Tambahkan formula $$...$$  untuk Eq. ({eq_num}) "
                        f"di sekitar konten Section yang relevan. "
                        f"Lihat screenshot halaman {page_no}."
                    ),
                })

    # ── 3. Cek gambar yang belum punya deskripsi ───────────────────────────
    figure_cache = load_json_safe(FIGURE_CACHE)
    figures_needing_desc = [
        # Figure dari paper yang belum punya deskripsi LLM (hanya manual)
        # Fig 10-13 (Office #2 results) – tidak ada dalam JSON images
        {
            "key": "page_13_fig10",
            "caption": "Fig. 10 – Visual comfort index office #1",
            "pdf_page": 13,
            "note": "Grafik visual comfort index 20 test, Office #1",
        },
        {
            "key": "page_14_fig11",
            "caption": "Fig. 11 – Thermal comfort index office #2",
            "pdf_page": 14,
            "note": "Grafik thermal comfort index 20 test, Office #2",
        },
        {
            "key": "page_15_fig12",
            "caption": "Fig. 12 – Acoustics comfort index office #2",
            "pdf_page": 15,
            "note": "Grafik acoustics comfort index 20 test, Office #2",
        },
        {
            "key": "page_15_fig13",
            "caption": "Fig. 13 – Visual comfort index office #2",
            "pdf_page": 15,
            "note": "Grafik visual comfort index 20 test, Office #2",
        },
        {
            "key": "page_16_fig14",
            "caption": "Fig. 14 – Mean values of IEQ_Tot, optimal layout configurations (RL comparison)",
            "pdf_page": 16,
            "note": "Grafik perbandingan rata-rata IEQ_Tot: MORL vs DQN vs A2C vs PPO",
        },
        {
            "key": "page_16_fig15",
            "caption": "Fig. 15 – Standard deviation of IEQ_Tot (RL comparison)",
            "pdf_page": 16,
            "note": "Grafik standar deviasi IEQ_Tot per test untuk setiap algoritma RL",
        },
        {
            "key": "page_16_fig16",
            "caption": "Fig. 16 – Execution times (RL comparison)",
            "pdf_page": 16,
            "note": "Grafik waktu eksekusi (detik) per test untuk setiap algoritma RL",
        },
        {
            "key": "page_17_fig17",
            "caption": "Fig. 17 – Mean values of IEQ_Tot, optimal layout configurations (NSGA-II comparison)",
            "pdf_page": 17,
            "note": "Grafik perbandingan rata-rata IEQ_Tot: MORL vs NSGA-II",
        },
        {
            "key": "page_18_fig18",
            "caption": "Fig. 18 – Standard deviation of IEQ_Tot (NSGA-II comparison)",
            "pdf_page": 18,
            "note": "Grafik standar deviasi IEQ_Tot: MORL vs NSGA-II",
        },
        {
            "key": "page_19_fig19",
            "caption": "Fig. 19 – Execution times (NSGA-II comparison)",
            "pdf_page": 19,
            "note": "Grafik waktu eksekusi: MORL vs NSGA-II (MORL ~21 detik, NSGA-II ~105 detik)",
        },
    ]

    for fig in figures_needing_desc:
        if fig["key"] not in figure_cache:
            screenshots = find_screenshots_for_page(fig["pdf_page"])
            items.append({
                "category": "figure_missing_description",
                "severity": "MEDIUM",
                "description": f"Gambar belum punya deskripsi teks: {fig['caption']}",
                "pdf_page": fig["pdf_page"],
                "figure_key": fig["key"],
                "note": fig["note"],
                "reference_screenshots": screenshots,
                "action": (
                    f"Tambahkan deskripsi ke figure_descriptions.json "
                    f"dengan key '{fig['key']}', lalu jalankan ulang "
                    f"rebuild_markdown.py. Atau tambahkan langsung ke "
                    f"data/markdown/furniture_arrangement_ieq_2023_rebuilt.md "
                    f"sebagai '> **Deskripsi gambar:** ...'."
                ),
            })

    # ── 4. Cek sisa masalah lain ───────────────────────────────────────────
    if rebuilt_text:
        # Cek karakter BEL (\x07) yang masih ada
        bel_lines = [
            i + 1
            for i, line in enumerate(rebuilt_text.splitlines())
            if "\x07" in line
        ]
        for line_no in bel_lines:
            items.append({
                "category": "encoding_artifact",
                "severity": "LOW",
                "description": "Karakter kontrol BEL (\\x07) masih ada di baris ini",
                "line_in_rebuilt_md": line_no,
                "action": "Hapus karakter \\x07 dari baris ini",
            })

        # Cek unicode codepoint yang belum di-decode
        for m in re.finditer(r"\bu1D[0-9A-F]{3}\b", rebuilt_text):
            line_no = rebuilt_text[:m.start()].count("\n") + 1
            items.append({
                "category": "encoding_artifact",
                "severity": "MEDIUM",
                "description": f"Unicode codepoint tidak terdecode: {m.group(0)!r}",
                "line_in_rebuilt_md": line_no,
                "action": f"Ganti {m.group(0)!r} dengan karakter Unicode yang benar "
                           f"(u1D6FC=α, u1D6FE=γ, u1D716=ε)",
            })

    # ── Tulis output markdown ──────────────────────────────────────────────
    high = [i for i in items if i.get("severity") == "HIGH"]
    medium = [i for i in items if i.get("severity") == "MEDIUM"]
    low = [i for i in items if i.get("severity") == "LOW"]

    lines = [
        "# Daftar Item untuk Perbaikan Manual",
        "",
        f"**Dibuat:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**File target:** `data/markdown/furniture_arrangement_ieq_2023_rebuilt.md`  ",
        f"**Total item:** {len(items)} ({len(high)} HIGH, {len(medium)} MEDIUM, {len(low)} LOW)",
        "",
        "> **Catatan:** Item ini tidak bisa diperbaiki otomatis. Item HIGH harus diselesaikan",
        "> sebelum pipeline RAG dapat dijalankan dengan benar.",
        "",
        "---",
        "",
    ]

    for severity, label, emoji in [
        ("HIGH", "Prioritas Tinggi", "🔴"),
        ("MEDIUM", "Prioritas Sedang", "🟡"),
        ("LOW", "Prioritas Rendah", "🟢"),
    ]:
        group = [i for i in items if i.get("severity") == severity]
        if not group:
            continue

        lines += [
            f"## {emoji} {label} ({len(group)} item)",
            "",
        ]

        for idx, item in enumerate(group, 1):
            cat = item.get("category", "").replace("_", " ").title()
            desc = item.get("description", "")
            action = item.get("action", "")
            page = item.get("pdf_page") or item.get("line_in_rebuilt_md")
            page_label = (
                f"Halaman PDF: {page}"
                if item.get("pdf_page")
                else f"Baris di rebuilt.md: {page}"
            ) if page else ""
            screenshots = item.get("reference_screenshots", [])
            eq_num = item.get("equation_number")
            context = item.get("context", "")

            lines += [
                f"### {severity}-{idx:02d}: {cat}",
                "",
                f"**Deskripsi:** {desc}  ",
            ]

            if page_label:
                lines.append(f"**Lokasi:** {page_label}  ")
            if eq_num:
                lines.append(f"**Nomor persamaan:** Eq. ({eq_num})  ")
            if context:
                lines.append(f"**Konteks:** `{context}`  ")

            lines += [
                f"**Tindakan:** {action}",
                "",
            ]

            if screenshots:
                lines.append("**Screenshot referensi:**")
                for s in screenshots:
                    lines.append(f"- [`{Path(s).name}`](file:///{ROOT / s})")
                lines.append("")

            lines.append("- [ ] Selesai")
            lines.append("")

    lines += [
        "---",
        "",
        "## Panduan Perbaikan Rumus LaTeX",
        "",
        "Semua rumus berikut tersedia di versi LlamaParse playground:",
        f"`data/llamaparse_playground_original/furniture_arrangement_ieq_2023.md`",
        "",
        "Format yang benar adalah `$$...$$` untuk display math dan `$...$` untuk inline math.",
        "",
        "### Rumus Utama (dari paper)",
        "",
        "| No. | Deskripsi | LaTeX |",
        "|-----|-----------|-------|",
        "| 1 | Bellman Equation | `$$Q(s, a) \\leftarrow (1-\\alpha)Q(s,a) + \\alpha[R + \\gamma \\cdot \\max_{a'} Q(s',a')]$$` |",
        "| 2 | Q̂-vector | `$$\\hat{Q}(s, a) = (\\hat{Q}_1(s, a), \\dots, \\hat{Q}_m(s, a))$$` |",
        "| 3 | SQ scalarized | `$$SQ(s, a) = \\sum_{i=1}^{m} w_i Q_i(s, a)$$` |",
        "| 7 | Sound pressure | `$$L_{Receiver} = L_{Source} + 10\\log(Q/(4\\pi r^2) + 4/Ac_R)$$` |",
        "| 16 | R_IEQ | `$$R_{IEQ} = p_{TC} \\cdot TC_{index} + p_{AC} \\cdot AC_{index} + p_{VC} \\cdot VC_{index}$$` |",
        "",
    ]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Output: {OUTPUT}")
    print(f"Total item: {len(items)} ({len(high)} HIGH, {len(medium)} MEDIUM, {len(low)} LOW)")

    # Simpan juga sebagai JSON untuk referensi script lain
    json_output = OUTPUT.with_suffix(".json")
    json_output.write_text(
        json.dumps(items, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"JSON: {json_output}")


if __name__ == "__main__":
    main()
