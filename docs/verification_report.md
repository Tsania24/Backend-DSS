# Laporan Verifikasi Kualitas Tahap 1: Pipeline Parsing & RAG

**Dokumen Sumber:** `data/raw/furniture_arrangement_ieq_2023.pdf`  
**Waktu Verifikasi:** 20 November 2026  
**Status Backup:** Disimpan di `backups/verification_20261120/`  

---

## 1. Ringkasan Eksekutif

Sesuai instruksi verifikasi kualitas Tahap 1, telah dilakukan pemeriksaan visual mandiri secara menyeluruh (multimodal vision langsung terhadap file crop visual dan halaman asli PDF) tanpa menebak dari pengetahuan umum:
1. **19 Figure Akademik:** Seluruh 19 figure dibuka, dibaca visualnya (tipe grafik, label sumbu, nama variabel, rentang angka, legenda warna, garis threshold, dan satuan), lalu dibandingkan dengan entri awal `figure_descriptions.json`.
   - **Hasil:** 7 figure denah/orientasi (`Fig. 1` s/d `Fig. 7`) berstatus **SESUAI**.
   - **Hasil:** 12 figure grafik (`Fig. 8` s/d `Fig. 19`) berstatus **ADA KESALAHAN** (pada teks awal Fig. 8–13 keliru disebut "grafik garis" padahal aktualnya adalah diagram batang/bar chart; Fig. 14–19 belum memuat angka numerik eksak per test dan satuan `[s]`; Fig. 19 terdapat kesalahan fatal mengutip angka narasi 105 s alih-alih data aktual grafik 4.40 s – 20.52 s).
   - **Tindakan:** Seluruh 12 deskripsi telah diperbaiki dengan data numerik visual lengkap, crop gambar resolusi tinggi (`fig_01.png` – `fig_19.png`) diintegrasikan, dan downstream pipeline telah diperbarui hingga chunks.
2. **8 Rumus Kompleks:** 8 rumus (termasuk rumus paling kompleks) dibandingkan simbol per simbol dengan potongan halaman asli PDF (`original_page_*.png` dan crop visual).
   - **Hasil:** Seluruh 8 rumus berstatus **SESUAI** (simbol, subscript, superscript, dan tanda operator tepat).

---

## 2. Tabel Verifikasi Kualitas 19 Deskripsi Gambar (Figures)

Pemeriksaan dilakukan langsung terhadap file crop gambar resolusi tinggi di `data/processed/assets/furniture_arrangement_ieq_2023/` (`fig_01.png` hingga `fig_19.png`) serta halaman asli PDF.

