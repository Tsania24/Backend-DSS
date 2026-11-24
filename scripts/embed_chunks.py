#!/usr/bin/env python3
"""
embed_chunks.py
----------------
Menghasilkan vector embedding untuk setiap chunk menggunakan model Ollama lokal
(qwen3-embedding:0.6b, 1024 dimensi) dan menyimpannya ke Supabase (pgvector).

Fitur:
1. Idempotent: upsert dokumen (on_conflict='source') dan chunks (on_conflict='document_id,chunk_index').
2. Menyimpan metadata lengkap:
   - source, page_number, heading_path, content_type, image_path, chunk_id
   - flag has_table, has_latex, has_figure_description
3. Mode --dry-run [N]: hanya proses N chunk pertama (default: 3) untuk verifikasi awal.
4. Mode --test-query: menguji fungsi RPC match_knowledge_chunks_v2.

Usage:
    python scripts/embed_chunks.py --dry-run 3
    python scripts/embed_chunks.py --all
    python scripts/embed_chunks.py --test-query "thermal comfort index threshold"
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# ── Konfigurasi ───────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
EMBEDDING_MODEL = "qwen3-embedding:0.6b"
EXPECTED_DIM = 1024
CHUNKS_FILE = ROOT / "data/chunks/furniture_arrangement_ieq_2023_chunks.jsonl"


def get_embedding(text: str, model: str = EMBEDDING_MODEL) -> list[float]:
    """Mengambil embedding vektor dari Ollama API lokal."""
    payload = json.dumps({"model": model, "input": text}).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            embeddings = data.get("embeddings")
            if not embeddings or not isinstance(embeddings, list):
                raise ValueError(f"Respon embedding kosong atau tidak valid: {data}")
            vec = embeddings[0]
            if len(vec) != EXPECTED_DIM:
                raise ValueError(
                    f"Dimensi vektor {len(vec)} tidak cocok dengan target {EXPECTED_DIM}"
                )
            return vec
    except urllib.error.URLError as err:
        raise ConnectionError(
            f"Gagal menghubungi Ollama di {OLLAMA_EMBED_URL}: {err}. "
            "Pastikan Ollama berjalan (`ollama serve`)."
        ) from err


def get_supabase_client():
    """Inisialisasi klien Supabase dari kredensial .env."""
    if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
        raise RuntimeError(
            "SUPABASE_URL atau SUPABASE_SECRET_KEY belum dikonfigurasi di .env."
        )
    return create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)


def upsert_document(sb, source_name: str, title: str, total_chunks: int) -> str:
    """Upsert entri dokumen utama ke tabel knowledge_documents."""
    doc_payload = {
        "source": source_name,
        "title": title,
        "content_hash": f"doc_{source_name}_{total_chunks}",
        "metadata": {
            "source_type": "journal",
            "format": "markdown",
            "total_chunks": total_chunks,
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dim": EXPECTED_DIM,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    }
    res = (
        sb.table("knowledge_documents")
        .upsert(doc_payload, on_conflict="source")
        .execute()
    )
    if not res.data:
        raise RuntimeError("Gagal meng-upsert baris ke knowledge_documents.")
    doc_id = res.data[0]["id"]
    return doc_id


def upsert_chunk(sb, document_id: str, chunk_data: dict, embedding: list[float]) -> dict:
    """Upsert satu entri chunk ke tabel knowledge_chunks."""
    chunk_payload = {
        "document_id": document_id,
        "chunk_index": chunk_data["chunk_index"],
        "chunk_id": chunk_data.get("chunk_id", f"chunk_{chunk_data['chunk_index']:03d}"),
        "content": chunk_data["content"],
        "content_hash": chunk_data["content_hash"],
        "page_number": chunk_data.get("page_number"),
        "heading_path": chunk_data.get("heading_path"),
        "content_type": chunk_data.get("content_type", "text"),
        "image_path": chunk_data.get("image_path", []),
        "embedding": embedding,
        "embedding_model": EMBEDDING_MODEL,
        "metadata": chunk_data.get("metadata", {}),
    }

    res = (
        sb.table("knowledge_chunks")
        .upsert(chunk_payload, on_conflict="document_id,chunk_index")
        .execute()
    )
    if not res.data:
        raise RuntimeError(
            f"Gagal meng-upsert chunk index {chunk_data['chunk_index']} ke knowledge_chunks."
        )
    return res.data[0]


def test_search(
    sb,
    query_text: str,
    top_k: int = 3,
    filter_source: str = None,
    filter_content_type: str = None,
):
    """Menguji semantic search menggunakan fungsi RPC match_knowledge_chunks_v2."""
    print(f"\n[SEARCH TEST] Query: '{query_text}'")
    query_vec = get_embedding(query_text)

    rpc_params = {
        "p_query_embedding": query_vec,
        "p_match_count": top_k,
        "p_filter_source": filter_source,
        "p_filter_content_type": filter_content_type,
        "p_filter_page_number": None,
    }

    res = sb.rpc("match_knowledge_chunks_v2", rpc_params).execute()
    matches = res.data or []

    print(f"Hasil ditemukan: {len(matches)} chunk")
    for i, m in enumerate(matches, 1):
        sim = m.get("similarity", 0.0)
        c_id = m.get("chunk_id")
        c_type = m.get("content_type")
        page = m.get("page_number")
        heading = m.get("heading_path")
        content_preview = m.get("content", "").replace("\n", " ")[:140]
        print(f"  {i}. [Sim: {sim:.4f}] {c_id} ({c_type}, Hal. {page})")
        print(f"     Heading : {heading}")
        print(f"     Preview : {content_preview}...")
    return matches


def main():
    parser = argparse.ArgumentParser(
        description="Embed RAG chunks ke Supabase pgvector."
    )
    parser.add_argument(
        "--dry-run",
        type=int,
        nargs="?",
        const=3,
        default=None,
        metavar="N",
        help="Proses hanya N chunk pertama (default: 3) tanpa memproses seluruh file.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Proses seluruh 43 chunk dari file JSONL.",
    )
    parser.add_argument(
        "--test-query",
        type=str,
        default=None,
        metavar="QUERY",
        help="Jalankan semantic search test dengan teks query setelah embedding.",
    )
    args = parser.parse_args()

    # Validasi argumen
    if not args.dry_run and not args.all and not args.test_query:
        print(
            "INFO: Tidak ada mode yang ditentukan. Menggunakan mode default: --dry-run 3.\n"
            "Gunakan --all untuk memproses seluruh dokumen setelah diverifikasi."
        )
        args.dry_run = 3

    if not CHUNKS_FILE.exists():
        print(f"ERROR: File chunks tidak ditemukan: {CHUNKS_FILE}")
        sys.exit(1)

    print("=" * 60)
    print("EMBEDDING & SUPABASE UPSERT PIPELINE")
    print("=" * 60)
    print(f"File Chunks    : {CHUNKS_FILE.name}")
    print(f"Embedding Model: {EMBEDDING_MODEL} ({EXPECTED_DIM} dimensi)")
    print(f"Target Database: Supabase pgvector")

    # Muat chunks
    with CHUNKS_FILE.open("r", encoding="utf-8") as f:
        all_chunks = [json.loads(line) for line in f if line.strip()]

    total_available = len(all_chunks)
    print(f"Total Chunks   : {total_available} chunk tersedia")

    # Inisialisasi Supabase
    sb = get_supabase_client()

    if args.test_query and not args.all and not args.dry_run:
        # Hanya menjalankan query test
        test_search(sb, args.test_query, top_k=5)
        return

    # Tentukan subset chunk yang akan diproses
    if args.dry_run:
        limit = min(args.dry_run, total_available)
        chunks_to_process = all_chunks[:limit]
        print(f"\n[MODE DRY-RUN]: Memproses {limit} chunk pertama saja.")
    else:
        chunks_to_process = all_chunks
        print(f"\n[MODE FULL]: Memproses seluruh {total_available} chunk.")

    # 1. Upsert parent document
    doc_source = all_chunks[0].get("source", "furniture_arrangement_ieq_2023.pdf")
    doc_title = all_chunks[0].get("document_title", "Furniture Arrangement with Optimal IEQ")
    print(f"\n[1/2] Upsert dokumen utama: {doc_source}")
    doc_id = upsert_document(sb, doc_source, doc_title, total_available)
    print(f"      Document ID: {doc_id}")

    # 2. Embed dan upsert chunks
    print(f"\n[2/2] Menghasilkan embedding & upserting chunks ({len(chunks_to_process)} chunk)...")
    results = []
    t_start = time.time()

    for idx, c in enumerate(chunks_to_process, 1):
        chunk_id = c.get("chunk_id", f"chunk_{c['chunk_index']:03d}")
        c_type = c.get("content_type", "text")
        heading = c.get("heading_path", c.get("section", "-"))
        page = c.get("page_number", "-")

        t0 = time.time()
        # Generate embedding
        vec = get_embedding(c["content"])
        t_embed = time.time() - t0

        t1 = time.time()
        # Upsert ke Supabase
        row = upsert_chunk(sb, doc_id, c, vec)
        t_upsert = time.time() - t1

        results.append({
            "chunk_id": chunk_id,
            "row_id": row["id"],
            "type": c_type,
            "page": page,
            "heading": heading,
            "embed_sec": round(t_embed, 3),
            "upsert_sec": round(t_upsert, 3),
        })

        print(
            f"  [{idx}/{len(chunks_to_process)}] {chunk_id:<9} | {c_type:<7} | "
            f"Hal {page:>2} | embed: {t_embed:.2f}s | upsert: {t_upsert:.2f}s | {heading[:40]}"
        )

    t_total = time.time() - t_start
    print(f"\nProses selesai dalam {t_total:.2f} detik (rata-rata {t_total/len(chunks_to_process):.2f}s/chunk).")

    # 3. Uji Retrieval Verifikasi jika dry-run
    if args.dry_run:
        print("\n" + "=" * 60)
        print("VERIFIKASI HASIL DRY-RUN (SEMANTIC SEARCH TEST)")
        print("=" * 60)
        # Test query relevan dengan 3 chunk pertama (Abstract / Introduction / IEQ)
        test_queries = [
            "Indoor Environmental Quality multi occupant offices",
            "reinforcement learning furniture arrangement",
        ]
        for q in test_queries:
            test_search(sb, q, top_k=3, filter_source=doc_source)

    print("\n" + "=" * 60)
    print("RINGKASAN STATUS")
    print("=" * 60)
    print(f"Chunks diproses : {len(results)}")
    print(f"Dimensi vektor  : {EXPECTED_DIM}")
    print(f"Tabel database  : knowledge_chunks (on_conflict: document_id, chunk_index)")
    print(f"Fungsi RPC      : match_knowledge_chunks_v2")


if __name__ == "__main__":
    main()
