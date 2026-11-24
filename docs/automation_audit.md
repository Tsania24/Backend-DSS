# Audit Otomatisasi Pipeline Knowledge Base & RAG (Tahap 5A)

Dokumen ini memuat inventarisasi lengkap seluruh modul, fungsi, skrip, dan konstanta dalam pipeline penyiapan dokumen, chunking, embedding, serta DSS Agent yang saat ini masih memiliki logika spesifik (*hardcoded*) untuk paper:
> **"A multi-objective reinforcement learning approach for furniture arrangement with optimal IEQ in multi-occupant offices"** (Ribino & Bonomolo, 2023).

---

## 1. Tabel Ringkasan Inventarisasi Komponen Khusus Paper

| No | File | Fungsi / Komponen | Mengapa Khusus Paper Ini | Solusi / Aturan Umum Pengganti | Kategori Status |
|:---:|:---|:---|:---|:---|:---:|
| 1 | `prepare_rag_markdown.py` | `fix_section_6_placement()` | Menyatukan 3 fragmen paragraf pembuka Section 6 yang dipecah oleh LlamaParse di antara Fig. 8–13. | Deteksi heading berurutan (`5.1 -> 6 -> 6.1`) dan penyatuan fragmen kalimat terpotong (tanpa tanda titik) secara sintaksis/AST dokumen. | **Butuh Review Manual** |
| 2 | `prepare_rag_markdown.py` | `fix_section_6_2_and_7_placement()` | Memindahkan Fig. 19 & tabel perbandingan dari awal Section 7 Conclusions kembali ke Section 6.2, lalu menyatukan Section 7. | Asosiasi posisi gambar/tabel berdasarkan referensi sitasi pertama dalam teks (`(Fig. 19)`) atau batas hierarki heading utama. | **Butuh Review Manual** |
| 3 | `prepare_rag_markdown.py` | `process_all_tables()` (Hapus Tabel Fig. 8–13) | Menghapus tabel HTML mentah 20 pengujian pada indeks tabel (5, 6, 7) karena bising dan sudah diwakili grafik. | Heuristik tabel: deteksi tabel berulang multi-run yang berkorelasi dengan bar chart, atau filter berbasis densitas token. | Aturan Umum |
| 4 | `prepare_rag_markdown.py` | `process_all_tables()` (Label Table 4, 5, 11) | Memberi caption manual untuk Table 4, Table 5, dan Table 11 yang hilang/tergabung pada ekstraksi LlamaParse. | Ekstraksi caption tabel generik berbasis pencarian pola `Table\s+\d+.*` dalam radius 1–3 baris sebelum/sesudah tag `<table>`. | Aturan Umum |
| 5 | `prepare_rag_markdown.py` | Injeksi `ILLUMINANCE_TABLE_1` & `ILLUMINANCE_TABLE_2` | Menimpa tabel HTML matriks pencahayaan 8×8 dan 10×8 yang diekstrak rusak oleh OCR dengan tabel terstruktur rapi. | Parsing matriks grid numerik 2D dari denah gambar menggunakan model VLM atau ekstraktor tabel spasial berbasis koordinat PDF. | **Butuh Review Manual** |
| 6 | `prepare_rag_markdown.py` | Pembersihan Artefak Soliter `\n3\n` | Menghapus angka '3' soliter sebelum Fig. 17 yang disisipkan salah oleh parser OCR. | Aturan regex generik untuk menghapus baris soliter berupa digit tunggal di antara blok teks. | Aturan Umum |
| 7 | `prepare_rag_markdown.py` | `split_and_convert_html_table()` | Deteksi split tabel eksperimen berbasis baris reset `first_cell == "1"` setelah `20` atau `5` test, dan baris artefak `21`. | Algoritma pemecahan tabel generik berbasis deteksi reset urutan numerik (monotonik naik kembali ke 1) pada kolom indeks. | Aturan Umum |
| 8 | `prepare_rag_markdown.py` | `FIGURE_MAPPINGS` (19 Triggers) | Hardcoding 19 trigger regex (`Fig. 1` s.d. `Fig. 19`) yang dipetakan ke key cache spesifik (`page_X_figY`). | Ekstraksi dinamis semua tag gambar `![caption](path)` dan pencocokan pola `Fig(ure)?\.?\s*(\d+)` secara otomatis. | Aturan Umum |
| 9 | `chunk_markdown.py` | `CHUNK_PAGE_MAP` (40 Chunks) | Mapping statis eksplisit dari `chunk_000` s.d. `chunk_039` ke tuple `(primary_page, [page_numbers])`. | Algoritma n-gram / fuzzy text matching antara konten chunk dengan teks per halaman pada `PAGE_INDEX` LlamaParse JSON. | Aturan Umum |
| 10 | `chunk_markdown.py` | `SECTION_PAGE_MAP` | Mapping statis nama bagian spesifik paper Ribino ke nomor halaman fallback (1–21). | Fallback dinamis berbasis nomor halaman awal dari item heading pertama yang ditemukan di JSON parser. | Aturan Umum |
| 11 | `chunk_markdown.py` | `ASSET_PAGE_MAP` | Mapping statis nama file aset gambar (`fig_01.png` s.d. `fig_19.png`) ke nomor halaman PDF. | Penyimpanan metadata `page_number` langsung pada objek aset saat proses ekstraksi gambar dari PDF berlangsung. | Aturan Umum |
| 12 | `chunk_markdown.py` | Konstanta Dokumen Statis | `DOCUMENT_SOURCE`, `DOCUMENT_TITLE`, dan path input/output file chunk di-hardcode ke paper 2023. | Parameterisasi via CLI arguments (`--input`, `--doc-title`, `--source-pdf`) atau file konfigurasi job ingestion (`config.yaml`). | Aturan Umum |
| 13 | `scripts/describe_figures.py` | `KNOWN_FIGURE_CONTEXT` & `ADDITIONAL_FIGURES` | Bounding box koordinat PDF, prompt khusus, dan konteks manual per figur untuk menghasilkan deskripsi grafik. | Pipeline VLM terotomatisasi (mis. Gemini Flash / GPT-4o) dengan prompt standar ekstraksi visual (sumbu, nilai, tren). | **Butuh Review Manual** |
| 14 | `clean_markdown.py` | `ARTIFACT_PATTERNS` (Header/Footer Jurnal) | Regex spesifik nama jurnal Springer (*Journal of Ambient Intelligence*), nama penulis (*P. Ribino, M. Bonomolo*), dan afiliasi (*ICAR-CNR*). | Algoritma pembersih running header/footer berbasis teks berulang di margin atas/bawah tiap halaman pada level JSON/PDF. | Aturan Umum |
| 15 | `clean_markdown.py` | `REPLACEMENTS` (Floating Table Breaks) | Menggabungkan teks spesifik yang terpotong oleh floating table Fig. 1 (*"into the direction of the best-scalarized action"*) dan Fig. 2. | Heuristik deteksi kalimat menggantung sebelum blok `<table>`/gambar (tanpa tanda baca akhir) yang dilanjutkan di bawahnya. | Aturan Umum |
| 16 | `clean_markdown.py` | `normalize_heading_level()` | Deteksi judul paper spesifik melalui substring *"multi-objective reinforcement learning approach for furniture"*. | Ekstraksi judul dokumen generik dari metadata PDF atau baris heading pertama berukuran font terbesar sebelum bagian Abstract. | Aturan Umum |
| 17 | `scripts/embed_chunks.py` | `CHUNKS_FILE` & Fallback `doc_source` | Path file chunks dan nama dokumen default di-hardcode ke file paper Ribino. | Menggunakan argumen CLI `--input` dan membaca field `source` serta `document_title` dari tiap baris file JSONL. | Aturan Umum |
| 18 | `server.py` | `DEFAULT_ROOM_CONTEXT` | Konteks geometri Office #1 (4,5×3,5 m) dan Office #2 (14,75 m²) di-hardcode di server DSS. | Parameterisasi dinamis: konteks ruangan dikirim oleh klien Unity Mixed Reality melalui payload sesi atau tabel database `room_configs`. | Aturan Umum |
| 19 | `server.py` | `system_prompt` (Contoh Query & Paper Rules) | Contoh pencarian (`"Bellman equation"`, `"Table 1 data synthesis"`) dan aturan komparasi Office #1 vs Office #2. | Meta-prompt generik yang memisahkan aturan integritas RAG universal dari variabel injeksi konteks paper aktif. | Aturan Umum |