| No | ID Figure | Halaman | Status | Hasil Pengecekan Visual Detail | Perbaikan yang Dilakukan |
| :---: | :--- | :---: | :---: | :--- | :--- |
| 1 | **Fig. 1** – Office #1 illuminance | 8 | **SESUAI** | Denah kantor Office #1 (4.5×3.5 m) dengan grid illuminance 9 kolom × 7 baris. Nilai sel berkisar 50 lx (pojok gelap barat-laut baris 1-2) hingga 800 lx (dekat jendela baris 5). Sesuai persis dengan data visual PDF. | Deskripsi dipertahankan; aset ditautkan ke crop bersih `fig_01.png`. |
| 2 | **Fig. 2** – Office #2 illuminance | 9 | **SESUAI** | Denah kantor Office #2 dengan dua jendela (NW dan N) serta sudut dinding terpotong (nilai 0 di pojok timur-laut). Matriks 7×9 lux sesuai visual asli. | Deskripsi dipertahankan; aset ditautkan ke crop bersih `fig_02.png`. |
| 3 | **Fig. 3** – Possible desk orientations | 10 | **SESUAI** | 4 orientasi meja: Horizontal-up, Vertical-right, Vertical-left, Horizontal-down dengan sistem koordinat referensi $x'$ dan $y'$. Dimensi meja 150×50 cm. Sesuai visual asli. | Deskripsi dipertahankan; aset ditautkan ke crop bersih `fig_03.png`. |
| 4 | **Fig. 4** – Office #1 Layout Pattern #1 | 11 | **SESUAI** | Denah 2D (kiri, dimensi 1.25m, 0.75m) dan render 3D (kanan). Posisi meja: User 1 di (2,2) Horizontal-up; User 2 di (5,2) Horizontal-down. Jarak 304 cm. | Deskripsi dipertahankan; aset ditautkan ke crop bersih `fig_04.png`. |
| 5 | **Fig. 5** – Office #1 Layout Pattern #2 | 11 | **SESUAI** | Denah 2D dan render 3D. Posisi meja: User 1 di (2,1) Vertical-right; User 2 di (5,2) Horizontal-down. Jarak 200 cm. Sesuai visual asli. | Deskripsi dipertahankan; aset ditautkan ke crop bersih `fig_05.png`. |
| 6 | **Fig. 6** – Office #2 Layout Pattern #1 | 12 | **SESUAI** | Denah 2D dan render 3D. Posisi meja: User 1 di (5,8) Vertical-left; User 2 di (0,2) Horizontal-down. Jarak 370 cm. Sesuai visual asli. | Deskripsi dipertahankan; aset ditautkan ke crop bersih `fig_06.png`. |
| 7 | **Fig. 7** – Office #2 Layout Pattern #2 | 13 | **SESUAI** | Denah 2D dan render 3D. Posisi meja: User 1 di (1,2) Horizontal-up; User 2 di (4,7) Horizontal-down. Jarak 353 cm. Sesuai visual asli. | Deskripsi dipertahankan; aset ditautkan ke crop bersih `fig_07.png`. |
| 8 | **Fig. 8** – Thermal comfort index office #1 | 13 | **ADA KESALAHAN** | **Tipe grafik keliru:** Pada teks awal tertulis *"Grafik garis"*, padahal aktualnya adalah **diagram batang berdampingan (grouped bar chart)**. Sumbu-X: Test 1–20; Sumbu-Y: Thermal Comfort index (80–100%). Batang oranye (User 1) & kuning (User 2). Garis putus-putus merah: threshold 90%. Nilai aktual konstan pada **95.0%**. | Memperbaiki jenis grafik menjadi diagram batang; menambahkan rincian sumbu-X, sumbu-Y, warna legenda, garis threshold 90%, dan nilai konstan 95.0%. Menautkan ke `fig_08.png`. |
| 9 | **Fig. 9** – Acoustics comfort index office #1 | 14 | **ADA KESALAHAN** | **Tipe grafik keliru:** Teks awal mencatat *"Grafik garis"*, aktualnya adalah **diagram batang berdampingan**. Sumbu-X: Test 1–20; Sumbu-Y: Acoustics Comfort index (70–100%). Batang biru (User 1) & kuning (User 2). Garis merah: threshold 95%. Nilai berkisar antara **87%–88%** (seluruhnya di bawah threshold). | Memperbaiki jenis grafik menjadi diagram batang; merinci label sumbu, ambang batas 95%, dan rentang nilai aktual 87%–88%. Menautkan ke `fig_09.png`. |
| 10 | **Fig. 10** – Visual comfort index office #1 | 14 | **ADA KESALAHAN** | **Tipe grafik keliru:** Teks awal mencatat *"Grafik garis"*, aktualnya adalah **diagram batang berdampingan**. Sumbu-X: Test 1–20; Sumbu-Y: Visual Comfort index (85–100%). Batang ungu tua (User 1) & ungu muda (User 2). Garis merah: threshold 97%. Nilai berada di kisaran **93.2%–95.5%** (khusus User 1 Test 7 turun ke **87.4%**). | Memperbaiki tipe grafik ke diagram batang; menambahkan anomali Test 7 (87.4%), threshold 97%, dan warna batang. Menautkan ke `fig_10.png`. |
| 11 | **Fig. 11** – Thermal comfort index office #2 | 15 | **ADA KESALAHAN** | **Tipe grafik keliru:** Teks awal mencatat *"Grafik garis"*, aktualnya adalah **diagram batang berdampingan**. Sumbu-X: Test 1–20; Sumbu-Y: Thermal Comfort index (80–100%). Garis merah: threshold 90%. Nilai konsisten **95.0%**, dengan sedikit drop ke **93.0%** pada Test 3, 4, 18, 20. | Memperbaiki tipe grafik ke diagram batang; merinci sumbu, legenda, threshold 90%, dan tes yang mengalami penurunan ke 93.0%. Menautkan ke `fig_11.png`. |
| 12 | **Fig. 12** – Acoustics comfort index office #2 | 15 | **ADA KESALAHAN** | **Tipe grafik keliru:** Teks awal mencatat *"Grafik garis"*, aktualnya adalah **diagram batang berdampingan**. Sumbu-X: Test 1–20; Sumbu-Y: Acoustics Comfort index (70–100%). Garis merah: threshold 95%. Nilai stabil pada rentang **84.8%–85.0%** di bawah threshold akibat 2 unit AC. | Memperbaiki tipe grafik ke diagram batang; merinci sumbu, legenda, threshold 95%, dan kestabilan nilai di 84.8%–85.0%. Menautkan ke `fig_12.png`. |
| 13 | **Fig. 13** – Visual comfort index office #2 | 16 | **ADA KESALAHAN** | **Tipe grafik keliru:** Teks awal mencatat *"Grafik garis"*, aktualnya adalah **diagram batang berdampingan**. Sumbu-X: Test 1–20; Sumbu-Y: Visual Comfort index (85–100%). Garis merah: threshold 97%. Nilai mayoritas melampaui batas (**97.2%–98.6%**), dengan penurunan kecil pada Test 11 dan 19 (**94.9%**). | Memperbaiki tipe grafik ke diagram batang; merinci sumbu, threshold 97%, rentang nilai, dan penurunan pada Test 11 & 19. Menautkan ke `fig_13.png`. |
| 14 | **Fig. 14** – Mean values of IEQ_Tot (RL) | 17 | **ADA KESALAHAN** | **Kurang data numerik eksak:** Visual adalah **diagram batang berkelompok (4 algoritma)**. Sumbu-X: #Test (1–5); Sumbu-Y: Mean Value of IEQ_Tot (595–620). Warna: A2C (biru), PPO (oranye), DQN (kuning), MORL (ungu). Angka tertera di tiap batang belum dicatat lengkap di deskripsi lama. | Menyertakan data lengkap per test:<br>• Test 1: [A2C: 606.40, PPO: 610.93, DQN: 609.90, MORL: 616.69]<br>• Test 2: [A2C: 606.33, PPO: 613.62, DQN: 611.85, MORL: 617.91]<br>• Test 3: [A2C: 611.93, PPO: 614.99, DQN: 614.24, MORL: 618.30]<br>• Test 4: [A2C: 604.53, PPO: 614.73, DQN: 614.15, MORL: 618.57]<br>• Test 5: [A2C: 603.35, PPO: 615.46, DQN: 614.24, MORL: 618.63]. Menautkan ke `fig_14.png`. |
| 15 | **Fig. 15** – Standard deviation of IEQ_Tot (RL) | 18 | **ADA KESALAHAN** | **Kurang data numerik eksak:** Visual adalah **diagram batang berkelompok**. Sumbu-X: #Test (1–5); Sumbu-Y: Standard Deviation (0–10). Angka eksak pada grafik belum termuat. | Menyertakan data lengkap per test:<br>• Test 1: [A2C: 9.02, PPO: 3.17, DQN: 6.42, MORL: 1.66]<br>• Test 2: [A2C: 6.71, PPO: 2.16, DQN: 3.21, MORL: 1.92]<br>• Test 3: [A2C: 4.89, PPO: 2.23, DQN: 2.45, MORL: 1.45]<br>• Test 4: [A2C: 6.46, PPO: 2.11, DQN: 2.46, MORL: 1.14]<br>• Test 5: [A2C: 5.35, PPO: 2.05, DQN: 2.01, MORL: 0.89]. Menautkan ke `fig_15.png`. |
| 16 | **Fig. 16** – Execution times (RL) | 18 | **ADA KESALAHAN** | **Satuan dan angka belum presisi:** Visual adalah diagram batang berkelompok. Sumbu-Y memiliki label satuan **"Execution Time [s]"** (detik, skala 0–30 s). Nilai per pengujian belum dirinci. | Menyertakan satuan `[s]` dan data per test:<br>• Test 1: [A2C: 9.71 s, PPO: 8.10 s, DQN: 9.22 s, MORL: 4.00 s]<br>• Test 2: [A2C: 14.52 s, PPO: 10.98 s, DQN: 14.19 s, MORL: 7.82 s]<br>• Test 3: [A2C: 19.34 s, PPO: 13.43 s, DQN: 19.34 s, MORL: 11.58 s]<br>• Test 4: [A2C: 23.77 s, PPO: 15.82 s, DQN: 24.16 s, MORL: 15.68 s]<br>• Test 5: [A2C: 28.54 s, PPO: 18.20 s, DQN: 28.93 s, MORL: 19.39 s]. Menautkan ke `fig_16.png`. |
| 17 | **Fig. 17** – Mean values of IEQ_Tot (NSGA-II) | 19 | **ADA KESALAHAN** | **Kurang data numerik eksak:** Visual membandingkan 2 algoritma: NSGA-II (hijau) vs MORL (ungu). Sumbu-Y: Mean Value of IEQ_Tot (595–620). Teks lama hanya menyebut rentang umum agregat. | Menyertakan data lengkap per test:<br>• Test 1: [NSGA-II: 610.24, MORL: 616.69]<br>• Test 2: [NSGA-II: 610.15, MORL: 617.91]<br>• Test 3: [NSGA-II: 612.55, MORL: 618.30]<br>• Test 4: [NSGA-II: 612.44, MORL: 618.57]<br>• Test 5: [NSGA-II: 612.00, MORL: 618.63]. Menautkan ke `fig_17.png`. |
| 18 | **Fig. 18** – Standard deviation of IEQ_Tot (NSGA-II) | 20 | **ADA KESALAHAN** | **Kurang data numerik eksak:** Visual adalah diagram batang berkelompok. Sumbu-Y: Standard Deviation (0–5). NSGA-II (hijau) vs MORL (ungu). Angka per test belum dicatat. | Menyertakan data lengkap per test:<br>• Test 1: [NSGA-II: 4.53, MORL: 1.66]<br>• Test 2: [NSGA-II: 3.87, MORL: 1.92]<br>• Test 3: [NSGA-II: 2.66, MORL: 1.45]<br>• Test 4: [NSGA-II: 3.12, MORL: 1.14]<br>• Test 5: [NSGA-II: 4.03, MORL: 0.89]. Menautkan ke `fig_18.png`. |
| 19 | **Fig. 19** – Execution times (NSGA-II) | 21 | **ADA KESALAHAN** | **Kesalahan interpretasi data angka:** Teks lama mencatat *"NSGA-II memerlukan waktu sekitar 105 detik"*, yang ternyata berasal dari narasi teks paragraf untuk kasus uji ekstrim 5000 generasi individual. Pada grafik Fig. 19 yang sebenarnya, Sumbu-Y berlabel **"Execution Time [s]"** (skala 0–22 s) dengan rentang waktu NSGA-II hanya **4.40 s – 20.52 s** dan MORL **4.00 s – 19.39 s**. | Menghapus narasi 105 s yang menyesatkan; menggantinya dengan nilai data batang visual yang benar:<br>• Test 1: [NSGA-II: 4.40 s, MORL: 4.00 s]<br>• Test 2: [NSGA-II: 8.52 s, MORL: 7.82 s]<br>• Test 3: [NSGA-II: 12.61 s, MORL: 11.58 s]<br>• Test 4: [NSGA-II: 16.37 s, MORL: 15.68 s]<br>• Test 5: [NSGA-II: 20.52 s, MORL: 19.39 s]. Menautkan ke `fig_19.png`. |

