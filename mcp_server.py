import json
import os
import urllib.error
import urllib.request

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from supabase import Client, create_client

# Muat konfigurasi dari ~/.hermes/.env dan .env lokal
load_dotenv(os.path.expanduser("~/.hermes/.env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)

# Konfigurasi Backend & MCP
API_KEY = os.getenv("API_SERVER_KEY")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
ALLOWED_SURFACES = {"FLOOR", "WALL", "TABLE"}

# Konfigurasi Supabase RAG & Embedding
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_ANON_KEY")
OLLAMA_EMBED_URL = os.getenv("OLLAMA_EMBED_URL", "http://127.0.0.1:11434/api/embed")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "qwen3-embedding:0.6b")
EXPECTED_DIM = 1024

# Ambang batas relevansi: jika similarity tertinggi < threshold DAN semua fts_rank = 0,
# maka status dinyatakan 'no_relevant_result'
RELEVANCE_SIMILARITY_THRESHOLD = 0.40

mcp = FastMCP("DSS-Adaptive-Building")

_supabase_client: Client | None = None


def get_supabase_client() -> Client:
    """Mengambil atau menginisialisasi singleton Supabase client."""
    global _supabase_client
    if _supabase_client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError(
                "SUPABASE_URL atau SUPABASE_KEY belum dikonfigurasi di file environment (.env)."
            )
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


def get_embedding(text: str) -> list[float]:
    """Mengambil vector embedding (1024 dimensi) dari Ollama qwen3-embedding:0.6b."""
    payload = json.dumps({"model": EMBEDDING_MODEL, "input": text}).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            embeddings = data.get("embeddings")
            if not embeddings or not isinstance(embeddings, list):
                raise ValueError(f"Respon embedding kosong atau tidak valid: {data}")
            vec = embeddings[0]
            if len(vec) != EXPECTED_DIM:
                raise ValueError(
                    f"Dimensi vektor ({len(vec)}) tidak sesuai target ({EXPECTED_DIM})"
                )
            return vec
    except urllib.error.URLError as err:
        raise ConnectionError(
            f"Gagal menghubungi Ollama di {OLLAMA_EMBED_URL}: {err}. "
            "Pastikan Ollama berjalan (`ollama serve`)."
        ) from err


@mcp.tool()
def spawn_furniture(
    asset_id: str,
    surface_label: str
) -> dict:
    """Send a furniture placement instruction to the DSS backend.

    Args:
        asset_id: Furniture asset identifier, e.g. table_wood.
        surface_label: Placement surface: FLOOR, WALL, or TABLE.
    """
    if not API_KEY:
        return {
            "status": "error",
            "message": "Backend API authentication is not configured"
        }

    if not asset_id.strip():
        return {
            "status": "error",
            "message": "asset_id must not be empty"
        }

    surface_label = surface_label.upper()

    if surface_label not in ALLOWED_SURFACES:
        return {
            "status": "error",
            "message": "surface_label must be FLOOR, WALL, or TABLE"
        }

    try:
        response = httpx.post(
            f"{BACKEND_URL}/api/mcp/spawn_furniture",
            headers={
                "Authorization": f"Bearer {API_KEY}"
            },
            json={
                "asset_id": asset_id,
                "surface_label": surface_label
            },
            timeout=10.0
        )

        response.raise_for_status()

        return response.json()

    except httpx.HTTPError as exc:
        return {
            "status": "error",
            "message": f"Could not forward command to backend: {exc}"
        }


@mcp.tool()
def search_documents(
    query: str,
    top_k: int = 5,
    content_type: str | None = None,
    page: int | None = None
) -> dict:
    """Cari dokumen referensi RAG menggunakan hybrid search (semantic + full-text search) dengan Reciprocal Rank Fusion.

    Kapan digunakan:
    Gunakan tool ini ketika memerlukan informasi faktual, rumus matematis, tabel data, atau grafik/denah dari paper ilmiah:
    'A multi-objective reinforcement learning approach for furniture arrangement with optimal IEQ in multi-occupant offices'.

    Pedoman Penggunaan:
    - Untuk istilah teknis (mis. "Bellman", "PMV", "NSGA-II"), gunakan kata kunci pendek, bukan kalimat panjang.
    - Paper memakai istilah bahasa Inggris, jadi query sebaiknya dalam bahasa Inggris (mis. "execution time", bukan "waktu komputasi").
    - Jawaban wajib menyertakan sitasi halaman (page_number) dan heading_path.
    - Jika status bernilai "no_relevant_result", jawab bahwa informasi tidak ada di dokumen.
    - Gunakan content_type="table" untuk pertanyaan angka tabel, "formula" untuk rumus, "figure" untuk grafik/denah.

    Args:
        query: Kata kunci atau pertanyaan penelusuran (disarankan dalam bahasa Inggris).
        top_k: Jumlah hasil terbaik yang dikembalikan (default: 5).
        content_type: Filter jenis konten: "table" (tabel), "formula" (rumus/LaTeX), "figure" (deskripsi grafik/gambar), atau None (semua).
        page: Filter nomor halaman tertentu di PDF asli (1-22), atau None.

    Returns:
        dict berisi 'status' ('success' atau 'no_relevant_result'), 'message', 'query', 'count', dan daftar 'results'.
        Setiap item memuat: chunk_id, text, page_number, page_numbers, heading_path, content_types, image_path, similarity, fts_rank, rrf_score.
    """
    if not query or not query.strip():
        return {
            "status": "error",
            "message": "Query tidak boleh kosong.",
            "results": []
        }

    sb = get_supabase_client()
    try:
        query_vec = get_embedding(query.strip())
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Gagal menghasilkan vector embedding query: {exc}",
            "results": []
        }

    ct = content_type.lower().strip() if content_type else None
    rpc_params = {
        "p_query_text": query.strip(),
        "p_query_embedding": query_vec,
        "p_match_count": max(1, top_k),
        "p_rrf_k": 60,
        "p_filter_source": None,
        "p_filter_content_type": None,
        "p_filter_page_number": page,
        "p_filter_has_latex": True if ct == "formula" else None,
        "p_filter_has_table": True if ct == "table" else None,
        "p_filter_has_figure_description": True if ct == "figure" else None,
    }

    try:
        res = sb.rpc("match_knowledge_chunks_hybrid", rpc_params).execute()
        rows = res.data or []
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Gagal mengeksekusi match_knowledge_chunks_hybrid RPC: {exc}",
            "results": []
        }

    # Aturan relevansi (BUKAN hanya similarity):
    # status "no_relevant_result" HANYA jika similarity tertinggi < 0.40 DAN semua fts_rank = 0.
    max_sim = max((r.get("similarity") or 0.0) for r in rows) if rows else 0.0
    has_any_fts = any((r.get("fts_rank") or 0.0) > 0.0 for r in rows) if rows else False

    is_relevant = (max_sim >= RELEVANCE_SIMILARITY_THRESHOLD) or has_any_fts
    status = "success" if is_relevant else "no_relevant_result"
    message = (
        "Ditemukan hasil yang relevan."
        if is_relevant
        else (
            f"Tidak ada hasil yang relevan (similarity tertinggi {max_sim:.4f} < "
            f"{RELEVANCE_SIMILARITY_THRESHOLD:.2f} dan semua fts_rank = 0). Informasi kemungkinan tidak ada di dokumen."
        )
    )

    formatted_results = []
    for r in rows:
        meta = r.get("metadata") or {}
        pg_no = r.get("page_number")
        pg_nums = meta.get("page_numbers") or ([pg_no] if pg_no is not None else [])
        c_types = meta.get("content_types") or (
            [r.get("content_type")] if r.get("content_type") else ["text"]
        )

        formatted_results.append({
            "chunk_id": r.get("chunk_id"),
            "text": r.get("content"),
            "page_number": pg_no,
            "page_numbers": pg_nums,
            "heading_path": r.get("heading_path"),
            "content_types": c_types,
            "image_path": r.get("image_path") or [],
            "similarity": r.get("similarity"),
            "fts_rank": r.get("fts_rank"),
            "rrf_score": r.get("rrf_score"),
        })

    return {
        "status": status,
        "message": message,
        "query": query,
        "count": len(formatted_results),
        "results": formatted_results,
    }


