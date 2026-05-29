-- =============================================================================
-- Supabase Postgres indexes for fast full-history search on radio transcriptions
-- IMPORTANT: Run these statements ONE AT A TIME in the SQL Editor
-- =============================================================================

-- DIAGNOSTIC: Run this first and tell me what it returns
SELECT table_name, column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'calls' 
ORDER BY ordinal_position;

-- If the above shows no rows, your table might be named differently (e.g. "Calls" or public.calls).
-- Paste the output here.

-- Step 1: Enable trigram extension
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Step 2: Index on transcription (run this by itself)
CREATE INDEX IF NOT EXISTS idx_calls_transcription_trgm
  ON calls USING gin (transcription gin_trgm_ops);

-- Step 3: Index on talkgroup_name (run this by itself)
CREATE INDEX IF NOT EXISTS idx_calls_talkgroup_name_trgm
  ON calls USING gin (talkgroup_name gin_trgm_ops);

-- =============================================================================
-- Verification (run in the same SQL Editor after the indexes finish building)
-- =============================================================================

-- Check that the indexes exist
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE tablename = 'calls' AND indexname LIKE '%trgm%';

-- Test query performance (look for "Bitmap Index Scan" or "Index Scan" in the plan)
EXPLAIN ANALYZE
SELECT filename, talkgroup_name, start_time, transcription
FROM calls
WHERE transcription ILIKE '%henry%'
ORDER BY start_time DESC
LIMIT 30;

-- Another realistic search
EXPLAIN ANALYZE
SELECT COUNT(*) 
FROM calls
WHERE transcription ILIKE '%dispatch%';

-- =============================================================================
-- Rollback (only if you ever need to remove the indexes)
-- =============================================================================
-- DROP INDEX IF EXISTS idx_calls_transcription_trgm;
-- DROP INDEX IF EXISTS idx_calls_talkgroup_name_trgm;
