-- =============================================================================
-- 000_check_schema.sql
-- -----------------------------------------------------------------------------
-- Query diagnostik untuk memeriksa skema database Supabase saat ini:
-- 1. Dimensi kolom embedding (format_type dari pg_attribute)
-- 2. Daftar seluruh kolom dan tipe data pada knowledge_documents & knowledge_chunks
-- 3. Daftar constraint (PRIMARY KEY, UNIQUE, FOREIGN KEY)
-- 4. Daftar index yang sudah ada
-- 5. Daftar fungsi RPC match yang sudah ada
--
-- Jalankan query ini di Supabase SQL Editor dan kirimkan hasilnya.
-- =============================================================================

-- 1. CEK TIPE DATA & DIMENSI KOLOM EMBEDDING
-- Menampilkan dimensi pasti (misal vector(1024) atau vector(1536) atau vector tanpa dimensi)
SELECT 
    c.table_name,
    c.column_name,
    c.data_type,
    c.udt_name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS full_type_with_dimension
FROM information_schema.columns c
JOIN pg_catalog.pg_class t ON t.relname = c.table_name
JOIN pg_catalog.pg_attribute a ON a.attrelid = t.oid AND a.attname = c.column_name
JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace AND n.nspname = c.table_schema
WHERE c.table_schema = 'public'
  AND c.table_name IN ('knowledge_chunks', 'knowledge_documents')
  AND c.column_name = 'embedding';

-- 2. DAFTAR SEMUA KOLOM & TIPE DATA
SELECT 
    table_name, 
    ordinal_position,
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public' 
  AND table_name IN ('knowledge_documents', 'knowledge_chunks')
ORDER BY table_name, ordinal_position;

-- 3. DAFTAR CONSTRAINT (PRIMARY KEY, UNIQUE, FOREIGN KEY)
SELECT 
    tc.table_name, 
    tc.constraint_name, 
    tc.constraint_type,
    kcu.column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu 
  ON tc.constraint_name = kcu.constraint_name 
  AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = 'public' 
  AND tc.table_name IN ('knowledge_documents', 'knowledge_chunks')
ORDER BY tc.table_name, tc.constraint_type, kcu.ordinal_position;

-- 4. DAFTAR INDEX YANG SUDAH TERDAFTAR
SELECT 
    tablename, 
    indexname, 
    indexdef
FROM pg_indexes
WHERE schemaname = 'public' 
  AND tablename IN ('knowledge_documents', 'knowledge_chunks')
ORDER BY tablename, indexname;

-- 5. DAFTAR FUNGSI RPC MATCH YANG ADA
SELECT 
    p.proname AS function_name,
    pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
    pg_catalog.pg_get_function_result(p.oid) AS return_type
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
  AND p.proname LIKE 'match_%';
