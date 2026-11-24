# Rancangan Otomatisasi Pipeline Ingestion Dokumen Ilmiah

Dokumen ini adalah spesifikasi desain teknis untuk menjadikan pipeline pemrosesan dokumen ilmiah **generik, multi-dokumen, dapat diulang** untuk banyak jurnal â€” menggantikan implementasi ad-hoc yang hardcoded untuk satu paper.

> [!NOTE] Batasan Ruang Lingkup
> `server.py` (konteks ruangan MR, katalog 3D, antrean SSE Unity, system prompt DSS) **dipisahkan tegas** dari pipeline dokumen. Itu bagian integrasi aplikasi Unity dan **tidak termasuk** dalam Tahap 5.

> [!CAUTION] Migrasi 005
> SQL migrasi 005 (di bawah) **BELUM BOLEH dijalankan** sampai setelah sidang. Pre-kondisi: `embed_chunks.py`, `eval/run_eval.py`, dan `mcp_server.py` (get_chunk) harus sudah mendukung prefixed chunk_id sebelum 005 dijalankan.

---

## VERSI 1 â€” Pipeline Sederhana (Target 2â€“4 Hari Kerja)

### V1.1. Antarmuka CLI

Satu perintah per jurnal; tidak ada `config.yaml` yang wajib ada di V1:

```bash
python ingest.py <pdf> --slug <nama>
# Contoh untuk paper baru:
python ingest.py data/raw/paper2.pdf --slug smart_building_sensor_2024
```

Langkah dijalankan berurutan secara otomatis: **parse â†’ clean â†’ figures â†’ chunk â†’ embed**. Setiap langkah dapat dijalankan ulang secara idempoten (tidak menyisakan baris duplikat di Supabase).

Opsi tambahan:
```bash
python ingest.py <pdf> --slug <nama> --step figures   # jalankan satu langkah saja
python ingest.py <pdf> --slug <nama> --dry-run        # validasi tanpa tulis ke Supabase
python ingest.py <pdf> --slug <nama> --force          # paksa ulang meski hash identik
```

> [!IMPORTANT] Kebijakan Paper Pertama (Paper 1)
> **Paper pertama JANGAN diproses ulang oleh V1.** Data 40 chunk paper pertama yang saat ini berada di Supabase dan berstatus terverifikasi dipertahankan sepenuhnya. Paper pertama hanya didaftarkan/di-backfill slug-nya melalui migrasi 005 pasca-sidang. Pipeline V1 diuji langsung pada **dua paper baru** (Paper 2 & Paper 3).

### V1.2. Langkah Pipeline

| # | Langkah | Modul | Keterangan |
|---|---------|-------|------------|
| 1 | **Parse** | `core/parser.py` | LlamaParse â†’ JSON struktural; nomor halaman diambil dari JSON parser, **bukan** n-gram teks |
| 2 | **Clean** | `core/cleaner.py` | Hapus baris header/footer berulang (generic, bukan publisher-specific); normalisasi heading |
| 3 | **Figures** | `core/figures.py` | Ekstrak gambar dari PDF, kirim ke VLM, cache deskripsi |
| 4 | **Chunk** | `core/chunker.py` | Chunk per heading; tabel dan rumus tidak dipotong; chunk_id = `{slug}:chunk_{n:03d}`. **Wajib memakai ulang fungsi chunking yang sudah ada** |
| 5 | **Embed** | `core/embedder.py` | Embed dengan `qwen3-embedding:0.6b`; upsert ke Supabase |
| 6 | **Report** | `core/reporter.py` | Hasilkan `quality_report.md` otomatis |

### V1.3. Struktur Direktori Output per Dokumen