---

## 2. Analisis Detail per Modul

### 2.1. `prepare_rag_markdown.py`

#### A. Restrukturisasi Section 6 (`fix_section_6_placement`)
- **Implementasi Saat Ini:** Fungsi ini mencari 3 string teks persis (`frag1_target`, `frag2_target`, `frag3_target`) yang tersebar di halaman 11, 12, dan 13 di antara Fig. 8–13, menghapusnya dari posisi aslinya, lalu merekonstruksinya menjadi satu paragraf utuh di bawah heading `## 6 Algorithm comparison`.
- **Mengapa Khusus Paper Ini:** Masalah ini timbul akibat karakteristik layout 2-kolom Springer di mana LlamaParse salah memprioritaskan aliran membaca tabel/gambar floating sebelum paragraf teks selesai.
- **Solusi Aturan Umum:**
  - Parsing dokumen ke dalam format AST (*Abstract Syntax Tree*).
  - Jika sebuah heading (mis. `## 6`) muncul sebelum seluruh elemen subsection sebelumnya selesai (masih ada referensi Fig. 8–13 dari Section 5.1), tunda penempatan heading tersebut.
  - Gabungkan paragraf yang terputus dengan memeriksa apakah kalimat berakhir dengan tanda titik/tanda baca terminal. Jika berakhir dengan preposisi atau kata sambung, gabungkan dengan paragraf teks berikutnya.
