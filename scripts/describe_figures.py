#!/usr/bin/env python3
"""
describe_figures.py
-------------------
Menghasilkan deskripsi teks untuk setiap figure bermakna di PDF menggunakan
LlamaCloud vision API. Hasil di-cache ke JSON agar tidak memanggil API ulang.

Idempotent: jika cache sudah ada dan tidak --force, skip figure yang sudah ada.

Usage:
    python scripts/describe_figures.py [--force]
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import pymupdf
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# ── Konfigurasi path ──────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
PDF_PATH = ROOT / "data/raw/furniture_arrangement_ieq_2023.pdf"
LLAMAPARSE_JSON = (
    ROOT
    / "data/llamaparse_playground_original"
    / "furniture_arrangement_ieq_2023 (1).json"
)
ASSETS_DIR = ROOT / "data/processed/assets/furniture_arrangement_ieq_2023"
CACHE_PATH = ROOT / "data/processed/assets/figure_descriptions.json"

# Ambang batas ukuran gambar (px): abaikan ikon/logo kecil
MIN_WIDTH_PX = 80
MIN_HEIGHT_PX = 60

# Render resolution
RENDER_DPI = 150
RENDER_SCALE = RENDER_DPI / 72  # PDF unit → pixel

LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY", "")

# ── Mapping caption dari context sekitar gambar (dari analisis PDF) ───────────
# Ini digunakan sebagai fallback jika LlamaCloud tidak bisa deskripsi
KNOWN_FIGURE_CONTEXT = {
    "page_1_item_5": {
        "skip": True,
        "reason": "Logo/icon kecil (13x10 px) – bukan figure bermakna",
    },
    "page_11_item_10": {
        "caption": "Fig. 8 – Thermal comfort index office #1",
        "fig_num": 8,
        "context": (
            "Diagram batang berdampingan (grouped bar chart) menampilkan "
            "Thermal Comfort index (TC index) untuk 20 test pada Office #1. "
            "Sumbu-X: Test 1 hingga Test 20; Sumbu-Y: Thermal Comfort index (rentang 80–100%). "
            "Batang oranye mewakili User 1 dan batang kuning mewakili User 2. "
            "Garis merah horizontal putus-putus menunjukkan ambang batas standar (threshold = 90%). "
            "Seluruh nilai TC index untuk User 1 dan User 2 pada Test 1–20 konsisten "
            "stabil pada nilai 95.0%, melampaui batas standar minimum."
        ),
    },
    "page_11_item_12": {
        "caption": "Fig. 4 – Office #1-layout pattern #1",
        "fig_num": 4,
        "context": (
            "Diagram denah kantor Office #1 (4.5×3.5 m) menampilkan "
            "Layout Pattern #1: posisi dua meja kerja (Desk User #1 di "
            "koordinat (2,2) orientasi Horizontal-up; Desk User #2 di "
            "koordinat (5,2) orientasi Horizontal-down). Jarak antar "
            "pengguna 304 cm, keduanya jauh dari pintu."
        ),
    },
    "page_11_item_13": {
        "caption": "Fig. 6 – Office #2-layout pattern #1",
        "fig_num": 6,
        "context": (
            "Diagram denah kantor Office #2 menampilkan Layout Pattern #1: "
            "posisi dua meja kerja (Desk User #1 di koordinat (5,8) "
            "orientasi Vertical-left; Desk User #2 di koordinat (0,2) "
            "orientasi Horizontal-down). Jarak antar pengguna 370 cm."
        ),
    },
    "page_11_item_14": {
        "caption": "Fig. 5 – Office #1-layout pattern #2",
        "fig_num": 5,
        "context": (
            "Diagram denah kantor Office #1 menampilkan Layout Pattern #2: "
            "posisi dua meja kerja (Desk User #1 di koordinat (2,1) "
            "orientasi Vertical-right; Desk User #2 di koordinat (5,2) "
            "orientasi Horizontal-down). Jarak antar pengguna 200 cm, "
            "lebih dekat dari Layout Pattern #1."
        ),
    },
    "page_12_item_3": {
        "caption": "Fig. 7 – Office #2-layout pattern #2",
        "fig_num": 7,
        "context": (
            "Diagram denah kantor Office #2 menampilkan Layout Pattern #2: "
            "posisi dua meja kerja (Desk User #1 di koordinat (1,2) "
            "orientasi Horizontal-up; Desk User #2 di koordinat (4,7) "
            "orientasi Horizontal-down). Jarak antar pengguna 353 cm."
        ),
    },
    "page_12_item_12": {
        "caption": "Fig. 9 – Acoustics comfort index office #1",
        "fig_num": 9,
        "context": (
            "Diagram batang berdampingan (grouped bar chart) menampilkan "
            "Acoustics Comfort index (AC index) untuk 20 test pada Office #1. "
            "Sumbu-X: Test 1 hingga Test 20; Sumbu-Y: Acoustics Comfort index (rentang 70–100%). "
            "Batang biru mewakili User 1 dan batang kuning mewakili User 2. "
            "Garis merah horizontal putus-putus menunjukkan ambang batas standar (threshold = 95%). "
            "Nilai AC index berkisar antara 87% hingga 88%, seluruhnya berada di bawah ambang batas "
            "karena tekanan akustik kombinasi unit AC (55 dB) dan koridor/aisle (50 dB)."
        ),
    },
    "page_14_item_5": {
        "skip": True,
        "reason": "Elemen grafis kecil (43x12 px) – bukan figure bermakna",
    },
}

# Figure tambahan yang ada di JSON tapi belum di-crop (perlu render dari PDF)
ADDITIONAL_FIGURES = {
    # Page 1: logo springer – skip
    # Page 8: Fig. 1 – illuminance table (ada di JSON sebagai tabel, bukan image)
    # Page 9: Fig. 2 – illuminance table (sama)
    # Page 10: Fig. 3 – desk orientations (ada sebagai drawing/text di JSON)
    # Page 13-21: grafik fig 10-19 (tidak ada di JSON sebagai image item)
}

# Figure yang perlu di-render dari PDF karena tidak ada dalam JSON images
FIGURES_FROM_PDF = [
    {
        "key": "page_8_fig1",
        "page": 8,  # 1-indexed
        "fig_num": 1,
        "caption": "Fig. 1 – Office #1 and illuminance values on its surface",
        "context": (
            "Denah kantor Office #1 (4.5×3.5 m, grid 9×7 sel @ 0.5m) "
            "dengan nilai illuminance dalam lux untuk setiap sel. "
            "Jendela menghadap barat-laut di sisi kiri; pintu di sisi kanan bawah. "
            "AC unit di bawah jendela (55 dB). "
            "Distribusi cahaya: pojok kiri atas (gelap, 50–130 lx), "
            "area tengah (~300 lx), area dekat jendela (500–800 lx). "
            "Matriks nilai illuminance lengkap (7 baris × 9 kolom): "
            "Baris 1: [80,50,130,130,130,110,100,90,90]; "
            "Baris 2: [80,50,130,130,130,110,100,90,90]; "
            "Baris 3: [440,350,350,300,300,300,100,90,90]; "
            "Baris 4: [540,350,350,300,300,200,200,150,90]; "
            "Baris 5: [800,350,300,300,300,200,200,150,125]; "
            "Baris 6: [700,350,370,300,300,200,200,150,110]; "
            "Baris 7: [300,350,370,330,200,190,190,180,200]."
        ),
        "is_known": True,  # sudah diketahui dari JSON/koreksi manual
    },
    {
        "key": "page_9_fig2",
        "page": 9,
        "fig_num": 2,
        "caption": "Fig. 2 – Office #2 and illuminance values on its surface",
        "context": (
            "Denah kantor Office #2 (grid 9×7 sel @ 0.5m) dengan dua jendela: "
            "barat-laut dan utara. Pintu di sudut dinding bawah. "
            "Dua unit AC di dinding berlawanan (masing-masing 55 dB). "
            "Distribusi cahaya: area tengah (~300 lx), "
            "dekat jendela barat-laut (500–700 lx), "
            "dekat jendela utara (400–550 lx), "
            "sudut gelap (nilai 0 untuk area di luar ruangan). "
            "Matriks nilai illuminance lengkap (7 baris × 9 kolom): "
            "Baris 1: [400,580,550,550,250,200,200,0,0]; "
            "Baris 2: [350,550,530,500,330,330,340,0,0]; "
            "Baris 3: [250,350,350,300,300,300,300,90,90]; "
            "Baris 4: [250,350,350,300,300,300,450,580,700]; "
            "Baris 5: [250,300,300,300,300,330,430,550,680]; "
            "Baris 6: [200,300,300,300,300,330,430,530,650]; "
            "Baris 7: [190,250,250,330,200,190,400,500,630]."
        ),
        "is_known": True,
    },
    {
        "key": "page_10_fig3",
        "page": 10,
        "fig_num": 3,
        "caption": "Fig. 3 – Possible desk orientations",
        "context": (
            "Diagram menampilkan 4 kemungkinan orientasi meja kerja "
            "(desk) dalam sistem grid ruangan: "
            "(1) HORIZONTAL-UP: meja horisontal, pengguna menghadap ke atas; "
            "(2) VERTICAL-RIGHT: meja vertikal, pengguna menghadap ke kanan; "
            "(3) VERTICAL-LEFT: meja vertikal, pengguna menghadap ke kiri; "
            "(4) HORIZONTAL-DOWN: meja horisontal, pengguna menghadap ke bawah. "
            "Setiap orientasi ditunjukkan dengan meja berukuran 150×50 cm "
            "dan simbol pengguna (kursi). Sumbu x′ dan y′ menunjukkan "
            "sistem koordinat referensi."
        ),
        "is_known": True,
    },
    {
        "key": "page_13_fig10",
        "page": 13,
        "fig_num": 10,
        "caption": "Fig. 10 – Visual comfort index office #1",
        "context": (
            "Diagram batang berdampingan (grouped bar chart) menampilkan Visual Comfort index "
            "(VC index) untuk 20 test pada Office #1. Sumbu-X: Test 1 hingga Test 20; "
            "Sumbu-Y: Visual Comfort index (rentang 85–100%). Batang ungu tua mewakili User 1 "
            "dan batang ungu muda mewakili User 2. Garis merah horizontal putus-putus menunjukkan ambang "
            "batas standar (threshold = 97%). Nilai berkisar antara 93.2% hingga 95.5% (kecuali "
            "Test 7 User 1 turun ke 87.4%), seluruhnya berada di bawah standar karena orientasi "
            "jendela tunggal ke barat-laut yang tidak optimal sepanjang hari."
        ),
        "is_known": True,
    },
    {
        "key": "page_14_fig11",
        "page": 14,
        "fig_num": 11,
        "caption": "Fig. 11 – Thermal comfort index office #2",
        "context": (
            "Diagram batang berdampingan (grouped bar chart) menampilkan Thermal Comfort index "
            "(TC index) untuk 20 test pada Office #2. Sumbu-X: Test 1 hingga Test 20; "
            "Sumbu-Y: Thermal Comfort index (rentang 80–100%). Batang oranye mewakili User 1 "
            "dan batang kuning mewakili User 2. Garis merah horizontal putus-putus menunjukkan ambang batas "
            "standar (threshold = 90%). Nilai mayoritas pengujian konsisten pada 95.0%, dengan "
            "penurunan kecil ke 93.0% pada Test 3, 4, 18, dan 20, seluruhnya melampaui standar."
        ),
        "is_known": True,
    },
    {
        "key": "page_15_fig12",
        "page": 15,
        "fig_num": 12,
        "caption": "Fig. 12 – Acoustics comfort index office #2",
        "context": (
            "Diagram batang berdampingan (grouped bar chart) menampilkan Acoustics Comfort index "
            "(AC index) untuk 20 test pada Office #2. Sumbu-X: Test 1 hingga Test 20; "
            "Sumbu-Y: Acoustics Comfort index (rentang 70–100%). Batang biru mewakili User 1 "
            "dan batang kuning mewakili User 2. Garis merah horizontal putus-putus menunjukkan ambang batas "
            "standar (threshold = 95%). Nilai stabil di kisaran 84.8%–85.0%, di bawah standar "
            "karena tekanan akustik gabungan dari dua unit AC (masing-masing 55 dB)."
        ),
        "is_known": True,
    },
    {
        "key": "page_15_fig13",
        "page": 15,
        "fig_num": 13,
        "caption": "Fig. 13 – Visual comfort index office #2",
        "context": (
            "Diagram batang berdampingan (grouped bar chart) menampilkan Visual Comfort index "
            "(VC index) untuk 20 test pada Office #2. Sumbu-X: Test 1 hingga Test 20; "
            "Sumbu-Y: Visual Comfort index (rentang 85–100%). Batang ungu tua mewakili User 1 "
            "dan batang ungu muda mewakili User 2. Garis merah horizontal putus-putus menunjukkan ambang batas "
            "standar (threshold = 97%). Nilai berkisar antara 97.2% hingga 98.6% (kecuali Test 11 "
            "dan Test 19 yang sedikit turun ke 94.9%), sebagian besar melampaui threshold berkat "
            "adanya dua jendela pada dinding barat-laut dan utara."
        ),
        "is_known": True,
    },
    {
        "key": "page_16_fig14",
        "page": 16,
        "fig_num": 14,
        "caption": "Fig. 14 – Mean values of IEQ_Tot related to optimal layout configurations (RL comparison)",
        "context": (
            "Diagram batang berkelompok (grouped bar chart) membandingkan nilai rata-rata "
            "kriteria evaluasi IEQ_Tot untuk 5 pengujian (#Test 1–5) pada 4 algoritma RL. "
            "Sumbu-X: #Test (1 sampai 5); Sumbu-Y: Mean Value of IEQ_Tot (skala 595–620). "
            "Legenda: A2C (biru), PPO (oranye), DQN (kuning), MORL (ungu). "
            "Nilai eksak per test: "
            "Test 1: [A2C: 606.40, PPO: 610.93, DQN: 609.90, MORL: 616.69]; "
            "Test 2: [A2C: 606.33, PPO: 613.62, DQN: 611.85, MORL: 617.91]; "
            "Test 3: [A2C: 611.93, PPO: 614.99, DQN: 614.24, MORL: 618.30]; "
            "Test 4: [A2C: 604.53, PPO: 614.73, DQN: 614.15, MORL: 618.57]; "
            "Test 5: [A2C: 603.35, PPO: 615.46, DQN: 614.24, MORL: 618.63]. "
            "MORL secara konsisten mencapai IEQ_Tot tertinggi di setiap pengujian."
        ),
        "is_known": True,
    },
    {
        "key": "page_16_fig15",
        "page": 16,
        "fig_num": 15,
        "caption": "Fig. 15 – Standard deviation of IEQ_Tot related to optimal layout configurations (RL comparison)",
        "context": (
            "Diagram batang berkelompok (grouped bar chart) membandingkan standar deviasi "
            "IEQ_Tot untuk 5 pengujian (#Test 1–5) pada algoritma RL. "
            "Sumbu-X: #Test (1 sampai 5); Sumbu-Y: Standard Deviation (skala 0–10). "
            "Legenda: A2C (biru), PPO (oranye), DQN (kuning), MORL (ungu). "
            "Nilai eksak per test: "
            "Test 1: [A2C: 9.02, PPO: 3.17, DQN: 6.42, MORL: 1.66]; "
            "Test 2: [A2C: 6.71, PPO: 2.16, DQN: 3.21, MORL: 1.92]; "
            "Test 3: [A2C: 4.89, PPO: 2.23, DQN: 2.45, MORL: 1.45]; "
            "Test 4: [A2C: 6.46, PPO: 2.11, DQN: 2.46, MORL: 1.14]; "
            "Test 5: [A2C: 5.35, PPO: 2.05, DQN: 2.01, MORL: 0.89]. "
            "MORL memiliki standar deviasi terendah (terbaik/paling stabil), sedangkan A2C paling fluktuatif."
        ),
        "is_known": True,
    },
    {
        "key": "page_16_fig16",
        "page": 16,
        "fig_num": 16,
        "caption": "Fig. 16 – Execution times (RL comparison)",
        "context": (
            "Diagram batang berkelompok (grouped bar chart) membandingkan waktu eksekusi "
            "untuk 5 pengujian (#Test 1–5) pada 4 algoritma RL. "
            "Sumbu-X: #Test (1 sampai 5); Sumbu-Y: Execution Time [s] (dalam detik, skala 0–30 s). "
            "Legenda: A2C (biru), PPO (oranye), DQN (kuning), MORL (ungu). "
            "Nilai eksak per test: "
            "Test 1: [A2C: 9.71 s, PPO: 8.10 s, DQN: 9.22 s, MORL: 4.00 s]; "
            "Test 2: [A2C: 14.52 s, PPO: 10.98 s, DQN: 14.19 s, MORL: 7.82 s]; "
            "Test 3: [A2C: 19.34 s, PPO: 13.43 s, DQN: 19.34 s, MORL: 11.58 s]; "
            "Test 4: [A2C: 23.77 s, PPO: 15.82 s, DQN: 24.16 s, MORL: 15.68 s]; "
            "Test 5: [A2C: 28.54 s, PPO: 18.20 s, DQN: 28.93 s, MORL: 19.39 s]. "
            "MORL menyelesaikan pelatihan tercepat di semua sesi pengujian."
        ),
        "is_known": True,
    },
    {
        "key": "page_17_fig17",
        "page": 17,
        "fig_num": 17,
        "caption": "Fig. 17 – Mean values of IEQ_Tot related to optimal layout configurations (NSGA-II comparison)",
        "context": (
            "Diagram batang berkelompok (grouped bar chart) membandingkan nilai rata-rata IEQ_Tot "
            "untuk 5 pengujian (#Test 1–5) antara algoritma NSGA-II dan MORL. "
            "Sumbu-X: #Test (1 sampai 5); Sumbu-Y: Mean Value of IEQ_Tot (skala 595–620). "
            "Legenda: NSGA-II (hijau), MORL (ungu). "
            "Nilai eksak per test: "
            "Test 1: [NSGA-II: 610.24, MORL: 616.69]; "
            "Test 2: [NSGA-II: 610.15, MORL: 617.91]; "
            "Test 3: [NSGA-II: 612.55, MORL: 618.30]; "
            "Test 4: [NSGA-II: 612.44, MORL: 618.57]; "
            "Test 5: [NSGA-II: 612.00, MORL: 618.63]. "
            "MORL secara konsisten melampaui NSGA-II dalam kualitas optimasi IEQ_Tot."
        ),
        "is_known": True,
    },
    {
        "key": "page_18_fig18",
        "page": 18,
        "fig_num": 18,
        "caption": "Fig. 18 – Standard deviation of IEQ_Tot related to optimal layout configurations (NSGA-II comparison)",
        "context": (
            "Diagram batang berkelompok (grouped bar chart) membandingkan standar deviasi "
            "IEQ_Tot untuk 5 pengujian (#Test 1–5) antara NSGA-II dan MORL. "
            "Sumbu-X: #Test (1 sampai 5); Sumbu-Y: Standard Deviation (skala 0–5). "
            "Legenda: NSGA-II (hijau), MORL (ungu). "
            "Nilai eksak per test: "
            "Test 1: [NSGA-II: 4.53, MORL: 1.66]; "
            "Test 2: [NSGA-II: 3.87, MORL: 1.92]; "
            "Test 3: [NSGA-II: 2.66, MORL: 1.45]; "
            "Test 4: [NSGA-II: 3.12, MORL: 1.14]; "
            "Test 5: [NSGA-II: 4.03, MORL: 0.89]. "
            "MORL menghasilkan variabilitas solusi yang jauh lebih kecil dan konsisten dibanding NSGA-II."
        ),
        "is_known": True,
    },
    {
        "key": "page_19_fig19",
        "page": 19,
        "fig_num": 19,
        "caption": "Fig. 19 – Execution times (NSGA-II comparison)",
        "context": (
            "Diagram batang berkelompok (grouped bar chart) membandingkan waktu eksekusi "
            "untuk 5 pengujian (#Test 1–5) antara NSGA-II dan MORL. "
            "Sumbu-X: #Test (1 sampai 5); Sumbu-Y: Execution Time [s] (dalam detik, skala 0–22 s). "
            "Legenda: NSGA-II (hijau), MORL (ungu). "
            "Nilai eksak per test: "
            "Test 1: [NSGA-II: 4.40 s, MORL: 4.00 s]; "
            "Test 2: [NSGA-II: 8.52 s, MORL: 7.82 s]; "
            "Test 3: [NSGA-II: 12.61 s, MORL: 11.58 s]; "
            "Test 4: [NSGA-II: 16.37 s, MORL: 15.68 s]; "
            "Test 5: [NSGA-II: 20.52 s, MORL: 19.39 s]. "
            "MORL sedikit lebih cepat di setiap test dibanding konfigurasi sepadan NSGA-II."
        ),
        "is_known": True,
    },
]


def load_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(cache_path: Path, cache: dict) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def render_page_to_png(pdf_path: Path, page_number: int, output_path: Path) -> Path:
    """Render halaman PDF (1-indexed) ke PNG."""
    pdf = pymupdf.open(pdf_path)
    page = pdf[page_number - 1]
    matrix = pymupdf.Matrix(RENDER_SCALE, RENDER_SCALE)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(output_path)
    pdf.close()
    return output_path


def describe_image_via_llamacloud(
    image_path: Path, caption_hint: str, context_hint: str
) -> str:
    """
    Panggil LlamaCloud untuk mendeskripsikan gambar.
    Fallback ke context_hint jika API gagal.
    """
    if not LLAMA_CLOUD_API_KEY:
        print(
            f"  [WARN] LLAMA_CLOUD_API_KEY tidak tersedia, "
            f"gunakan deskripsi manual untuk {image_path.name}"
        )
        return context_hint

    try:
        from llama_cloud import LlamaCloud

        client = LlamaCloud()

        # Upload gambar sebagai file
        with open(image_path, "rb") as f:
            uploaded = client.files.create(file=image_path, purpose="parse")

        # Parse dengan premium untuk vision
        result = client.parsing.parse(
            file_id=uploaded.id,
            tier="premium",
            version="latest",
            expand=["markdown"],
            system_prompt=(
                "You are a scientific figure description assistant. "
                "Describe this figure from an academic paper about "
                "furniture arrangement and indoor environmental quality (IEQ). "
                "Be concise but complete. Focus on: what the figure shows, "
                "key data values visible, axes labels, and scientific meaning. "
                "Respond in Indonesian (Bahasa Indonesia)."
            ),
        )

        pages = result.markdown.pages if result.markdown else []
        texts = [p.markdown or "" for p in pages if getattr(p, "success", True)]
        description = "\n".join(texts).strip()

        if not description or len(description) < 20:
            print(f"  [WARN] LlamaCloud tidak menghasilkan deskripsi, gunakan fallback")
            return context_hint

        return description

    except Exception as exc:
        print(f"  [WARN] LlamaCloud vision gagal ({type(exc).__name__}: {exc}), "
              f"gunakan deskripsi manual")
        return context_hint


def process_figures_from_json(
    llamaparse_json: Path,
    assets_dir: Path,
    cache: dict,
    force: bool,
) -> dict:
    """Proses gambar yang sudah ada di assets_dir (dari JSON LlamaParse)."""
    data = json.loads(llamaparse_json.read_text(encoding="utf-8"))
    results = {}

    for page_index, page in enumerate(data.get("pages", [])):
        page_no = page.get("page_number", page_index + 1)

        for item_index, item in enumerate(page.get("items", [])):
            if item.get("type") != "image":
                continue

            bbox_list = item.get("bbox") or []
            bbox = bbox_list[0] if isinstance(bbox_list, list) and bbox_list else {}
            w = float(bbox.get("w", 0))
            h = float(bbox.get("h", 0))

            # Skip gambar kecil (logo/ikon)
            if w < MIN_WIDTH_PX or h < MIN_HEIGHT_PX:
                key = f"page_{page_no}_item_{item_index}"
                results[key] = {
                    "skip": True,
                    "reason": f"Terlalu kecil ({w:.0f}x{h:.0f} px)",
                }
                continue

            key = f"page_{page_no}_item_{item_index}"

            # Cek cache
            if key in cache and not force:
                print(f"  [CACHE] {key} – skip (sudah ada di cache)")
                results[key] = cache[key]
                continue

            # Cek known context
            known = KNOWN_FIGURE_CONTEXT.get(key, {})
            if known.get("skip"):
                results[key] = known
                continue

            caption = known.get("caption", item.get("caption") or f"Figure page {page_no}")
            context = known.get("context", "")

            # Cari file gambar yang sudah ada (utamakan fig_XX.png crop jika tersedia)
            fig_num = known.get("fig_num")
            fig_crop = assets_dir / f"fig_{fig_num:02d}.png" if fig_num else None
            if fig_crop and fig_crop.exists():
                asset_file = fig_crop
                print(f"  [CROP] {key}: gunakan crop {fig_crop.name}")
            else:
                asset_file = assets_dir / f"page_{page_no:02d}_item_{item_index:03d}.png"

            if not asset_file.exists():
                # Coba render dari PDF
                print(
                    f"  [RENDER] {key}: aset tidak ada, render dari PDF halaman {page_no}"
                )
                asset_file = assets_dir / f"page_{page_no:02d}_item_{item_index:03d}.png"
                try:
                    pdf_path = llamaparse_json.parent.parent.parent / "data/raw/furniture_arrangement_ieq_2023.pdf"
                    render_page_to_png(pdf_path, page_no, asset_file)
                except Exception as exc:
                    print(f"  [ERROR] Render gagal: {exc}")
                    results[key] = {
                        "caption": caption,
                        "description": context or "[Deskripsi tidak tersedia]",
                        "source": "fallback_manual",
                        "error": str(exc),
                    }
                    continue

            print(f"  [DESCRIBE] {key}: {caption}")

            if context:
                # Sudah ada deskripsi manual yang valid, skip API call
                description = context
                source = "manual_known"
            else:
                description = describe_image_via_llamacloud(
                    asset_file, caption, context
                )
                source = "llamacloud_vision"
                time.sleep(1)  # Rate limit

            result = {
                "page": page_no,
                "item": item_index,
                "caption": caption,
                "description": description,
                "asset_path": str(asset_file),
                "source": source,
            }
            results[key] = result

    return results


def process_additional_figures(
    pdf_path: Path,
    assets_dir: Path,
    cache: dict,
    force: bool,
) -> dict:
    """Proses figure yang diketahui dari PDF tapi tidak ada di JSON sebagai item image."""
    results = {}

    for fig in FIGURES_FROM_PDF:
        key = fig["key"]

        if key in cache and not force:
            print(f"  [CACHE] {key} – skip")
            results[key] = cache[key]
            continue

        caption = fig["caption"]
        context = fig["context"]
        page_no = fig["page"]

        # Render halaman jika belum ada screenshot / crop
        fig_num = fig.get("fig_num")
        fig_crop = assets_dir / f"fig_{fig_num:02d}.png" if fig_num else None
        render_path = assets_dir / f"render_page_{page_no:02d}.png"

        if fig_crop and fig_crop.exists():
            render_path = fig_crop
            print(f"  [CROP] {key}: gunakan crop {fig_crop.name}")
        else:
            # Cek apakah screenshot sudah ada di validation
            val_dir = assets_dir.parent.parent.parent / "data/validation"
            existing = None
            for pattern in [
                f"original_page_{page_no}.png",
                f"original_page-{page_no:02d}.png",
                f"original_page_{page_no:02d}.png",
            ]:
                candidate = val_dir / pattern
                if candidate.exists():
                    existing = candidate
                    break

            if existing:
                render_path = existing
                print(f"  [REUSE] {key}: gunakan screenshot existing {existing.name}")
            else:
                print(f"  [RENDER] {key}: render halaman {page_no}")
                try:
                    render_page_to_png(pdf_path, page_no, render_path)
                except Exception as exc:
                    print(f"  [ERROR] Render gagal: {exc}")
                    results[key] = {
                        "caption": caption,
                        "description": context,
                        "source": "fallback_manual",
                        "error": str(exc),
                    }
                    continue

        if fig.get("is_known") and context:
            description = context
            source = "manual_known"
            print(f"  [MANUAL] {key}: deskripsi dari knowledge base manual")
        else:
            print(f"  [DESCRIBE] {key}: {caption}")
            description = describe_image_via_llamacloud(render_path, caption, context)
            source = "llamacloud_vision"
            time.sleep(1)

        results[key] = {
            "page": page_no,
            "caption": caption,
            "description": description,
            "asset_path": str(render_path),
            "source": source,
        }

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Hasilkan deskripsi teks untuk figure bermakna di PDF."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Paksa deskripsi ulang meski sudah di cache",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("DESCRIBE FIGURES")
    print("=" * 60)

    cache = load_cache(CACHE_PATH)
    print(f"Cache dimuat: {len(cache)} entri")

    # Proses gambar dari JSON LlamaParse
    print("\n[1/2] Proses gambar dari JSON LlamaParse...")
    json_results = process_figures_from_json(
        LLAMAPARSE_JSON, ASSETS_DIR, cache, args.force
    )

    # Proses figure tambahan dari PDF
    print("\n[2/2] Proses figure tambahan dari PDF...")
    pdf_results = process_additional_figures(
        PDF_PATH, ASSETS_DIR, cache, args.force
    )

    # Merge semua hasil
    all_results = {**cache, **json_results, **pdf_results}

    # Simpan cache
    save_cache(CACHE_PATH, all_results)
    print(f"\nTotal figure diproses: {len(all_results)}")
    print(f"Cache disimpan: {CACHE_PATH}")

    # Summary
    skipped = sum(1 for v in all_results.values() if v.get("skip"))
    described = len(all_results) - skipped
    print(f"  Dideskripsikan: {described}")
    print(f"  Di-skip (ikon kecil): {skipped}")

    for key, val in all_results.items():
        if not val.get("skip"):
            src = val.get("source", "?")
            cap = val.get("caption", "")[:60]
            print(f"  [{src}] {key}: {cap}")


if __name__ == "__main__":
    main()
