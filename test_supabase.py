import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

# Memuat konfigurasi dari file .env di folder proyek.
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(env_path)

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SECRET_KEY")

if not url or not key:
    raise RuntimeError(
        "SUPABASE_URL atau SUPABASE_SECRET_KEY belum dikonfigurasi."
    )

try:
    supabase = create_client(url, key)

    # Menguji akses ke tabel yang sebelumnya kita buat.
    result = (
        supabase
        .table("knowledge_documents")
        .select("id")
        .limit(1)
        .execute()
    )

    print("Status: KONEKSI BERHASIL")
    print("Database dapat diakses.")
    print("Jumlah baris yang dikembalikan:", len(result.data))

except Exception as error:
    print("Status: KONEKSI GAGAL")
    print(type(error).__name__ + ":", error)