```text
data/<doc_slug>/
â”œâ”€â”€ raw/           # PDF asli
â”œâ”€â”€ parsed/        # JSON + markdown mentah dari LlamaParse
â”œâ”€â”€ markdown/      # Teks bersih + teks final dengan injeksi deskripsi gambar
â”œâ”€â”€ assets/        # fig_01.png ... + figure_descriptions.json (cache VLM)
â”œâ”€â”€ chunks/        # <doc_slug>_chunks.jsonl
â””â”€â”€ reports/       # validation_log.json + quality_report.md
```

### V1.4. Deteksi Tabel Palsu (Pengganti Daftar Drop Hardcoded)

**Aturan generik:** Tabel HTML/markdown yang berada dalam konteks gambar â€” yaitu tidak ada caption `Table N` dalam radius N baris sebelumnya AND berada di dalam blok figure atau segera setelah caption figure â€” ditandai `needs_review: true` dan **tidak dimasukkan** sebagai chunk data tabel.

**Cara menguji:** Jalankan heuristik pada data parsed paper 1; hasilnya harus mendeteksi otomatis **6 tabel palsu** (dari Fig. 8â€“13) tanpa daftar drop eksplisit. Indikator gagal: salah satu dari 6 tabel itu lolos ke `chunks/` sebagai chunk tipe `table`, atau tabel data valid (Table 1â€“5) ikut terdrop.

**Risiko:** Heuristik ini berpotensi false positive jika caption tabel legitimate tidak mengikuti pola `Table N`. Kasus ambigu dicatat ke `validation_log.json` dengan flag `needs_review`, bukan ditolak diam-diam.

### V1.5. Konfigurasi VLM & Penyimpanan Kredensial

Satu blok konfigurasi di `ingest.py` (atau `.env`), mendukung dua provider:

```python
VLM_CONFIG = {
    "provider": "9router",          # "9router" | "gemini_api"
    "model": "cx/gpt-6-luna[1m]",   # untuk 9router
    "base_url": "http://localhost:20128/v1",
    "api_key_env": "NINEROUTER_API_KEY",   # baca dari env
    # Untuk gemini_api:
    # "model": "gemini-2.0-flash",   # [BELUM DIVERIFIKASI]
    # "base_url": None,
    # "api_key_env": "GEMINI_API_KEY",
    "prompt_version": "v1.0",       # dipakai untuk cache-key hash
    "cache_enabled": True,          # skip VLM jika cache hit
}
```

#### Penyimpanan Kredensial 9router
- **Lokasi Fisik Key:** Kredensial 9router tersimpan secara lokal pada database SQLite di `/home/advance/.9router/db/data.sqlite` pada tabel `apiKeys` (kolom `key`).
- **Nama Variabel Lingkungan:** `NINEROUTER_API_KEY`, didefinisikan pada file `/home/advance/backend-dss/.env`.

#### Verifikasi Model Gemini & Biaya `[BELUM DIVERIFIKASI]`
- Nama model Gemini (mis. `gemini-2.0-flash` atau `gemini-1.5-flash`) dan perkiraan biaya (~$0.0003/gambar) berstatus **`[BELUM DIVERIFIKASI]`**.
- **Cara Memverifikasi:**
  1. Pasang key ke `.env`: `echo "GEMINI_API_KEY=<your-key>" >> /home/advance/backend-dss/.env`.
  2. Periksa model aktif yang mendukung vision via cURL:
     ```bash
     curl -s "https://generativelanguage.googleapis.com/v1beta/models?key=${GEMINI_API_KEY}" | grep -E 'name|supportedGenerationMethods'
     ```
  3. Cek tier akun dan batasan kuota (RPM/RPD serta pricing per 1M tokens) pada Google AI Studio Console resmi.

**Aturan VLM (diterapkan via prompt):**
- Grafik batang tanpa label angka â†’ gunakan kata `"sekitar"`, **jangan** membuat tabel data tiruan.
- Angka yang tidak tercetak sebagai label â†’ gunakan `"sekitar"`, **jangan** sertakan desimal semu.
- Jika semua provider gagal â†’ tandai figure `needs_review: true` dan **lanjutkan ingestion** (jangan hentikan pipeline).

