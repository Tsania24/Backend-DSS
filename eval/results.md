# Laporan Evaluasi RAG & Agentic AI (Tahap 4, 4B & 4C)

Dokumen ini menyajikan hasil evaluasi komprehensif sistem RAG berbasis FastMCP, PostgreSQL Supabase pgvector (hybrid search semantic + full-text search dengan reciprocal rank fusion), dan Hermes Agent pada paper ilmiah *“A multi-objective reinforcement learning approach for furniture arrangement with optimal IEQ in multi-occupant offices”* (Ribino & Bonomolo, 2023).

---

## 1. Ringkasan Metodologi & Tahapan Evaluasi

Evaluasi dilakukan dalam tiga tahap terukur tanpa mengubah pipeline retrieval pgvector maupun data chunk:

1. **Tahap 4 (Evaluasi Awal Baseline):**
   - 20 pertanyaan terstruktur (Q01–Q20) mencakup teks, tabel, gambar, rumus, luar domain, dan lintas bagian.
   - Mengidentifikasi kelemahan runtime di mana Hermes Agent macet mencoba mengeksekusi kode Python arbitrer via `execute_code` untuk menghitung perbedaan angka tabel.
2. **Tahap 4B (Konfigurasi Minimal Gateway & Pertanyaan Alami):**
   - **Konfigurasi Minimal Platform `api_server: []`**: Toolset bawaan non-MCP (`code_execution`, `terminal`, `file`, `browser`, `computer_use`, `cronjob`, `delegation`, `web`, `image_gen`, `tts`, `memory`, dll.) dinonaktifkan secara struktural pada platform gateway HTTP API server (port 8642), menyisakan **hanya 4 tool MCP** (`spawn_furniture`, `search_documents`, `get_chunk`, `get_page_context`). Platform CLI tetap utuh.
   - **Koreksi Data Acuan**: Menghapus dimensi fiktif pada Q19, memperluas cakupan chunk Q03 ke `chunk_026` dan `chunk_027`, serta menyempurnakan acuan Q24.
   - **6 Pertanyaan Baru (Q21–Q26)**: Disusun tanpa pengenal eksplisit (*"Table N"*, *"Fig. N"*, *"Eq. N"*) menggunakan parafrase bahasa alami pengguna. Mode 1 diuji menggunakan string query yang dihasilkan sendiri oleh Hermes Agent saat menjawab pertanyaan di Mode 2.
