-- =============================================================================
-- 001_setup_vector_and_schema.sql
-- -----------------------------------------------------------------------------
-- Migrasi Skema RAG Knowledge Base:
-- 1. Pastikan extension pgvector aktif
-- 2. Pastikan UNIQUE constraint pada knowledge_documents(source)
-- 3. Tambah kolom metadata ke knowledge_chunks: heading_path, content_type, image_path, chunk_id
-- 4. Set tipe kolom embedding ke vector(1024) agar kompatibel dengan qwen3-embedding:0.6b
-- 5. Tambah UNIQUE constraint pada knowledge_chunks(document_id, chunk_index) untuk idempotensi upsert
-- 6. Index HNSW untuk cosine distance (vector_cosine_ops)
-- 7. Index B-tree untuk performa filtering metadata
-- 8. Fungsi RPC BARU: match_knowledge_chunks_v2 (dengan filter source, content_type, page_number)
--    * Fungsi match_knowledge_chunks lama TIDAK ditimpa *
--
-- Jalankan file ini di Supabase SQL Editor setelah mengecek 000_check_schema.sql.
-- =============================================================================

-- 1. AKTIFKAN EXTENSION PGVECTOR
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. UNIQUE CONSTRAINT PADA knowledge_documents(source)
-- Diperlukan agar dokumen dapat di-upsert berdasarkan nama file sumber
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_knowledge_documents_source'
    ) THEN
        ALTER TABLE knowledge_documents 
            ADD CONSTRAINT uq_knowledge_documents_source UNIQUE (source);
    END IF;
END $$;

-- 3. TAMBAH KOLOM METADATA KE knowledge_chunks
ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS chunk_id text,
    ADD COLUMN IF NOT EXISTS heading_path text,
    ADD COLUMN IF NOT EXISTS content_type text,
    ADD COLUMN IF NOT EXISTS image_path text[];

-- 4. PASTIKAN TIPE DAN DIMENSI KOLOM EMBEDDING ADALAH vector(1024)
-- Model yang digunakan: qwen3-embedding:0.6b (1.024 dimensi).
-- Index HNSW membutuhkan dimensi tetap (fixed dimension).
ALTER TABLE knowledge_chunks 
    ALTER COLUMN embedding TYPE vector(1024) 
    USING embedding::vector(1024);

-- 5. UNIQUE CONSTRAINT PADA knowledge_chunks(document_id, chunk_index)
-- Menjamin idempotensi saat insert/upsert berulang
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_knowledge_chunks_doc_chunk'
    ) THEN
        ALTER TABLE knowledge_chunks 
            ADD CONSTRAINT uq_knowledge_chunks_doc_chunk UNIQUE (document_id, chunk_index);
    END IF;
END $$;

-- 6. INDEX HNSW UNTUK COSINE SIMILARITY
-- m = 16, ef_construction = 64 memberikan rasio recall/kecepatan optimal untuk 1024-dim
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding_hnsw
    ON knowledge_chunks 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 7. INDEX B-TREE UNTUK FILTERING METADATA
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_doc_id 
    ON knowledge_chunks (document_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_page_number 
    ON knowledge_chunks (page_number);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_content_type 
    ON knowledge_chunks (content_type);

-- 8. FUNGSI RPC BARU: match_knowledge_chunks_v2
-- Mendukung semantic search dengan multi-filter (source, content_type, page_number)
CREATE OR REPLACE FUNCTION match_knowledge_chunks_v2(
    p_query_embedding vector(1024),
    p_match_count integer DEFAULT 5,
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
    similarity double precision
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
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
        (1 - (kc.embedding <=> p_query_embedding)) AS similarity
    FROM knowledge_chunks kc
    JOIN knowledge_documents kd ON kc.document_id = kd.id
    WHERE (p_filter_source IS NULL OR kd.source = p_filter_source)
      AND (p_filter_content_type IS NULL OR kc.content_type = p_filter_content_type)
      AND (p_filter_page_number IS NULL OR kc.page_number = p_filter_page_number)
      AND kc.embedding IS NOT NULL
    ORDER BY kc.embedding <=> p_query_embedding
    LIMIT p_match_count;
END;
$$;