@mcp.tool()
def get_chunk(chunk_id: str) -> dict:
    """Ambil satu chunk spesifik berdasarkan chunk_id.

    Kapan digunakan:
    Gunakan tool ini ketika Anda sudah mengetahui chunk_id tertentu (misal: 'chunk_008') dari penelusuran sebelumnya
    atau saat ingin memeriksa detail lengkap isi suatu chunk tanpa melakukan pencarian ulang.

    Args:
        chunk_id: Identifier chunk, misal 'chunk_008' atau 'chunk_027'.

    Returns:
        dict berisi status dan objek chunk lengkap (chunk_id, text, page_number, page_numbers, heading_path,
        content_types, image_path, similarity, fts_rank, rrf_score).
    """
    if not chunk_id or not chunk_id.strip():
        return {
            "status": "error",
            "message": "chunk_id tidak boleh kosong.",
            "chunk": None
        }

    sb = get_supabase_client()
    try:
        res = (
            sb.table("knowledge_chunks")
            .select("*")
            .eq("chunk_id", chunk_id.strip())
            .execute()
        )
        if not res.data:
            return {
                "status": "not_found",
                "message": f"Chunk dengan ID '{chunk_id}' tidak ditemukan di database.",
                "chunk": None,
            }

        r = res.data[0]
        meta = r.get("metadata") or {}
        pg_no = r.get("page_number")
        pg_nums = meta.get("page_numbers") or ([pg_no] if pg_no is not None else [])
        c_types = meta.get("content_types") or (
            [r.get("content_type")] if r.get("content_type") else ["text"]
        )

        return {
            "status": "success",
            "chunk": {
                "chunk_id": r.get("chunk_id"),
                "text": r.get("content"),
                "page_number": pg_no,
                "page_numbers": pg_nums,
                "heading_path": r.get("heading_path"),
                "content_types": c_types,
                "image_path": r.get("image_path") or [],
                "similarity": None,
                "fts_rank": None,
                "rrf_score": None,
            },
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Gagal mengambil chunk '{chunk_id}': {exc}",
            "chunk": None,
        }