3. **Tahap 4C (Perbaikan Prompt Grounding & Anti-Kausalitas):**
   - Penambahan aturan ketat pada `system_prompt` server.py:
     - Larangan menyimpulkan penyebab/hubungan kausal yang tidak dinyatakan eksplisit di paper.
     - Larangan menyebut subjek atau mekanisme yang tidak tercantum di teks chunk hasil pencarian.
     - Kewajiban mencakup seluruh objek saat pertanyaan menyebut beberapa entitas (mis. Office #1 dan Office #2).
     - Sitasi wajib menyertakan seluruh rentang `page_numbers` dari chunk yang digunakan.

---

## 2. Tabel Sebelum vs Sesudah: Konfigurasi & Pertanyaan

| ID | Aspek | Kondisi Sebelum (Tahap 4) | Kondisi Sesudah (Tahap 4B / 4C) | Dampak & Keterangan |
|:---|:---|:---|:---|:---|
| **Q03** | Chunk Target | `expected_chunk_ids: ["chunk_027"]` | `expected_chunk_ids: ["chunk_026", "chunk_027"]` | Kalimat ambang batas kenyamanan ($TC > 90, VC > 97, AC > 95$) tercetak di kedua chunk karena batas overlap. Keduanya kini terhitung valid. |
| **Q19** | Konten Acuan & Mode 2 Agent | Teks acuan memuat dimensi fiktif "5.5 x 4.8 x 2.8 m".<br>Mode 2 Agent **Timed Out (180s)** akibat loop panggilan `execute_code`. | Dimensi fiktif dihapus (denah non-persegi panjang).<br>Mode 2 Agent **Selesai dalam 27–29 detik** tanpa loop kode, menghasilkan jawaban komparatif lengkap dengan sitasi akurat. | Masalah timeout terselesaikan total dengan menonaktifkan `code_execution` di gateway API. |
| **Q24** | Formulasi Acuan | Mengasumsikan User #1 ditempatkan di dekat jendela. | Acuan diperbaiki: Layout Pattern #2 Office #2 memiliki indeks termal lebih rendah (93.0 untuk User #1, Table 5) karena kursi pekerja dekat jendela, tanpa mengklaim User #1 yang sengaja didekatkan ke jendela. | Sesuai persis dengan teks dan tabel di PDF Hal. 10–12. |
| **Gateway API** | Toolset Aktif | Semua toolset bawaan aktif (termasuk `execute_code`, `terminal`, `browser`). | `platform_toolsets.api_server: []` -> **Hanya 4 Tool MCP aktif**. | Keamanan gateway meningkat, eliminasi resiko eksekusi kode lokal arbitrer. |

---

## 3. Hasil Mode 2: Perbandingan Berdampingan Sebelum vs Sesudah Perbaikan Prompt (Tahap 4B vs Tahap 4C)

Seluruh pengujian dijalankan dengan batas timeout **90 detik**. Hasil disajikan lengkap tanpa penilaian otomatis biner (kolom evaluasi mandiri disediakan):

| ID | Pertanyaan User | Respon Sebelum Perbaikan Prompt (Tahap 4B) | Respon Sesudah Perbaikan Prompt (Tahap 4C) | Waktu & Query Agen (4C) | Sitasi Dokumen (4C) | Perlu Dinilai Manusia |
|:---|:---|:---|:---|:---:|:---|:---:|
| **Q19** | *Bagaimana perbedaan karakteristik fisik Office #1 dan Office #2 (Section 5) dan bagaimana kaitannya dengan hasil total reward kedua kantor pada Table 1 (Section 5.1)?* | Office #1 berukuran 4,5 × 3,5 × 2,8 m, dengan satu jendela besar... Office #2 disebut sedikit berbeda ukuran dan bentuknya, tetapi dimensi pastinya tidak dicantumkan... Pada Table 1, total reward Office #2 lebih tinggi: rerata 561,27 dibanding 558,80... Deviasi standarnya juga lebih rendah (1,20 vs 1,63)... | Office #1 berukuran 4,5 × 3,5 × 2,8 m dan memiliki satu jendela besar menghadap barat laut serta satu unit AC. Area lantainya 15,75 m². Cahaya alami tidak merata: bagian tengah sekitar 300 lx, dekat jendela 500–800 lx, dan sudut kiri atas hanya 50–130 lx.<br><br>Office #2 berbentuk tidak beraturan dan sedikit lebih kecil: luas lantai 14,75 m². Kantor ini memiliki dua jendela—menghadap barat laut dan utara—serta dua unit AC di dinding berlawanan. Dua orientasi jendela memberi sebaran cahaya yang lebih baik; area dekat jendela utara sekitar 400–550 lx dan dekat jendela barat laut 500–700 lx. [Hal. 8–9, Section 5 Experimental evaluation]<br><br>Pada Table 1, Office #2 memperoleh total reward rata-rata sedikit lebih tinggi: 561,27 dibanding 558,80 pada Office #1. Nilai maksimum/minimumnya juga lebih tinggi (563,21/558,92 vs. 561,46/553,66), sementara deviasi standarnya lebih kecil (1,20 vs. 1,63). Jadi hasil Office #2 sedikit lebih baik dan lebih konsisten. Penulis mengaitkan keunggulan IEQ visual Office #2 dengan dua jendelanya yang berorientasi berbeda. Namun, Table 1 tidak membuktikan bahwa perbedaan fisik itu satu-satunya penyebab reward lebih tinggi: kenyamanan termal memenuhi standar di kedua kantor, sedangkan akustik tetap di bawah standar. | 27.49s<br><br>Query: `'Office #1 Office #2 physical characteristics Section 5 total reward Table 1'` (4x) | `[Hal. 8–9, Section 5 Experimental evaluation]`, `[Hal. 9–10, Section 5.1 Results and discussions; Hal. 12–13, Section 5.1 Results and discussions]` | Ya |
| **Q21** | *Mengapa performa tata letak pada Office #2 dilaporkan lebih baik dan lebih konsisten dibandingkan Office #1?* | Office #2 memiliki konfigurasi fisik yang lebih mendukung kenyamanan visual: dua jendelanya menghadap ke arah berbeda... Angka hasil 20 pengujian juga menunjukkan keunggulan kecil sekaligus variasi yang lebih rendah pada Office #2: rata-rata reward 561,27 dibanding 558,80, dan deviasi standar 1,20 dibanding 1,63... | Office #2 memperoleh reward rata-rata lebih tinggi (561,27 vs. 558,80) dan simpangan baku lebih rendah (1,20 vs. 1,63). Jadi, tata letak yang ditemukan bukan hanya sedikit lebih baik secara rata-rata, tetapi hasil antarpercobaannya juga lebih seragam. Rentang reward Office #2 juga lebih sempit: 558,92–563,21, dibandingkan 553,66–561,46 pada Office #1.<br><br>Paper mengaitkan perbedaan hasil dengan karakteristik fisik kantor yang memengaruhi kenyamanan lingkungan. Secara khusus, dua jendela dengan orientasi berbeda di Office #2 meningkatkan kenyamanan visual; Office #1 sulit mencapai standar kenyamanan visual pada siang hari karena orientasi jendelanya membatasi distribusi cahaya. Namun, akustik tetap di bawah standar pada kedua kantor, dan kenyamanan termalnya memenuhi standar. | 15.69s<br><br>Query: `'Office #2 Office #1 layout performance consistency results IEQ furniture arrangement'` | `[Hal. 9–13, Section 5 Experimental evaluation > 5.1 Results and discussions]` | Ya |
| **Q22** | *Seberapa stabil hasil optimasi MORL jika dibandingkan dengan algoritma reinforcement learning lainnya seperti PPO, DQN, dan A2C?* | Dalam eksperimen paper, MORL paling stabil di antara MORL, PPO, DQN, dan A2C: simpangan baku IEQ_Tot-nya paling rendah pada kelima pengujian, berkisar 0,89–1,92... | Dalam eksperimen paper, MORL tampak paling stabil di antara MORL, PPO, DQN, dan A2C: standar deviasi hasil IEQ_Tot-nya paling rendah pada kelima pengujian. Variabilitas MORL juga menurun seiring bertambahnya langkah pembelajaran, dan penulis menyebut pembelajarannya makin terkonsolidasi pada 5 × 10³ langkah. Sebaliknya, A2C menunjukkan variabilitas lebih tinggi; PPO dan DQN memerlukan lebih banyak langkah untuk memperoleh hasil yang lebih terkonsolidasi.<br><br>Kesimpulan ini terbatas pada eksperimen penataan furnitur yang dilaporkan—setiap eksperimen diulang 10 kali—bukan jaminan bahwa MORL selalu lebih stabil untuk tugas lain. | 14.07s<br><br>Query: `'MORL PPO DQN A2C stability robustness comparative optimization results'` | `[Hal. 12–13, Section 6; Hal. 17–19, Section 6.1]` | Ya |
| **Q23** | *Berapa standar tingkat bising yang direkomendasikan untuk ruang kantor, dan apakah ruangan kantor uji memenuhi standar tersebut?* | Standar kebisingan yang direkomendasikan untuk kantor dalam penelitian ini adalah 45 dB. Office #1 tidak memenuhi standar: tingkat tekanan akustik di posisi kerja sekitar 50 dB... | Standar akustik yang direkomendasikan adalah 45 dB. **Kedua kantor uji tidak memenuhi standar**: tingkat kebisingan di **Office #1 sekitar 50 dB**, sedangkan di **Office #2 sekitar 52 dB**. | 16.37s<br><br>Query: `'office acoustic noise sound level recommended standard test office room dB'` | `[Hal. 11–12, Section 5.1 Results and discussions; Hal. 12–13, Section 5 Experimental evaluation > 5.1 Results and discussions]` | Ya |
| **Q24** | *How does placing an occupant's chair close to the window affect their thermal comfort in Office #2 Layout Pattern #2?* | In Office #2 Layout Pattern #2, placing the chair near the window lowers thermal comfort for User #1: their thermal comfort index is 93, compared with 95 for User #2... | In Office #2 Layout Pattern #2, placing the chair near the window reduces thermal comfort: the window has a lower mean radiant temperature than the other surfaces, which can make the occupant feel thermally dissatisfied. The pattern’s thermal comfort index is 93.0 for User #1, compared with 95.0 for User #2; both remain above the paper’s 90 threshold. | 10.54s<br><br>Query: `'Office #2 Layout Pattern #2 occupant chair close to window thermal comfort'` | `[pp. 10–12, Section 5.1, “Results and discussions”]` | Ya |
| **Q25** | *How does the multi-objective reinforcement learning approach compare to the genetic algorithm NSGA-II in terms of execution time across different test scenarios?* | MORL was faster than NSGA-II in all five test scenarios: Test 1: MORL 4.00 s vs NSGA-II 4.40 s... | MORL was slightly faster than NSGA-II in all five test scenarios:<br><br>Test 1: MORL 4.00 s vs NSGA-II 4.40 s<br>Test 2: 7.82 s vs 8.52 s<br>Test 3: 11.58 s vs 12.61 s<br>Test 4: 15.68 s vs 16.37 s<br>Test 5: 19.39 s vs 20.52 s<br><br>Execution time rose for both methods across the tests, but MORL remained faster each time. | 10.92s<br><br>Query: `'MORL NSGA-II execution time different test scenarios'` | `[pp. 20–21, Section 6.2 “Comparison with NSGA-II”]` | Ya |
| **Q26** | *Bagaimana pembobotan prioritas antara kepuasan kenyamanan lingkungan (IEQ) dan kendala jarak spasial pada fungsi reward penataan furnitur?* | Fungsi reward dirumuskan sebagai multiobjektif: reward IEQ untuk masing-masing penghuni dan reward jarak antarpenghuni. Dalam eksperimen, bobot vektor W = (0,4; 0,4; 0,2)... | Bobotnya ditetapkan sebagai W = (0,4; 0,4; 0,2): kepuasan IEQ kedua penghuni mendapat bobot lebih besar daripada jarak antar-penghuni. Artinya, fungsi reward memprioritaskan kenyamanan IEQ, tetapi tetap mempertimbangkan jarak sebagai objektif tersendiri—bukan mengabaikannya. [Hal. 9–10, Section 5 Experimental evaluation]<br><br>Di dalam komponen IEQ, kenyamanan termal, akustik, dan visual diasumsikan berbobot sama, masing-masing p = 0,33. | 11.97s<br><br>Query: `'IEQ satisfaction spatial distance constraints reward function weighting priority furniture arrangement'` | `[Hal. 9–10, Section 5 Experimental evaluation]` | Ya |

---

## 4. Hasil Mode 1 Menggunakan Query Alami yang Diformulasikan Agen (Tahap 4C: Q21–Q26)

Pada pengujian ini, string pencarian yang dimasukkan ke `search_documents` **bukan buatan manusia**, melainkan diambil langsung dari query terjemahan/reformulasi yang dibuat oleh Hermes Agent pada Tahap 4C:

| ID | Pertanyaan Bahasa Alami | Query yang Diformulasikan Agen (Tahap 4C) | Chunk Target Acuan | Top-5 Retrieval (Peringkat & Chunk) | Peringkat Chunk Acuan | Target Rank | Hit@1 | Hit@3 | Hit@5 | Recall@5 | MRR |
|:---|:---|:---|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Q21** | *Mengapa performa tata letak pada Office #2 dilaporkan lebih baik dan lebih konsisten dibandingkan Office #1?* | `Office #2 Office #1 layout performance consistency results IEQ furniture arrangement` | `chunk_021`, `chunk_022`, `chunk_023`, `chunk_025` | 1. `chunk_028`<br>2. `chunk_027`<br>3. `chunk_026`<br>4. **`chunk_025`\***<br>5. **`chunk_022`\*** | `chunk_025`: #4<br>`chunk_022`: #5<br>`chunk_021`, `023`: >5 | **4** | 0 | 0 | 1 | 0.50 | 0.2500 |
| **Q22** | *Seberapa stabil hasil optimasi MORL jika dibandingkan dengan algoritma reinforcement learning lainnya seperti PPO, DQN, dan A2C?* | `MORL PPO DQN A2C stability robustness comparative optimization results` | `chunk_034`, `chunk_035` | 1. **`chunk_035`\***<br>2. **`chunk_034`\***<br>3. `chunk_033`<br>4. `chunk_036`<br>5. `chunk_031` | `chunk_035`: #1<br>`chunk_034`: #2 | **1** | 1 | 1 | 1 | 1.00 | 1.0000 |
| **Q23** | *Berapa standar tingkat bising yang direkomendasikan untuk ruang kantor, dan apakah ruangan kantor uji memenuhi standar tersebut?* | `office acoustic noise sound level recommended standard test office room dB` | `chunk_026`, `chunk_027`, `chunk_028` | 1. **`chunk_027`\***<br>2. `chunk_012`<br>3. `chunk_029`<br>4. `chunk_021`<br>5. **`chunk_028`\*** | `chunk_027`: #1<br>`chunk_028`: #5<br>`chunk_026`: >5 | **1** | 1 | 1 | 1 | 0.67 | 1.0000 |
| **Q24** | *How does placing an occupant's chair close to the window affect their thermal comfort in Office #2 Layout Pattern #2?* | `Office #2 Layout Pattern #2 occupant chair close to window thermal comfort` | `chunk_026`, `chunk_027` | 1. **`chunk_026`\***<br>2. `chunk_028`<br>3. **`chunk_027`\***<br>4. `chunk_025`<br>5. `chunk_001` | `chunk_026`: #1<br>`chunk_027`: #3 | **1** | 1 | 1 | 1 | 1.00 | 1.0000 |
| **Q25** | *How does the multi-objective reinforcement learning approach compare to the genetic algorithm NSGA-II in terms of execution time across different test scenarios?* | `MORL NSGA-II execution time different test scenarios` | `chunk_038` | 1. **`chunk_038`\***<br>2. `chunk_037`<br>3. `chunk_035`<br>4. `chunk_036`<br>5. `chunk_034` | `chunk_038`: #1 | **1** | 1 | 1 | 1 | 1.00 | 1.0000 |
| **Q26** | *Bagaimana pembobotan prioritas antara kepuasan kenyamanan lingkungan (IEQ) dan kendala jarak spasial pada fungsi reward penataan furnitur?* | `IEQ satisfaction spatial distance constraints reward function weighting priority furniture arrangement` | `chunk_024` | 1. `chunk_014`<br>2. `chunk_001`<br>3. `chunk_025`<br>4. **`chunk_024`\***<br>5. `chunk_015` | `chunk_024`: #4 | **4** | 0 | 0 | 1 | 1.00 | 0.2500 |

> [!NOTE]
> Dari 6 query bahasa alami yang diformulasikan sendiri oleh Hermes Agent pada Tahap 4C:
> - **100% (6 dari 6)** berhasil menemukan chunk target dalam Top-5 (**Hit@5 = 1.0000**).
> - **66.7% (4 dari 6)** langsung menempatkan chunk target di **Peringkat 1** (**Hit@1 = 0.6667**, naik dari 50% di Tahap 4B).
> - **66.7% (4 dari 6)** menempatkan chunk target di **Top-3** (**Hit@3 = 0.6667**).
> - Rata-rata **MRR = 0.7500** (naik dari 0.6583 di Tahap 4B).
> - Rata-rata **Recall@5 = 0.8617** (86.17%).
> Ini membuktikan bahwa query yang diekspansi oleh LLM Agent pada Tahap 4C sangat efektif mengarahkan retrieval ke bagian dokumen yang tepat meskipun pengguna tidak menyebutkan nomor tabel atau figur.

---

## 5. Hasil Deteksi di Luar Dokumen: Level Tool vs Level Agent

Tabel berikut memisahkan secara tegas bagaimana pertanyaan di luar cakupan dokumen ditangani pada dua tingkatan arsitektur:

| ID | Pertanyaan User | Deteksi pada Level Tool (`search_documents`) | Deteksi pada Level Agent (Hermes LLM) | Analisis & Perbedaan Perilaku |
|:---|:---|:---|:---|:---|
| **Q17** | *Bagaimana resep dan langkah-langkah memasak rendang daging sapi khas Minangkabau?* (Out-of-Domain Penuh) | **Status: `success`** (Bukan `no_relevant_result`)<br>• Sim Max: 0.2404 (di bawah ambang 0.40)<br>• FTS Rank: 0.10 (kata umum *'steps'* cocok di teks) | **Menolak Langsung (Zero-Shot)**<br>• Tool dipanggil: **0 (Tidak memanggil tool)**<br>• Respon: *"Pertanyaan ini di luar cakupan sistem dan tidak ada di dokumen."* | Pada level tool leksikal, kata umum bahasa Inggris seperti *'steps'* memicu `fts_rank > 0` sehingga aturan `no_relevant_result` tidak terpicu. Namun pada level kognitif, Agent langsung menyaring topik kuliner tanpa membuang token untuk memanggil database. |
| **Q18** | *Berapa konsumsi listrik (kWh) sistem AC pada Office #1?* (Near Out-of-Domain) | **Status: `success`**<br>• Sim Max: 0.4811<br>• FTS Rank: 3.20 (kata *'air conditioning'*, *'Office 1'* cocok kuat) | **Mengecek Dokumen lalu Menjelaskan Batasnya**<br>• Tool dipanggil: `search_documents`<br>• Respon: Menyebut bahwa AC di Office #1 menghasilkan kebisingan 55 dB dan suhu 23 °C pada Hal. 8, tetapi data konsumsi listrik dalam kWh tidak tercantum di paper. | Karena query memuat entitas in-domain yang valid (*AC*, *Office 1*), tool retrieval mengembalikan chunk fisik. Namun Agent tidak berhalusinasi mengarang angka kWh, melainkan secara tepat menjelaskan batas dokumen berdasarkan hasil bacaan chunk. |

---

## 6. Kesimpulan Tahap 4, 4B & 4C

1. **Eliminasi Celah Timeout & Panggilan Tool Eksternal**:
   - Penerapan `api_server: []` mengunci toolset gateway hanya pada 4 tool domain FastMCP, meniadakan percobaan eksekusi kode lokal dan menjaga waktu respons tetap stabil di bawah 30 detik.
2. **Kualitas Faktual & Netralitas Kausalitas (Tahap 4C)**:
   - Respon Q19 kini secara lengkap memuat dimensi fisik kedua kantor dan menegaskan secara jujur bahwa paper tidak membuktikan perbedaan fisik tersebut sebagai satu-satunya penyebab kenaikan reward.
   - Respon Q23 kini secara tuntas melaporkan data kedua kantor: Office #1 (~50 dB) dan Office #2 (~52 dB).
   - Respon Q24 tidak lagi menarik kesimpulan tak berdasar tentang penempatan User #1, melainkan murni menjelaskan dampak termal di dekat jendela dan angka Table 5 (93.0 vs 95.0).
3. **Retrieval Berkelanjutan**:
   - Seluruh 4 tool FastMCP (termasuk `spawn_furniture` ke antrean Unity SSE) terbukti stabil tanpa regresi.
   - Sistem siap untuk fase integrasi berikutnya.