- **Klasifikasi:** **Butuh Review Manual** (karena penataan layout 2-kolom sangat bervariasi antar penerbit ilmiah).

#### B. Relokasi Fig. 19 dan Rekonstruksi Section 7 (`fix_section_6_2_and_7_placement`)
- **Implementasi Saat Ini:** String hardcoded `start_frag` dan `end_frag` digunakan untuk memotong tabel Fig. 19 dari dalam `## 7 Conclusions` dan memindahkannya ke akhir Section 6.2.
- **Mengapa Khusus Paper Ini:** Fig. 19 secara visual terletak di halaman 20 dekat judul Conclusions, sehingga LlamaParse salah mengelompokkannya ke dalam Section 7.
- **Solusi Aturan Umum:**
  - Posisikan setiap gambar dan tabel Markdown di bawah sub-bagian (*heading path*) tempat elemen tersebut pertama kali disitir/disebut di dalam teks narasi (mis. teks *"as shown in Fig. 19"* berada di Section 6.2).
- **Klasifikasi:** **Butuh Review Manual**.

#### C. Pembersihan dan Penanganan Tabel (`process_all_tables`)
- **Penghapusan Tabel Fig. 8–13:** Hardcoded indeks `idx in (5, 6, 7)`. Pada paper ini, tabel hasil 20 pengujian dihilangkan karena redundan dengan grafik vision.
  - *Aturan umum:* Deteksi tabel yang memiliki kolom berulang (mis. 20 iterasi) tanpa agregasi statistik, atau sediakan flag konfigurasi `--drop-raw-run-tables`.
- **Penamaan Table 4, 5, dan 11:** Indeks `idx == 3`, `idx == 4`, `idx == 10`.
  - *Aturan umum:* Cari baris teks terdekat yang cocok dengan pola regex `^(?:Table\|Tabel)\s+(\d+)\b[:\.\s—-]*(.*)$` dan gunakan string tersebut sebagai heading tabel Markdown pipe.