@mcp.tool()
def get_page_context(page: int) -> dict:
    """Ambil semua chunk yang mencakup halaman tertentu di PDF asli (urut berdasarkan chunk_index).

    Kapan digunakan:
    Gunakan tool ini ketika Anda ingin membaca konteks lengkap dari suatu halaman PDF secara menyeluruh
    (misal setelah menemukan referensi halaman dari pencarian atau memeriksa konteks halaman sekitar).

    Args:
        page: Nomor halaman PDF asli yang ingin dibaca (1-22).

    Returns:
        dict berisi status, nomor halaman, jumlah chunk, dan daftar semua chunk pada halaman tersebut secara kronologis.
        Setiap chunk memuat: chunk_id, text, page_number, page_numbers, heading_path, content_types, image_path,
        similarity, fts_rank, rrf_score.
    """
    if not isinstance(page, int) or page < 1:
        return {
            "status": "error",
            "message": f"Nomor halaman '{page}' tidak valid. Harus integer >= 1.",
            "page": page,
            "chunks": []
        }

    sb = get_supabase_client()
    try:
        # Filter chunk yang mencakup halaman ini pada array metadata->page_numbers
        res = (
            sb.table("knowledge_chunks")
            .select("*")
            .filter("metadata->page_numbers", "cs", f"[{page}]")
            .order("chunk_index")
            .execute()
        )
        rows = res.data or []
        if not rows:
            # Fallback ke kolom primer page_number jika filter jsonb kosong
            res2 = (
                sb.table("knowledge_chunks")
                .select("*")
                .eq("page_number", page)
                .order("chunk_index")
                .execute()
            )
            rows = res2.data or []

        chunks = []
        for r in rows:
            meta = r.get("metadata") or {}
            pg_no = r.get("page_number")
            pg_nums = meta.get("page_numbers") or ([pg_no] if pg_no is not None else [])
            c_types = meta.get("content_types") or (
                [r.get("content_type")] if r.get("content_type") else ["text"]
            )

            chunks.append({
                "chunk_id": r.get("chunk_id"),
                "text": r.get("content"),
                "page_number": pg_no,
                "page_numbers": pg_nums,
                "heading_path": r.get("heading_path"),
                "content_types": c_types,
                "image_path": r.get("image_path") or [],
                "similarity": None,
                "fts_rank": None,
                "rrf_score": None,
            })

        return {
            "status": "success",
            "page": page,
            "count": len(chunks),
            "chunks": chunks,
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Gagal mengambil page context untuk halaman {page}: {exc}",
            "page": page,
            "chunks": [],
        }


if __name__ == "__main__":
    mcp.run(transport="stdio")