**Cache:** Key = `sha256(image_bytes) + ":" + prompt_version`. Hasil tersimpan di `assets/figure_descriptions.json`. Jalankan ulang dengan flag `--force` untuk paksa refresh.

### V1.6. Pemakaian Ulang Logika Chunker (`core/chunker.py`)

Untuk mencegah regresi logika pemotongan dokumen, modul `core/chunker.py` **WAJIB memakai ulang fungsi yang sudah teruji** pada `chunk_markdown.py`, bukan menulis ulang dari nol:
1. **`overlap_tail(text: str)`:** Menghitung sliding window overlap karakter antar-chunk untuk kesinambungan semantik kalimat perbatasan.
2. **`determine_content_type(...)`:** Mengklasifikasikan tipe chunk (`narrative`, `table`, `formula`, `figure`) dan menentukan boolean flags (`has_table`, `has_latex`, `has_figure_description`).
3. **Logika Pengikatan Judul Tabel (*Table Caption Binding*):** Memastikan judul/caption tabel diikat menjadi satu kesatuan blok dengan tabel datanya agar tidak terpotong ke chunk berbeda.

Format Chunk ID: **`<slug>:chunk_{n:03d}`** (contoh: `smart_building_sensor_2024:chunk_005`).

> [!NOTE] Catatan Kasus Q11 & Q25 (Fig. 19)
> Pada paper pertama, akurasi Q11 dan Q25 bergantung pada penempatan figur Fig. 19 yang dilakukan secara spesifik oleh fungsi `fix_section_6_placement` (mengatasi bug LlamaParse yang menempatkan floating figure di akhir dokumen). Fitur relokasi otomatis ini masuk dalam cakupan **V2 (Auto Figure Relocation)**. Pada V1, figur diletakkan sesuai posisi asli ekstraksi parser; jika figur floating terjadi pada paper baru, fenomena ini dicatat pada `quality_report.md` sebagai temuan parser.

### V1.7. Pemetaan Halaman & Kriteria Akurasi

| Tipe Chunk | Sumber Nomor Halaman | Catatan |
|------------|----------------------|---------|
| **Figure / Tabel** | Atribut halaman aset dari JSON LlamaParse atau bounding-box PyMuPDF | Bukan n-gram teks deskripsi VLM |
| **Teks narasi** | Anchor minimal **8 kata unik** dari teks PDF | Jika ambigu (muncul >1 halaman): cari anchor alternatif; jika tetap ambigu â†’ flag `page_mapping_ambiguous: true` di validation_log, jangan ditebak |

**Kriteria Akurasi Pemetaan Halaman:**
- Algoritma pemetaan baru diuji terhadap data ground truth 40 chunk paper pertama (`CHUNK_PAGE_MAP`).
- **Target Akurasi: $\ge \mathbf{97.5\%}$ cocok** (minimal 39 dari 40 chunk memiliki kesesuaian nomor halaman primer atau rentang halaman terverifikasi).

### V1.8. Penambahan Parameter `source` pada `mcp_server.py` (Masuk V1)

Untuk memenuhi kriteria lulus multi-dokumen (isolasi pencarian per paper), parameter pemfilteran `source` dimasukkan langsung ke **Versi 1**:

#### Penjelasan Perubahan Kecil pada `mcp_server.py`:
Fungsi Supabase RPC `match_knowledge_chunks_hybrid` (hasil migrasi 004) **sudah mendukung** parameter `p_filter_source text DEFAULT NULL`. Saat ini di `mcp_server.py`, nilai tersebut di-hardcode: `"p_filter_source": None`.

Perubahan yang dilakukan di V1 sangat minimal:
1. Tambahkan parameter opsional `source: str | None = None` pada tanda tangan fungsi `search_documents`:
   ```python
   @mcp.tool()
   def search_documents(
       query: str,
       top_k: int = 5,
       content_type: str | None = None,
       page: int | None = None,
       source: str | None = None   # <-- Ditambahkan di V1
   ) -> dict:
   ```