---

## 3. Tabel Verifikasi Kualitas 8 Rumus Kompleks

Verifikasi dilakukan dengan membandingkan teks rumus di Markdown hasil pipeline (`furniture_arrangement_ieq_2023_rag.md`) langsung dengan potongan gambar halaman asli PDF (`data/validation/eq_crops/` dan `original_page_*.png`).

Pengecekan mencakup simbol matematika, subscript/superscript, tanda operator perkalian/pembagian/eksponen, dan struktur tanda kurung.

| No | Persamaan | Halaman PDF | Status | Rumus dalam Markdown (LaTeX) | Hasil Pemeriksaan Simbol, Indeks & Operator vs PDF Asli |
| :---: | :--- | :---: | :---: | :--- | :--- |
| 1 | **Eq. (1)** – Single-agent Q-learning update | 3 | **SESUAI** | `$$Q(s, a) \leftarrow (1 - \alpha)Q(s, a) + \alpha \left[ R + \gamma \cdot \max_{a'} Q(s', a') \right]$$` | • Simbol panah assignment `\leftarrow` sesuai PDF.<br>• Koefisien pembobotan learning rate `(1 - \alpha)` dan `\alpha` sesuai.<br>• Tanda kurung siku `\left[ ... \right]` memuat reward $R$ dan faktor diskon `\gamma \cdot \max_{a'}` dengan operator perkalian titik.<br>• Indeks state-action berikut $s', a'$ tepat. |
| 2 | **Eq. (4)** – Multi-agent Q-learning update | 4 | **SESUAI** | `$$Q_i(s, a) \leftarrow (1 - \alpha)Q_i(s, a) + \alpha \left[ r_i + \gamma \cdot \max_{a'} Q_i(s', a') \right]$$` | • Subscript agen $i$ pada $Q_i$ konsisten.<br>• Reward komponen $r_i$ ditulis huruf kecil sesuai notasi PDF aslinya (berbeda dari reward skalar kapital $R$ pada Eq. 1).<br>• Operator dan tanda kurung siku sesuai. |
| 3 | **Eq. (7)** – Indoor acoustics SPL receiver | 5 | **SESUAI** | `$$L_{Receiver} = L_{Source} + 10\log(Q / (4\pi r^2) + 4 / Ac_R)$$` | • Subscript kata `Receiver` dan `Source` lengkap.<br>• Faktor pengali logaritma `10\log` tepat.<br>• Komponen suara langsung: directivity $Q$ dibagi `4\pi r^2` dengan simbol pi $\pi$ dan jarak kuadrat $r^2$.<br>• Komponen dengung: `4 / Ac_R` dengan konstanta penyerapan ruangan berindeks $R$. |
| 4 | **Eq. (8)** – Room acoustic constant ($Ac_R$) | 5 | **SESUAI** | `$$Ac_R = S \bar{\alpha}_{abs} / (1 - \bar{\alpha}_{abs})$$` | • Variabel luas permukaan total $S$ kapital.<br>• Koefisien serap rata-rata memakai overline `\bar{\alpha}` dan subscript `abs`.<br>• Penyebut `(1 - \bar{\alpha}_{abs})` dengan tanda kurang dan pembagian sesuai rumus Sabine/Eyring akustik di PDF. |
| 5 | **Eq. (11)** – Mean radiant temperature ($T_{mr}$) | 5 | **SESUAI** | `$$T_{mr} = T_1 F_{p-1} + T_2 F_{p-2} + \dots + T_n F_{p-n}$$` | • Subscript $T_{mr}$ tepat.<br>• Suku perkalian suhu permukaan $T_i$ dengan sudut pandang (view factor) $F_{p-i}$ memakai tanda hubung `p-1`, `p-2`, `p-n` tepat sesuai teks jurnal.<br>• Tanda elipsis `\dots` terdefinisi rapi. |
| 6 | **Eq. (16)** – Total IEQ reward function | 6 | **SESUAI** | `$$R_{IEQ} = p_{TC} * TC_{index} + p_{AC} * AC_{index} + p_{VC} * VC_{index}$$` | • Subscript indeks kenyamanan termal ($TC$), akustik ($AC$), dan visual ($VC$) konsisten.<br>• Koefisien bobot prioritas pengguna $p_{TC}, p_{AC}, p_{VC}$ tepat.<br>• Tanda operator perkalian dan penjumlahan linear sesuai PDF. |
| 7 | **Eq. (18)** – Predicted Percentage Dissatisfied ($PD_{TC}$) | 6 | **SESUAI** | `$$PD_{TC} = 100 - 95 \times e^{(-0.03353 PMV^4 - 0.2179 PMV^2)}$$` | • Subscript $PD_{TC}$ tepat.<br>• Konstanta 100 dan 95 dengan tanda minus tepat.<br>• Basis natural eksponen $e$.<br>• Eksponen PMV: koefisien desimal $-0.03353$ dengan pangkat 4 ($PMV^4$) dan $-0.2179$ dengan pangkat 2 ($PMV^2$). Tanda negatif pada kedua suku akurat. |
| 8 | **Eq. (24)** – Evaluasi IEQ Total untuk dua pengguna | 16 | **SESUAI** | `$$IEQ_{Tot} = R_{user_1} + R_{user_2} + R_{dist-users}$$` | • Subscript $Tot$ pada $IEQ_{Tot}$ tepat.<br>• Notasi reward individual $R_{user_1}$ dan $R_{user_2}$ tepat.<br>• Komponen penalti jarak antar meja $R_{dist-users}$ dengan tanda hubung sesuai teks jurnal. |

