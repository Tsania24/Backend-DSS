-- =============================================================================
-- 003_fix_hybrid.sql
-- -----------------------------------------------------------------------------
-- Migrasi Hybrid Search RPC dengan Reciprocal Rank Fusion (RRF):
-- 1. Memastikan kolom fts (tsvector) dan GIN index tersedia pada knowledge_chunks
-- 2. CREATE OR REPLACE FUNCTION match_knowledge_chunks_hybrid:
--    - Menggunakan websearch_to_tsquery('english', query) untuk FTS yang fleksibel
--    - Menggabungkan semantic search (pgvector) dan FTS via FULL OUTER JOIN
--    - Menghitung Reciprocal Rank Fusion: 1/(k + rank_sem) + 1/(k + rank_fts)
--    - Mendukung filtering metadata via flag:
--        * p_filter_has_latex (boolean)
--        * p_filter_has_table (boolean)
--        * p_filter_has_figure_description (boolean)
--      serta p_filter_source, p_filter_content_type, p_filter_page_number
--    - TIDAK menggunakan DROP (idempotent dan aman)
--
-- Jalankan file ini di Supabase SQL Editor.
-- =============================================================================

-- 1. PASTIKAN KOLOM TSVECTOR DAN GIN INDEX TERSEDIA
ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS fts tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(heading_path, '') || ' ' || coalesce(content, ''))
    ) STORED;

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_fts
    ON knowledge_chunks 
    USING gin (fts);

-- 2. HAPUS OVERLOAD LAMA (7 PARAMETER) UNTUK MENCEGAH POSTGREST AMBIGUITY (PGRST203)
DROP FUNCTION IF EXISTS match_knowledge_chunks_hybrid(text, vector, integer, integer, text, text, integer);

-- 3. DEFINISI FUNGSI HYBRID SEARCH DENGAN RRF & FLAG FILTERING (10 PARAMETER)
CREATE OR REPLACE FUNCTION match_knowledge_chunks_hybrid(
    p_query_text text,
    p_query_embedding vector(1024),
    p_match_count integer DEFAULT 5,
    p_rrf_k integer DEFAULT 60,
    p_filter_source text DEFAULT NULL,
    p_filter_content_type text DEFAULT NULL,
    p_filter_page_number integer DEFAULT NULL,
    p_filter_has_latex boolean DEFAULT NULL,
    p_filter_has_table boolean DEFAULT NULL,
    p_filter_has_figure_description boolean DEFAULT NULL
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
DECLARE
    v_tsquery tsquery;
BEGIN
    -- Konversi query teks menggunakan websearch_to_tsquery untuk parsing operator penelusuran web
    IF p_query_text IS NOT NULL AND trim(p_query_text) <> '' THEN
        v_tsquery := websearch_to_tsquery('english', p_query_text);
    ELSE
        v_tsquery := NULL;
    END IF;

    RETURN QUERY
    WITH 
    -- 1. Kandidat Semantic Search (Cosine Similarity top 30)
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
          AND (p_filter_has_latex IS NULL OR coalesce((kc.metadata->>'has_latex')::boolean, false) = p_filter_has_latex)
          AND (p_filter_has_table IS NULL OR coalesce((kc.metadata->>'has_table')::boolean, false) = p_filter_has_table)
          AND (p_filter_has_figure_description IS NULL OR coalesce((kc.metadata->>'has_figure_description')::boolean, false) = p_filter_has_figure_description)
          AND kc.embedding IS NOT NULL
        ORDER BY kc.embedding <=> p_query_embedding
        LIMIT 30
    ),
    -- 2. Kandidat Full-Text Search (ts_rank_cd top 30)
    fts_candidates AS (
        SELECT 
            kc.id,
            CASE 
                WHEN v_tsquery IS NOT NULL THEN ts_rank_cd(kc.fts, v_tsquery)::double precision
                ELSE 0.0::double precision
            END AS rank_score,
            ROW_NUMBER() OVER (
                ORDER BY 
                    CASE 
                        WHEN v_tsquery IS NOT NULL THEN ts_rank_cd(kc.fts, v_tsquery)::double precision
                        ELSE 0.0::double precision
                    END DESC
            ) AS rank
        FROM knowledge_chunks kc
        JOIN knowledge_documents kd ON kc.document_id = kd.id
        WHERE (p_filter_source IS NULL OR kd.source = p_filter_source)
          AND (p_filter_content_type IS NULL OR kc.content_type = p_filter_content_type)
          AND (p_filter_page_number IS NULL OR kc.page_number = p_filter_page_number)
          AND (p_filter_has_latex IS NULL OR coalesce((kc.metadata->>'has_latex')::boolean, false) = p_filter_has_latex)
          AND (p_filter_has_table IS NULL OR coalesce((kc.metadata->>'has_table')::boolean, false) = p_filter_has_table)
          AND (p_filter_has_figure_description IS NULL OR coalesce((kc.metadata->>'has_figure_description')::boolean, false) = p_filter_has_figure_description)
          AND (v_tsquery IS NOT NULL AND kc.fts @@ v_tsquery)
        ORDER BY rank_score DESC
        LIMIT 30
    ),
    -- 3. Fusi Skor RRF melalui FULL OUTER JOIN
    combined_scores AS (
        SELECT 
            coalesce(s.id, f.id) AS id,
            coalesce(s.sim, 0.0::double precision) AS similarity,
            coalesce(f.rank_score, 0.0::double precision) AS fts_rank,
            (coalesce(1.0 / (p_rrf_k + s.rank), 0.0::double precision) + coalesce(1.0 / (p_rrf_k + f.rank), 0.0::double precision)) AS rrf_score
        FROM semantic_candidates s
        FULL OUTER JOIN fts_candidates f ON s.id = f.id
    )
    -- 4. Pengurutan akhir berdasarkan RRF score
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