2. Teruskan parameter tersebut ke `rpc_params`:
   ```python
   "p_filter_source": source.strip() if source and source.strip() else None,
   ```
3. Update docstring tool agar agen mengetahui bahwa ia dapat memfilter pencarian ke dokumen tertentu (mis. `source="furniture_arrangement_ieq_2023.pdf"`).
*Tidak ada perubahan skema database atau migrasi SQL yang diperlukan untuk fitur ini.*

### V1.9. Quality Report

File output: `data/<doc_slug>/reports/quality_report.md`

Isi laporan otomatis:
- Rumus yang gagal parse (LaTeX/MathML tidak valid)
- Figure dengan status `needs_review: true` (VLM gagal atau angka tak tercetak dipertanyakan)
- Chunk yang mencakup >3 halaman (potensi chunking terlalu besar)
- Tabel tanpa caption `Table N` yang terdeteksi (calon tabel palsu)
- Section yang hasilnya kosong setelah cleaning
- Akurasi pemetaan halaman dan daftar anchor teks ambigu

### V1.10. File yang Dibuat / Dimodifikasi

| File | Status | Keterangan |
|------|--------|------------|
| `ingest.py` | **Baru** | CLI orkestrator pipeline |
| `core/parser.py` | **Baru** | Wrapper LlamaParse |
| `core/cleaner.py` | **Baru** | Pembersih header/footer generic |
| `core/figures.py` | **Baru** | Ekstraksi visual, VLM & cache |
| `core/chunker.py` | **Baru** | Chunker (reuse fungsi `chunk_markdown.py`) + slug prefix |
| `core/embedder.py` | **Baru** | Reuse logika upsert dari `embed_chunks.py` |
| `core/reporter.py` | **Baru** | Quality report generator |
| `mcp_server.py` | **Modifikasi kecil** | Tambah parameter `source` pada `search_documents` |
| `embed_chunks.py` | Dipertahankan as-is | Tidak disentuh |
| `server.py` | **Tidak disentuh** | Di luar scope pipeline |

### V1.11. Risiko dan Mitigasi

| Risiko | Dampak | Mitigasi |
|--------|--------|----------|
| Heuristik tabel palsu menghasilkan false positive | Tabel data valid terdrop | Log ke `needs_review`; verifikasi manual via `quality_report.md` |
| Nomor halaman LlamaParse drift pada layout kompleks | Sitasi halaman salah | Validasi anchor 8-kata terhadap indeks halaman; capai target $\ge 97.5\%$ |
| 9router quota habis saat ingestion batch | Pipeline berhenti di langkah figures | Fallback ke `needs_review: true`; lanjutkan langkah berikutnya |
| Anchor 8-kata tidak unik | `page_mapping_ambiguous: true` terlalu banyak | Audit laporan; perluas window anchor jika perlu |

### V1.12. Kriteria Kelulusan Tahap 5C.7

1. **Paper 1 baseline tidak regresi:** Evaluasi Mode 1 pada 24 pertanyaan in-domain tidak boleh turun dari baseline (Hit@5 $\ge 95.83\%$, MRR $\ge 0.7236$), diuji setelah paper baru masuk ke Supabase (baik dengan filter `source` maupun tanpa filter).
2. **Paper baru berhasil diingesti:** Dua paper baru (Paper 2 & Paper 3) berhasil diproses dari PDF hingga Supabase; **setiap perubahan pada `core/` dicatat sebagai temuan, bukan kegagalan**.
3. **Akurasi Pemetaan Halaman:** $\ge 97.5\%$ kecocokan pada uji verifikasi data `CHUNK_PAGE_MAP`.
4. **Audit Angka VLM:** Setiap angka dalam deskripsi yang tidak tercetak di gambar otomatis diberi flag `needs_review: true`.
5. **Quality report dihasilkan otomatis** untuk setiap dokumen yang diproses.

