-- =============================================================================
-- Hotel Recommendation System — RAG Pipeline
-- Milestone 3: Performance Evidence
-- Authors : Emmanuel Mukange (ZDA24B029), Raudhat Ramadhan (ZDA24B010)
-- Course  : Database Management Systems — IIT Madras Zanzibar
-- DBMS    : PostgreSQL 15+
-- Run     : psql -U <user> -d <database> -f performance.sql
--
-- Structure:
--   SECTION 1 — Baseline EXPLAIN ANALYZE (before indexes)
--   SECTION 2 — Index DDL (composite + partial)
--   SECTION 3 — Post-index EXPLAIN ANALYZE (same queries)
--   SECTION 4 — Stored Procedure: sp_refresh_hotel_rating_summary
-- =============================================================================


-- =============================================================================
-- SECTION 1 — SLOW QUERY BASELINES 
-- =============================================================================

DISCARD ALL;

-- ----------------------------------------------------------------------------
-- [SQ-1] AGG-2: Average review rating per city
-- ----------------------------------------------------------------------------

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    h.city,
    h.state,
    COUNT(r.review_id)               AS review_count,
    ROUND(AVG(r.rating), 2)          AS avg_rating,
    ROUND(MIN(r.rating), 2)          AS lowest_rating,
    ROUND(MAX(r.rating), 2)          AS highest_rating
FROM   reviews r
JOIN   hotels  h ON h.hotel_id = r.hotel_id
GROUP  BY h.city, h.state
HAVING COUNT(r.review_id) >= 5
ORDER  BY avg_rating DESC, review_count DESC;


-- ----------------------------------------------------------------------------
-- [SQ-2] JOIN-2: Top-reviewed hotels with star rating and helpful-vote totals
-- ----------------------------------------------------------------------------
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    h.hotel_id,
    h.name                               AS hotel_name,
    h.city,
    h.category,
    h.star_rating,
    h.price_per_night,
    COUNT(r.review_id)                   AS review_count,
    ROUND(AVG(r.rating), 2)              AS avg_review_rating,
    SUM(r.helpful_votes)                 AS total_helpful_votes
FROM   hotels  h
JOIN   reviews r ON r.hotel_id = h.hotel_id
GROUP  BY h.hotel_id, h.name, h.city, h.category, h.star_rating, h.price_per_night
ORDER  BY avg_review_rating DESC, total_helpful_votes DESC
LIMIT  20;


-- ----------------------------------------------------------------------------
-- [SQ-3] WIN-1 (filtered): High-value bookings ranked within category
-- ----------------------------------------------------------------------------
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    b.booking_id,
    h.category,
    h.name                                               AS hotel_name,
    b.total_price,
    RANK() OVER (
        PARTITION BY h.category
        ORDER BY b.total_price DESC
    )                                                    AS rank_in_category
FROM   bookings b
JOIN   hotels   h ON h.hotel_id = b.hotel_id
WHERE  b.status IN ('confirmed', 'completed')
ORDER  BY h.category, rank_in_category;


-- =============================================================================
-- SECTION 2 — INDEX DDL
-- =============================================================================

-- ----------------------------------------------------------------------------
-- [IDX-1] Composite index on reviews(hotel_id, rating)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_reviews_hotel_rating
    ON reviews (hotel_id, rating);

-- ----------------------------------------------------------------------------
-- [IDX-2] Partial index on bookings(hotel_id) WHERE status IN (...)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_bookings_hotel_status_partial
    ON bookings (hotel_id, total_price)
    WHERE status IN ('confirmed', 'completed');

-- ----------------------------------------------------------------------------
-- [IDX-3] Composite index on bookings(status, check_in_date)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_bookings_status_checkin
    ON bookings (status, check_in_date);

-- =============================================================================
-- SECTION 3 — POST-INDEX EXPLAIN ANALYZE (same queries, same data)
-- =============================================================================

SET enable_seqscan = OFF;

-- [SQ-1] After IDX-1
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    h.city,
    h.state,
    COUNT(r.review_id)               AS review_count,
    ROUND(AVG(r.rating), 2)          AS avg_rating,
    ROUND(MIN(r.rating), 2)          AS lowest_rating,
    ROUND(MAX(r.rating), 2)          AS highest_rating
FROM   reviews r
JOIN   hotels  h ON h.hotel_id = r.hotel_id
GROUP  BY h.city, h.state
HAVING COUNT(r.review_id) >= 5
ORDER  BY avg_rating DESC, review_count DESC;