---

## 4. Item yang Perlu Dicek Manual oleh Pengguna

Meskipun seluruh 19 figure dan 8 rumus utama telah diverifikasi secara visual dan otomatis, berikut adalah poin pertimbangan khusus yang disarankan untuk ditinjau oleh pengguna:

1. **Gaya Notasi Persamaan (Eq. 7 & Eq. 8):**
   - Di Markdown saat ini, pembagian ditulis dalam bentuk baris datar: `10\log(Q / (4\pi r^2) + 4 / Ac_R)` dan `S \bar{\alpha}_{abs} / (1 - \bar{\alpha}_{abs})`.
   - Bentuk ini sangat aman untuk rendering RAG dan parser LLM. Jika pengguna menghendaki representasi bertingkat LaTeX standar (`\frac{...}{...}`), bentuk ini dapat diubah menjadi `10\log\left(\frac{Q}{4\pi r^2} + \frac{4}{Ac_R}\right)` dan `\frac{S \bar{\alpha}_{abs}}{1 - \bar{\alpha}_{abs}}`. Keduanya valid secara matematis.
2. **Kesesuaian Satuan Suhu pada Eq. 11:**
   - Dalam jurnal, $T_{mr}$ dan $T_n$ dihitung dalam derajat Celcius (°C) atau Kelvin (K) bergantung pada metode linearisasi Fanger. Dalam teks RAG telah disertakan konteks bahwa suhu permukaan ruangan diuji pada setpoint 23°C.