### V1.13. Estimasi Waktu Realistis (2â€“4 Hari Kerja)

| Langkah | Rincian Pekerjaan | Estimasi |
|---------|-------------------|----------|
| **Langkah 1** | `core/parser.py` & `core/cleaner.py`: wrapper LlamaParse, normalisasi heading, pembersihan generic header/footer | 0.5 â€“ 1 hari |
| **Langkah 2** | `core/figures.py`: ekstraksi visual PDF, integrasi VLM 9router (`cx/gpt-6-luna[1m]`), caching SHA-256 | 0.5 â€“ 1 hari |
| **Langkah 3** | `core/chunker.py`: integrasi fungsi `chunk_markdown.py` (`overlap_tail`, `determine_content_type`, binding tabel), format chunk_id slug, dan dynamic page mapper | 0.5 â€“ 1 hari |
| **Langkah 4** | `core/embedder.py`, CLI `ingest.py`, dan update kecil parameter `source` di `mcp_server.py` | 0.5 hari |
| **Langkah 5** | `core/reporter.py` (quality report) & pengujian end-to-end 2 paper baru + uji regresi baseline paper 1 | 0.5 â€“ 1 hari |
| **Total** | **Rentang estimasi keseluruhan** | **2 â€“ 4 hari kerja** |

---

## VERSI 2 â€” Pipeline Lengkap (Future, Setelah V1 Stabil)

Fitur-fitur berikut **tidak masuk V1** dan dijadwalkan untuk iterasi berikutnya:

| Fitur | Keterangan |
|-------|------------|
| **Auto figure relocation** | Logika otomatis setara `fix_section_6_placement`: deteksi figur yang terapung/salah seksi di PDF dan relokasi otomatis ke seksi rujukan terdekat (mis. penanganan kasus Fig. 19 / Q11 / Q25) |
| **Publisher profiles** | Pola header/footer spesifik per penerbit (Springer, Elsevier, IEEE, ACM) berbasis rule catalog |
| **Per-document `config.yaml`** | Konfigurasi deklaratif aturan khusus per dokumen (custom drop pattern, caption radius, custom regex) |
| **Multi-layer VLM fallback** | Prioritas fallback otomatis bertingkat: 9router â†’ Gemini API â†’ Ollama vision â†’ `needs_review` |
| **Sitasi multi-dokumen dinamis** | Format sitasi otomatis pada system prompt DSS: `[Ribino et al. 2023, Hal. 9]` saat menjawab dari multi-dokumen |

---

## Catatan: ag/ Quota Sharing dengan IDE

Model dengan prefix `ag/` (mis. `ag/gemini-3.8-flash`) di 9router **menggunakan akun Antigravity (AGY) yang sama** dengan model IDE agent. Eksperimen selama spike mengkonfirmasi ini: `ag/gemini-3.8-flash` mengembalikan `503 Individual quota reached (429 upstream)` persis ketika IDE model sedang aktif.

**Kesimpulan:** Jangan gunakan model `ag/` dalam skrip ingestion batch â€” quota akan bersaing dengan sesi IDE. Gunakan `cx/gpt-6-luna[1m]` via 9router untuk VLM, atau gunakan `GEMINI_API_KEY` untuk akses langsung ke Gemini API tanpa quota AGY.

---

## Skema Supabase â€” Migrasi 005 (BELUM DIJALANKAN)

> [!CAUTION]
> Migrasi ini **BELUM BOLEH dijalankan** sampai setelah sidang. Pre-kondisi: `embed_chunks.py`, `eval/run_eval.py`, dan `mcp_server.py` (get_chunk) harus sudah mendukung prefixed chunk_id terlebih dahulu.

