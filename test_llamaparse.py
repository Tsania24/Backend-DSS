import time
import re
from pathlib import Path
from dotenv import load_dotenv
from llama_cloud import LlamaCloud

load_dotenv()

PDF_PATH = Path("data/raw/furniture_arrangement_ieq_2023.pdf")

if not PDF_PATH.exists():
    raise FileNotFoundError(f"PDF tidak ditemukan: {PDF_PATH}")

print("=" * 55)
print("LLAMAPARSE BENCHMARK")
print("=" * 55)

client = LlamaCloud()

# 1. Upload PDF
print("\n[1/2] Mengunggah PDF...")
upload_start = time.perf_counter()

uploaded_file = client.files.create(
    file=str(PDF_PATH),
    purpose="parse"
)

upload_time = time.perf_counter() - upload_start
print(f"Upload selesai: {upload_time:.2f} detik")
print(f"File ID: {uploaded_file.id}")

# 2. Parse PDF
print("\n[2/2] Memproses PDF dengan LlamaParse...")
parse_start = time.perf_counter()

result = client.parsing.parse(
    file_id=uploaded_file.id,
    tier="cost_effective",
    version="latest",
    expand=["markdown"]
)

parse_time = time.perf_counter() - parse_start

# 3. Analisis hasil di memori
pages = result.markdown.pages if result.markdown else []
successful_pages = [
    page for page in pages
    if getattr(page, "success", True)
]

page_texts = [
    page.markdown or ""
    for page in successful_pages
]

full_text = "\n".join(page_texts)

table_count = len(re.findall(
    r"(?m)^\s*\|.*\|\s*$",
    full_text
))

equation_markers = len(re.findall(
    r"\\\[|\\\(|\$\$|\\begin\{equation\}",
    full_text
))

# 4. Tampilkan hasil
print("\n" + "=" * 55)
print("HASIL BENCHMARK")
print("=" * 55)

print(f"Total halaman terdeteksi : {len(pages)}")
print(f"Halaman berhasil        : {len(successful_pages)}")
print(f"Total karakter          : {len(full_text):,}")
print(f"Estimasi baris tabel    : {table_count}")
print(f"Penanda persamaan       : {equation_markers}")
print(f"Waktu upload            : {upload_time:.2f} detik")
print(f"Waktu parsing           : {parse_time:.2f} detik")
print(f"Total waktu             : {upload_time + parse_time:.2f} detik")

print("\nContoh hasil ekstraksi (maksimal 1.000 karakter):")
print("-" * 55)
print(full_text[:1000])

print("\nBenchmark selesai.")
print("Hasil parsing hanya disimpan di memori, bukan file Markdown.")