3. **Penggunaan File Aset Gambar:**
   - Direktori `data/processed/assets/furniture_arrangement_ieq_2023/` kini memiliki aset gambar tunggal yang rapi (`fig_01.png` s/d `fig_19.png`). Semua gambar ini beresolusi tinggi dan siap dipakai langsung oleh agentic AI untuk referensi visual.

---

## 5. Ringkasan Pipeline Downstream

Setelah seluruh perbaikan deskripsi visual diterapkan:
- **`scripts/describe_figures.py`**: Berhasil menyimpan 19 entri deskripsi valid ke `data/processed/assets/figure_descriptions.json` dan menautkan setiap entri ke aset `fig_01.png` – `fig_19.png`.
- **`prepare_rag_markdown.py`**: Berhasil menyisipkan ke-19 deskripsi gambar serta merapikan 19 tabel Markdown pipe dan mempertahankan 24 rumus LaTeX ke `furniture_arrangement_ieq_2023_rag.md` (ukuran: 84.0 KB).
- **`chunk_markdown.py`**: Berhasil membagi teks ke dalam **43 chunks** di `furniture_arrangement_ieq_2023_chunks.jsonl` tanpa memotong tabel, rumus, atau deskripsi gambar (0 tabel terpotong, 0 rumus terpotong, 0 gambar terpotong).