```sql
-- =============================================================================
-- 005_add_multidoc_support.sql
-- Tambahkan dukungan multi-dokumen. Aman dijalankan: ALTER TABLE IF NOT EXISTS.
-- Pre-kondisi: embed_chunks.py, eval/run_eval.py, dan mcp_server.py sudah
-- mendukung prefixed chunk_id sebelum 005 ini dijalankan.
-- =============================================================================

-- 1. Tambah kolom pada knowledge_documents (file_hash dihapus â€” gunakan content_hash yang ada)
ALTER TABLE knowledge_documents
    ADD COLUMN IF NOT EXISTS doc_slug text,
    ADD COLUMN IF NOT EXISTS metadata jsonb DEFAULT '{}'::jsonb;

-- 2. Backfill paper pertama (COALESCE agar tidak menimpa metadata yang sudah ada)
UPDATE knowledge_documents
SET
    doc_slug = 'furniture_arrangement_ieq_2023',
    metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object(
        'year', 2023,
        'authors', jsonb_build_array('Patrizia Ribino', 'Marina Bonomolo'),
        'language', 'en',
        'publisher', 'springer'
    )
WHERE source = 'furniture_arrangement_ieq_2023.pdf'
  AND (doc_slug IS NULL OR doc_slug = '');

-- 3. Tambah UNIQUE constraint setelah backfill selesai
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_knowledge_documents_doc_slug'
    ) THEN
        ALTER TABLE knowledge_documents
            ADD CONSTRAINT uq_knowledge_documents_doc_slug UNIQUE (doc_slug);
    END IF;
END $$;

-- 4. Backfill chunk_id dengan prefix slug (hanya baris yang belum berprefiks)
UPDATE knowledge_chunks kc
SET chunk_id = kd.doc_slug || ':' || kc.chunk_id
FROM knowledge_documents kd
WHERE kc.document_id = kd.id
  AND kd.doc_slug IS NOT NULL
  AND kc.chunk_id NOT LIKE '%:%';

-- 5. Index untuk performa
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_chunk_id
    ON knowledge_chunks (chunk_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_documents_doc_slug
    ON knowledge_documents (doc_slug);
```

---

## Spike VLM â€” Hasil Eksekusi

### Round 1: Fig. 1, Fig. 8, Fig. 19

| Figur | Tipe | Durasi | Token | Kepatuhan Aturan |
|-------|------|--------|-------|-----------------|
| **Fig. 1** | Denah + matriks iluminansi (angka tercetak) | 8.62s | 3.706 | âœ… Semua angka disalin 100% akurat; tidak ada "sekitar" palsu |
| **Fig. 8** | Grouped bar chart tanpa label angka | 4.54s | 3.701 | âœ… Memakai "sekitar"; tidak membuat tabel tiruan; tidak ada desimal semu |
| **Fig. 19** | Grouped bar chart dengan label angka tercetak | 5.93s | 3.822 | âœ… Semua 10 angka disalin persis (cocok 100% dengan tabel paper) |