- **Injeksi Matriks Iluminansi (`ILLUMINANCE_TABLE_1` & `ILLUMINANCE_TABLE_2`):**
  - *Mengapa:* Matriks denah sel ruangan berukuran 8×8 dan 10×8 diekstrak hancur oleh OCR.
  - *Aturan umum:* **Butuh Review Manual** jika dokumen memuat data spasial berbasis koordinat sel/grid. Untuk dokumen teks biasa, parser tabel standar sudah mencukupi.

---

### 2.2. `chunk_markdown.py`

#### A. Pemetaan Halaman Statis (`CHUNK_PAGE_MAP`)
- **Implementasi Saat Ini:** Kamus kamus statis 40 entri:
  ```python
  CHUNK_PAGE_MAP = {
      "chunk_000": (1, [1]),
      "chunk_001": (1, [1, 2]),
      ...,
      "chunk_038": (21, [20, 21]),
      "chunk_039": (20, [20, 21]),
  }
  ```
- **Mengapa Khusus Paper Ini:** Dibuat secara manual agar evaluasi sitasi halaman LLM pada Tahap 4 memiliki *ground truth* 100% presisi sesuai halaman fisik PDF 22 halaman.
- **Solusi Aturan Umum:**
  - `chunk_markdown.py` sebenarnya telah memiliki implementasi `PAGE_INDEX` berbasis teks JSON LlamaParse.
  - Aturan umum: Ambil 5 kata pertama dan 5 kata terakhir dari setiap chunk, cari kemunculannya pada `PAGE_INDEX[pno]`, dan tetapkan `page_numbers` secara dinamis. Bila chunk membentang melewati batas halaman, sertakan seluruh halaman yang terdeteksi.

#### B. Fallback Section dan Asset Map (`SECTION_PAGE_MAP` & `ASSET_PAGE_MAP`)
- **Implementasi Saat Ini:** Dictionary yang memetakan string judul bagian (`"3.1 indoor comfort conditions": 3`) dan file gambar (`"fig_01.png": 8`).
- **Solusi Aturan Umum:**
  - Untuk heading: simpan `page_number` saat parser pertama kali menemukan baris heading tersebut.
  - Untuk gambar: simpan atribut `page` dari bounding box saat gambar diekstrak dari PDF menggunakan PyMuPDF (`fitz`).

---

### 2.3. `scripts/describe_figures.py`

#### Bounding Box dan Konteks Manual (`KNOWN_FIGURE_CONTEXT` & `ADDITIONAL_FIGURES`)
- **Implementasi Saat Ini:** Berisi 700+ baris kode dengan koordinat piksel eksplisit per figur (`bbox = [ymin, xmin, ymax, xmax]`), prompt khusus, dan teks fallback per diagram (Fig. 1–19).
- **Mengapa Khusus Paper Ini:** LlamaCloud OCR awal mengekstrak diagram batang tanpa angka sumbu dan tanpa nilai numerik per pengujian.
- **Solusi Aturan Umum:**
  - Pipeline pemrosesan gambar otomatis:
    1. Ekstraksi otomatis seluruh elemen gambar dari PDF menggunakan `page.get_images()` PyMuPDF.
    2. Kirim gambar ke model Vision Language Model (VLM) seperti Gemini 1.5 Flash / GPT-4o dengan prompt baku:
       > *"Deskripsikan tipe visual (diagram batang/denah/kurva), label sumbu X dan Y beserta satuannya, legenda, nilai data eksak (termasuk nilai minimum, maksimum, rata-rata jika tercetak), serta kesimpulan utama gambar ini."*
    3. Simpan output ke cache JSON terstruktur otomatis: `data/processed/assets/{doc_id}_figures.json`.
- **Klasifikasi:** **Butuh Review Manual** untuk verifikasi angka tabel vs pembacaan visual grafik.

---

### 2.4. `clean_markdown.py` / `scripts/rebuild_markdown.py`

