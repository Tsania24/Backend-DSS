-- =============================================================================
-- 002_hybrid_search_rrf.sql
-- -----------------------------------------------------------------------------
-- Migrasi Hybrid Search menggunakan Reciprocal Rank Fusion (RRF):
-- 1. Tambah kolom Full-Text Search (tsvector) pada knowledge_chunks
-- 2. Buat GIN index untuk pencarian teks cepat
-- 3. Buat fungsi RPC BARU: match_knowledge_chunks_hybrid
--    Menggabungkan Semantic Search (pgvector HNSW) dan Full-Text Search (FTS)
--    menggunakan Reciprocal Rank Fusion (RRF):
--        RRF_Score = 1/(k + rank_semantic) + 1/(k + rank_fts)
--    * Fungsi match_knowledge_chunks_v2 lama TIDAK ditimpa *
--
-- Jalankan file ini di Supabase SQL Editor setelah disetujui.
-- =============================================================================

-- 1. TAMBAH KOLOM TSVECTOR (GENERATED STORED)
-- Menggabungkan heading_path dan content dengan konfigurasi bahasa inggris
ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS fts tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(heading_path, '') || ' ' || coalesce(content, ''))
    ) STORED;

-- 2. BUAT GIN INDEX UNTUK FULL-TEXT SEARCH
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_fts
    ON knowledge_chunks 
    USING gin (fts);

-- 3. FUNGSI RPC BARU: match_knowledge_chunks_hybrid
CREATE OR REPLACE FUNCTION match_knowledge_chunks_hybrid(
    p_query_text text,
    p_query_embedding vector(1024),
    p_match_count integer DEFAULT 5,
    p_rrf_k integer DEFAULT 60,
    p_filter_source text DEFAULT NULL,
    p_filter_content_type text DEFAULT NULL,
    p_filter_page_number integer DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    document_id uuid,
    chunk_index integer,
    chunk_id text,
    source text,
    document_title text,
    page_number integer,
    heading_path text,
    content_type text,
    image_path text[],
    content text,
    content_hash text,
    metadata jsonb,
    similarity double precision,
    fts_rank double precision,
    rrf_score double precision
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH 
    -- 1. Semantic search kandidat (top 30 berdasarkan cosine distance)
    semantic_candidates AS (
        SELECT 
            kc.id,
            (1 - (kc.embedding <=> p_query_embedding)) AS sim,
            ROW_NUMBER() OVER (ORDER BY kc.embedding <=> p_query_embedding) AS rank
        FROM knowledge_chunks kc
        JOIN knowledge_documents kd ON kc.document_id = kd.id
        WHERE (p_filter_source IS NULL OR kd.source = p_filter_source)
          AND (p_filter_content_type IS NULL OR kc.content_type = p_filter_content_type)
          AND (p_filter_page_number IS NULL OR kc.page_number = p_filter_page_number)
          AND kc.embedding IS NOT NULL
        ORDER BY kc.embedding <=> p_query_embedding
        LIMIT 30
    ),
    -- 2. Full-text search kandidat (top 30 berdasarkan keyword rank)
    fts_candidates AS (
        SELECT 
            kc.id,
            ts_rank_cd(kc.fts, plainto_tsquery('english', p_query_text)) AS rank_score,
            ROW_NUMBER() OVER (ORDER BY ts_rank_cd(kc.fts, plainto_tsquery('english', p_query_text)) DESC) AS rank
        FROM knowledge_chunks kc
        JOIN knowledge_documents kd ON kc.document_id = kd.id
        WHERE (p_filter_source IS NULL OR kd.source = p_filter_source)
          AND (p_filter_content_type IS NULL OR kc.content_type = p_filter_content_type)
          AND (p_filter_page_number IS NULL OR kc.page_number = p_filter_page_number)
          AND kc.fts @@ plainto_tsquery('english', p_query_text)
        ORDER BY ts_rank_cd(kc.fts, plainto_tsquery('english', p_query_text)) DESC
        LIMIT 30
    ),
    -- 3. Penggabungan RRF
    combined_scores AS (
        SELECT 
            coalesce(s.id, f.id) AS id,
            coalesce(s.sim, 0.0) AS similarity,
            coalesce(f.rank_score, 0.0) AS fts_rank,
            (coalesce(1.0 / (p_rrf_k + s.rank), 0.0) + coalesce(1.0 / (p_rrf_k + f.rank), 0.0)) AS rrf_score
        FROM semantic_candidates s
        FULL OUTER JOIN fts_candidates f ON s.id = f.id
    )
    SELECT 
        kc.id,
        kc.document_id,
        kc.chunk_index,
        kc.chunk_id,
        kd.source,
        kd.title AS document_title,
        kc.page_number,
        kc.heading_path,
        kc.content_type,
        kc.image_path,
        kc.content,
        kc.content_hash,
        kc.metadata,
        cs.similarity,
        cs.fts_rank,
        cs.rrf_score
    FROM combined_scores cs
    JOIN knowledge_chunks kc ON cs.id = kc.id
    JOIN knowledge_documents kd ON kc.document_id = kd.id
    ORDER BY cs.rrf_score DESC
    LIMIT p_match_count;
END;
$$;