Model: `cx/gpt-6-luna[1m]` via 9router `localhost:20128`. Output mentah: [`spike_results.json`](file:///home/advance/backend-dss/data/_spike/spike_results.json)

### Round 2: Fig. 10, Fig. 13, Fig. 3

| Figur | Tipe | Durasi | Token | Kepatuhan Aturan | Perbandingan vs Ground Truth |
|-------|------|--------|-------|-----------------|------------------------------|
| **Fig. 10** | Grouped bar chart Visual Comfort Office #1, tanpa label angka batang | 6.99s | 3.787 | âœ… Memakai "sekitar" untuk nilai batang; hanya menyalin angka sumbu Y (85,87,89,...,100) dan threshold 97 yang tercetak; tidak membuat tabel tiruan | Cocok: rentang "sekitar 93â€“95", anomali Test 7 User 1 "sekitar 87". Ground truth juga menyebut 93â€“95.5 kecuali Test 7 |
| **Fig. 13** | Grouped bar chart Visual Comfort Office #2, tanpa label angka batang | 4.66s | 3.798 | âœ… Memakai "sekitar"; hanya salin sumbu Y dan threshold tercetak; tidak ada desimal semu | Cocok: "sekitar atau di atas 97", penurunan Test 11 dan 19. Ground truth: 97â€“98.6 kecuali Test 11 & 19 |
| **Fig. 3** | Diagram skematik 4 orientasi meja | 3.89s | 3.944 | âœ… Tidak ada angka data â†’ tidak ada "sekitar"; deskripsikan 4 orientasi secara kualitatif | Cocok: HORIZONTAL-UP, VERTICAL-RIGHT, VERTICAL-LEFT, HORIZONTAL-DOWN dengan sumbu xâ€² yâ€² |

Output mentah: [`spike_results_round2.json`](file:///home/advance/backend-dss/data/_spike/spike_results_round2.json)

---

## Kandidat Paper 2 & 3 untuk Uji Ingestion V1

Dua kandidat dipilih dengan karakteristik layout **berbeda dari paper 1** (Springer 2-kolom, header berulang, figur mixed). Paper harus mengandung rumus dan tabel untuk menguji generalisasi pipeline.

### Kandidat A â€” Single-Column arXiv Preprint
**Contoh:** Paper energi bangunan atau simulasi termal di arXiv (format LaTeX single-column, layout lebar, heading tanpa nomor)
- **Perbedaan dari paper 1:** Tidak ada running header penerbit, heading bisa berupa bold teks biasa (bukan `## Heading N`), tabel bisa menggunakan format LaTeX `tabular` alih-alih HTML.
- **Tantangan uji:** Cleaner tidak boleh menganggap `4.1.` sebagai header jika tidak ada hierarki jelas; chunker harus mengenali `\begin{equation}` dan tidak memotong di tengahnya.
- **Cocok untuk menguji:** generic header removal, formula preservation, single-column flow.

### Kandidat B â€” IEEE atau Elsevier Double-Column
**Contoh:** Paper smart building / IoT sensor comfort dari IEEE Transactions atau Elsevier Energy & Buildings
- **Perbedaan dari paper 1:** Header format "IEEE TRANSACTIONS ON ... VOL. X, NO. Y, MONTH YEAR", nomor halaman di kiri/kanan luar, footnote pada kolom pertama, figur kadang full-width memotong dua kolom.
- **Tantangan uji:** Header regex berbeda dari Springer; LlamaParse mungkin menggabungkan atau memisahkan kolom secara acak; tabel bisa mencakup kedua kolom.
- **Cocok untuk menguji:** publisher-agnostic cleaner, multi-column figure handling, cross-column table detection.

### Dampak Cross-Document Search & Pemfilteran

Setelah dua paper baru masuk database:
- **Pencarian dengan filter `source` (V1):** Mengisolasi pencarian ke dokumen target tertentu menggunakan parameter `source` pada `search_documents`. Menjamin evaluasi paper 1 tidak terpengaruh oleh konten paper 2.
- **Pencarian tanpa filter `source`:** Retrieval mencampur chunk dari seluruh dokumen. Ranking ditentukan oleh relevansi semantik dan leksikal gabungan.

---

## Baseline Retrieval Paper 1 (Sebelum Refactoring)

Dihitung dari 24 pertanyaan in-domain (Q01â€“Q16, Q19â€“Q26):

| Metrik | Nilai |
|--------|-------|
| Hit@1 | 14/24 = **58.33%** |
| Hit@3 | 20/24 = **83.33%** |
| Hit@5 | 23/24 = **95.83%** |
| MRR | **0.7236** |
| Recall@5 | **90.97%** |
| Miss@5 | Q02 (rank=None) |

Kriteria regresi 5C.7: Hit@5 â‰¥ 95.83% dan MRR â‰¥ 0.7236 pada 24 pertanyaan in-domain paper pertama, diuji setelah paper baru masuk database, baik dengan maupun tanpa filter `source`.

---

*Dokumen ini diperbarui pada Tahap 5B (revisi 2). Implementasi 5C belum dimulai.*
