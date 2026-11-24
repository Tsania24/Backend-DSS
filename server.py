import asyncio
import hmac
import json
import os
import re
import time

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

load_dotenv(os.path.expanduser("~/.hermes/.env"))

HERMES_API_KEY = os.getenv("API_SERVER_KEY")
HERMES_CHAT_URL = "http://127.0.0.1:8642/v1/chat/completions"

SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or ""
SUPABASE_TABLE = os.getenv("SUPABASE_TABLE") or "Assets"

app = FastAPI(title="DSS Adaptive Building")
command_queue = asyncio.Queue()
ALLOWED_SURFACES = {"FLOOR", "WALL", "TABLE"}

_catalog_cache = {"items": [], "fetched_at": 0.0}
CACHE_TTL_SECONDS = 60.0


async def fetch_supabase_catalog() -> list[dict]:
    now = time.time()
    if _catalog_cache["items"] and (now - _catalog_cache["fetched_at"]) < CACHE_TTL_SECONDS:
        return _catalog_cache["items"]

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        print("[Supabase Warning] SUPABASE_URL atau SUPABASE_ANON_KEY belum diisi di .env")
        return _catalog_cache["items"]

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Accept": "application/json",
    }

    # Coba nama tabel dengan huruf kapital 'Assets' dan huruf kecil 'assets'
    candidate_tables = list(dict.fromkeys([SUPABASE_TABLE, "Assets", "assets"]))
    rows = None

    async with httpx.AsyncClient(timeout=15.0) as client:
        for tbl in candidate_tables:
            url = f"{SUPABASE_URL}/rest/v1/{tbl}?select=*"
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    rows = resp.json()
                    print(f"[Supabase Sync] Sukses dari tabel '{tbl}' ({len(rows)} baris)")
                    break
                else:
                    print(f"[Supabase Info] Tabel '{tbl}' HTTP {resp.status_code}")
            except Exception as exc:
                print(f"[Supabase Error] Tabel '{tbl}': {exc}")

    if rows is None:
        return _catalog_cache["items"]

    normalized = []
    for r in rows:
        aid = r.get("asset_code") or r.get("asset_id") or r.get("id")
        if not aid:
            continue
        normalized.append({
            "asset_id": str(aid),
            "name": r.get("name") or str(aid),
            "style": r.get("style") or "",
            "keyword": r.get("keyword") or "",
        })

    _catalog_cache["items"] = normalized
    _catalog_cache["fetched_at"] = now
    print(f"[Supabase Catalog] IDs aktif: {[x['asset_id'] for x in normalized]}")
    return normalized


@app.get("/")
async def root():
    return {"status": "online", "service": "DSS Adaptive Building"}


@app.get("/health")
async def health():
    catalog = await fetch_supabase_catalog()
    return {
        "status": "healthy",
        "supabase_connected": bool(catalog),
        "catalog_count": len(catalog),
        "asset_ids": [item["asset_id"] for item in catalog],
    }


@app.post("/api/mcp/spawn_furniture")
async def enqueue_furniture_command(request: Request):
    authorization = request.headers.get("Authorization", "")
    expected = f"Bearer {HERMES_API_KEY or ''}"

    if not HERMES_API_KEY or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

    data = await request.json()
    asset_id = data.get("asset_id")
    surface_label = str(data.get("surface_label", "")).upper()

    if not isinstance(asset_id, str) or not asset_id.strip():
        raise HTTPException(status_code=400, detail="asset_id must not be empty")
    if surface_label not in ALLOWED_SURFACES:
        raise HTTPException(status_code=400, detail="Invalid surface_label")

    instruction = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "spawn_furniture",
            "arguments": {"asset_id": asset_id, "surface_label": surface_label},
        },
    }
    await command_queue.put(json.dumps(instruction))
    print(f"[MCP -> Unity Queue] {asset_id} on {surface_label}")
    return {"status": "queued", "asset_id": asset_id, "surface_label": surface_label}