#### A. Pola Artefak Penerbit (`ARTIFACT_PATTERNS`)
- **Implementasi Saat Ini:** Regex yang menargetkan string spesifik jurnal Springer, nama penulis *Patrizia Ribino* dan *Marina Bonomolo*, serta afiliasi *Istituto di Calcolo*.
- **Solusi Aturan Umum:**
  - Mengganti regex spesifik penulis dengan filter generik:
    - Running headers/footers: teks yang identik berulang pada posisi yang sama di >50% halaman dokumen.
    - Pola metadata publikasi umum: ISSN, ISBN, DOI (`10\.\d{4,9}/[-._;()/:A-Z0-9]+`), baris hak cipta (`©\s*\d{4}`), email (`[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}`), dan penanda footnote numerik di awal baris.

#### B. Rekoneksi Kalimat Terpotong (`REPLACEMENTS`)
- **Implementasi Saat Ini:** Penggantian regex untuk menyambung kalimat spesifik yang terpotong oleh tag `<table>` Fig. 1 dan Fig. 2.
- **Solusi Aturan Umum:**
  - Buat algoritma pra-pemrosesan: jika sebuah blok tabel/gambar berada tepat di antara kalimat yang tidak diakhiri tanda baca penutup (`.`, `?`, `!`, `:`) dan baris berikutnya diawali dengan huruf kecil, pindahkan blok tabel/gambar tersebut ke akhir paragraf terkait.

---

### 2.5. `server.py` & Konfigurasi DSS

#### A. Konteks Ruangan Statis (`DEFAULT_ROOM_CONTEXT`)
- **Implementasi Saat Ini:** Konteks fisik ruangan Office #1 dan Office #2 diisi statis di dalam dictionary Python.
- **Solusi Aturan Umum:**
  - Konteks ruangan harus bersifat dinamis. Saat pengguna menggunakan headset Unity Mixed Reality / Web frontend, sistem mengirimkan geometri ruangan aktual yang sedang aktif melalui endpoint sesi `/api/room/context` atau diambil dari tabel database `room_profiles`.

#### B. Aturan Retrieval Prompt DSS
- **Implementasi Saat Ini:** Contoh pencarian menyebutkan `"Bellman equation"`, `"Table 1 data synthesis"`, serta larangan halusinasi spesifik untuk Office #1 vs Office #2.
- **Solusi Aturan Umum:**
  - Pisahkan prompt menjadi **Core DSS System Prompt** (bersifat invarian untuk semua dokumen teknik) dan **Document-Specific System Context** yang diinjeksikan secara modular berdasarkan dokumen yang sedang dimuat ke dalam Knowledge Base.

---

## 3. Matriks Keputusan Transisi ke Pipeline Generik (Tahap 5B)

| Komponen | Status Saat Ini | Rencana Tahap 5B | Tingkat Kompleksitas |
|:---|:---:|:---|:---:|
| **Pembersihan Header/Footer** | Spesifik Springer & Ribino | Generik (Deteksi running header berulang & DOI) | Rendah |
| **Penyambungan Kalimat Floating Table** | Hardcoded teks | Generik (Deteksi kalimat belum berujung tanda baca) | Sedang |
| **Normalisasi Judul & Heading** | Hardcoded string judul | Generik (Heading font terbesar sebelum Abstract) | Rendah |
| **Pemecahan Tabel Multi-Run** | Split pada baris 20 dan 5 | Generik (Deteksi siklus reset indeks kolom pertama) | Sedang |
| **Penataan Section Floating (Section 6 & 7)** | Hardcoded string fragmen | **Butuh Review Manual** / Heuristik AST | Tinggi |
| **Deskripsi Visual Gambar & Grafik** | Konteks manual Fig. 1–19 | Pipeline VLM terotomatisasi + Cache per dokumen | Sedang |
| **Pemetaan Halaman Chunk** | `CHUNK_PAGE_MAP` statis | Generik (Fuzzy text n-gram matching ke LlamaParse JSON) | Rendah |
| **Konteks Ruangan DSS** | Hardcoded Office #1 & #2 | Parameter dinamis via API sesi Unity/database | Rendah |
