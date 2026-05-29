-- =====================================================
-- Verification Queries - Radio Transcription Search
-- =====================================================
-- Purpose:
-- These queries were used to validate the pg_trgm indexes
-- (idx_calls_transcription_trgm and idx_calls_talkgroup_name_trgm)
-- during initial deployment in May 2026.
--
-- Database side status: COMPLETE
-- Both indexes are live and being used in production.
--
-- You can safely re-run these queries in the future for
-- performance spot-checks. Use the light versions when possible.
-- =====================================================

-- -----------------------------------------------------
-- Light verification queries (preferred)
-- -----------------------------------------------------

-- How many calls contain "henry"?
SELECT COUNT(*) 
FROM calls 
WHERE transcription ILIKE '%henry%';

-- How many calls are from Auburn-related talkgroups?
SELECT COUNT(*) 
FROM calls 
WHERE talkgroup_name ILIKE '%Auburn%';

-- -----------------------------------------------------
-- Realistic production-style query (what the app actually runs)
-- -----------------------------------------------------
SELECT filename, talkgroup_name, start_time, transcription
FROM calls
WHERE transcription ILIKE '%henry%'
ORDER BY start_time DESC
LIMIT 30;

-- -----------------------------------------------------
-- Heavy diagnostic versions (use sparingly - higher cost)
-- -----------------------------------------------------
-- EXPLAIN ANALYZE
-- SELECT COUNT(*) 
-- FROM calls 
-- WHERE transcription ILIKE '%henry%';
--
-- EXPLAIN ANALYZE
-- SELECT COUNT(*) 
-- FROM calls 
-- WHERE talkgroup_name ILIKE '%Auburn%';