@app.post("/api/chat")
async def chat_with_hermes(request: Request):
    data = await request.json()
    user_prompt = data.get("prompt") or data.get("message") or ""
    spatial_data = data.get("spatial_context", {})

    if not isinstance(user_prompt, str) or not user_prompt.strip():
        raise HTTPException(status_code=400, detail="prompt must not be empty")

    catalog = await fetch_supabase_catalog()
    valid_ids = [item["asset_id"] for item in catalog]

    system_prompt = f"""
You are an adaptive building design agent for Mixed Reality.
You also have access to domain knowledge from the reference paper:
"A multi-objective reinforcement learning approach for furniture arrangement with optimal IEQ in multi-occupant offices"

Room spatial context: {json.dumps(spatial_data, ensure_ascii=False)}

Available Furniture Catalog (from Supabase):
{json.dumps(catalog, ensure_ascii=False)}

FURNITURE PLACEMENT RULES:
- When the user requests placing, adding, or arranging furniture (e.g. "taruh meja", "tempatkan kursi", "spawn desk", "taruh meja di lantai"):
  * Call the tool spawn_furniture(asset_id=..., surface_label=...). Do NOT merely output text or JSON.
  * You MUST select "asset_id" STRICTLY from this exact list of valid IDs: {json.dumps(valid_ids)}.
  * Example mapping: if the user asks for a desk/table ("meja"), pick a desk/table asset_id from the catalog (such as TAB_01_01); if chair ("kursi"), pick a chair asset_id (such as SEA_01_01); if lamp ("lampu"), pick LIG_01_01.
  * NEVER invent IDs like "wooden_table_01" or "table_wood". Use ONLY an ID from {json.dumps(valid_ids)}.
  * "surface_label" MUST be one of: FLOOR, WALL, or TABLE.
  * Do NOT claim an object was placed unless the tool confirms it was queued.

PAPER KNOWLEDGE & RETRIEVAL RULES:
- If the user asks about paper contents, Indoor Environmental Quality (IEQ), thermal/visual/acoustic comfort, Multi-Objective Reinforcement Learning (MORL), Q-learning, algorithms, Bellman equation, formulas, tables, figures, experimental setup (Office #1, Office #2), or evaluation results:
  * You MUST call the search tool search_documents(query=...) FIRST before answering.
  * Query formulation: translate the user query into concise English keywords (for example: "Bellman equation"). Always include specific technical terms, equation names, or identifiers (e.g. "Bellman equation", "Table 1 data synthesis", "NSGA-II MORL computation time"). Never send long conversational sentences.
  * Specific filters: use content_type ("formula", "table", "figure") or page when appropriate.
  * Multi-object coverage: Jika pertanyaan mencakup beberapa objek (mis. Office #1 dan Office #2), pastikan jawaban mencakup semuanya secara lengkap; jalankan search_documents tambahan bila perlu.
  * Additional context: use get_chunk(chunk_id) or get_page_context(page) if surrounding context is needed.

CITATIONS & FACTUAL GROUNDING:
- Sitasi halaman: gunakan seluruh page_numbers dari chunk yang dipakai kalimat itu dan sebutkan rentang lengkap beserta section-nya (mis. "[Hal. 9–10, Section 5.1]" atau "[Hal. 11–12, Section 5.1]").
- STRICT FACTUALITY & NO UNSTATED CAUSALITY:
  * Jangan menyimpulkan penyebab, alasan, atau hubungan kausal yang tidak dinyatakan paper. Jika paper hanya melaporkan sebuah hasil (mis. Office #2 punya reward lebih tinggi), katakan itu, dan nyatakan eksplisit bahwa paper tidak menjelaskan penyebabnya.
  * Jangan menyebut subjek (mis. "User #1") atau mekanisme yang tidak disebut teks hasil pencarian. Gunakan hanya fakta yang tertulis.
  * NEVER state metrics, numbers, or conclusions that are not present in the retrieved chunks.
- GRAPH ESTIMATIONS: Numeric values originating from Figure 8 to 13 (bar charts of 20 tests) are visual readings, not exact printed table data. You MUST explicitly describe them with the qualifier "sekitar" without invented units (e.g. "sekitar 95").
- NO RELEVANT RESULT & OUT-OF-DOMAIN:
  * If the user's question is out-of-domain / outside the scope of building design and does not exist in the document (e.g. cooking recipes, general trivia): answer briefly that the question is outside the scope of the system and is not in the document ("Pertanyaan ini di luar cakupan sistem dan tidak ada di dokumen"), WITHOUT calling spawn_furniture.
  * If search_documents returns status "no_relevant_result" (or no chunks match): state clearly that the requested information is not in the document.
  * Do NOT hallucinate, guess, or invent answers.

GENERAL:
- Respond in the language used by the user (e.g. Bahasa Indonesia), while keeping standard scientific terms intact.
"""

    payload = {
        "model": "hermes-agent",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                HERMES_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {HERMES_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        response.raise_for_status()

        result = response.json()
        content = (result["choices"][0]["message"].get("content") or "").strip()
        print(f"[Hermes Agent] {content}")

        return {"status": "success", "response": content, "message": content}

    except Exception as exc:
        print(f"[Hermes API Error] {type(exc).__name__}: {exc}")
        raise HTTPException(status_code=502, detail="Failed to communicate with Hermes Agent")


@app.get("/api/stream")
async def sse_stream(request: Request):
    async def event_generator():
        while not await request.is_disconnected():
            try:
                command = await asyncio.wait_for(command_queue.get(), timeout=1.0)
                yield {"data": command}
            except asyncio.TimeoutError:
                continue

    print("[SSE] Unity/MR client connected")
    return EventSourceResponse(event_generator())