-- [SQ-2] After IDX-1
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    h.hotel_id,
    h.name                               AS hotel_name,
    h.city,
    h.category,
    h.star_rating,
    h.price_per_night,
    COUNT(r.review_id)                   AS review_count,
    ROUND(AVG(r.rating), 2)              AS avg_review_rating,
    SUM(r.helpful_votes)                 AS total_helpful_votes
FROM   hotels  h
JOIN   reviews r ON r.hotel_id = h.hotel_id
GROUP  BY h.hotel_id, h.name, h.city, h.category, h.star_rating, h.price_per_night
ORDER  BY avg_review_rating DESC, total_helpful_votes DESC
LIMIT  20;


-- [SQ-3] After IDX-2
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    b.booking_id,
    h.category,
    h.name                                               AS hotel_name,
    b.total_price,
    RANK() OVER (
        PARTITION BY h.category
        ORDER BY b.total_price DESC
    )                                                    AS rank_in_category
FROM   bookings b
JOIN   hotels   h ON h.hotel_id = b.hotel_id
WHERE  b.status IN ('confirmed', 'completed')
ORDER  BY h.category, rank_in_category;

SET enable_seqscan = ON;


-- =============================================================================
-- SECTION 4 — STORED PROCEDURE
-- =============================================================================

-- Summary table (idempotent)
CREATE TABLE IF NOT EXISTS hotel_rating_summary (
    hotel_id            INT           PRIMARY KEY REFERENCES hotels(hotel_id) ON DELETE CASCADE,
    avg_rating          NUMERIC(3,2),
    review_count        INT,
    total_helpful_votes BIGINT,
    last_refreshed_at   TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Procedure
CREATE OR REPLACE PROCEDURE sp_refresh_hotel_rating_summary(p_hotel_id INT DEFAULT NULL)
LANGUAGE plpgsql
AS $$
DECLARE
    v_avg_rating          NUMERIC(3,2);
    v_review_count        INT;
    v_total_helpful_votes BIGINT;
    rec                   RECORD;
BEGIN
    -- -------------------------------------------------------------------------
    -- If a specific hotel_id is supplied, refresh only that hotel.
    -- If NULL is passed, loop over every hotel that has at least one review.
    -- -------------------------------------------------------------------------
    IF p_hotel_id IS NOT NULL THEN

        SELECT
            ROUND(AVG(rating)::NUMERIC, 2),
            COUNT(*),
            SUM(helpful_votes)
        INTO v_avg_rating, v_review_count, v_total_helpful_votes
        FROM reviews
        WHERE hotel_id = p_hotel_id;

        INSERT INTO hotel_rating_summary
            (hotel_id, avg_rating, review_count, total_helpful_votes, last_refreshed_at)
        VALUES
            (p_hotel_id, v_avg_rating, v_review_count, v_total_helpful_votes, now())
        ON CONFLICT (hotel_id) DO UPDATE
            SET avg_rating            = EXCLUDED.avg_rating,
                review_count          = EXCLUDED.review_count,
                total_helpful_votes   = EXCLUDED.total_helpful_votes,
                last_refreshed_at     = EXCLUDED.last_refreshed_at;

        RAISE NOTICE 'Refreshed hotel_id=% → avg_rating=%, reviews=%, helpful_votes=%',
            p_hotel_id, v_avg_rating, v_review_count, v_total_helpful_votes;

    ELSE

        FOR rec IN
            SELECT DISTINCT hotel_id FROM reviews
        LOOP
            SELECT
                ROUND(AVG(rating)::NUMERIC, 2),
                COUNT(*),
                SUM(helpful_votes)
            INTO v_avg_rating, v_review_count, v_total_helpful_votes
            FROM reviews
            WHERE hotel_id = rec.hotel_id;

            INSERT INTO hotel_rating_summary
                (hotel_id, avg_rating, review_count, total_helpful_votes, last_refreshed_at)
            VALUES
                (rec.hotel_id, v_avg_rating, v_review_count, v_total_helpful_votes, now())
            ON CONFLICT (hotel_id) DO UPDATE
                SET avg_rating            = EXCLUDED.avg_rating,
                    review_count          = EXCLUDED.review_count,
                    total_helpful_votes   = EXCLUDED.total_helpful_votes,
                    last_refreshed_at     = EXCLUDED.last_refreshed_at;
        END LOOP;

        RAISE NOTICE 'Full summary refresh complete.';

    END IF;
END;
$$;

-- =============================================================================
-- END OF performance.sql
-- =============================================================================