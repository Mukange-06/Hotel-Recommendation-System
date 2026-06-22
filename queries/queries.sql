-- =============================================================================
-- Hotel Recommendation System — RAG Pipeline
-- Milestone 1: SQL Queries
-- Authors : Emmanuel Mukange (ZDA24B029), Raudhat Ramadhan (ZDA24B010)
-- Course  : Database Management Systems — IIT Madras Zanzibar
-- DBMS    : PostgreSQL 15+
-- Run     : psql -U <user> -d <database> -f queries.sql
--
-- Coverage:
--   [AGG-1]  Aggregation  — Revenue summary by hotel category
--   [AGG-2]  Aggregation  — Average review rating per city with review count
--   [JOIN-1] Join         — Full booking details with hotel, user, and room type
--   [JOIN-2] Join         — Top-reviewed hotels with their star rating
--   [SUB-1]  Subquery     — Hotels with above-average price per night
--   [SUB-2]  Subquery     — Users who have never made a booking
--   [CTE-1]  CTE          — Monthly booking revenue trend
--   [CTE-2]  CTE          — Hotel tier classification by revenue per booking
--   [WIN-1]  Window fn    — Booking revenue ranked within each hotel category
--   [WIN-2]  Window fn    — Running total of bookings per user over time
-- =============================================================================

-- =============================================================================
-- [AGG-1]  AGGREGATION: Revenue summary by hotel category
-- Purpose : Shows total confirmed/completed revenue, average booking value,
--           and number of bookings broken down by hotel category.
--           Useful for understanding which market segment drives the most revenue.
-- =============================================================================
SELECT
    h.category,
    COUNT(b.booking_id)                              AS total_bookings,
    ROUND(SUM(b.total_price), 2)                     AS total_revenue_usd,
    ROUND(AVG(b.total_price), 2)                     AS avg_booking_value_usd,
    ROUND(MIN(b.total_price), 2)                     AS min_booking_usd,
    ROUND(MAX(b.total_price), 2)                     AS max_booking_usd
FROM   bookings b
JOIN   hotels   h ON h.hotel_id = b.hotel_id
WHERE  b.status IN ('confirmed', 'completed')
GROUP  BY h.category
ORDER  BY total_revenue_usd DESC;


-- =============================================================================
-- [AGG-2]  AGGREGATION: Average review rating per city with review count
-- Purpose : Identifies which cities have the best-reviewed hotels on average.
--           Filters to cities with at least 5 reviews to avoid statistical noise.
-- =============================================================================
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


-- =============================================================================
-- [JOIN-1] JOIN: Full booking details — hotel, guest, and room type in one row
-- Purpose : Produces a human-readable booking ledger suitable for a front-desk
--           report.  Joins four tables: bookings, users, hotels, room_types.
-- =============================================================================
SELECT
    b.booking_id,
    b.check_in_date,
    b.check_out_date,
    (b.check_out_date - b.check_in_date)             AS nights,
    u.first_name || ' ' || u.last_name               AS guest_name,
    u.nationality,
    h.name                                           AS hotel_name,
    h.city,
    h.category                                       AS hotel_category,
    rt.type_name                                     AS room_type,
    b.num_guests,
    b.total_price,
    b.status
FROM   bookings   b
JOIN   users      u  ON u.user_id      = b.user_id
JOIN   hotels     h  ON h.hotel_id     = b.hotel_id
JOIN   room_types rt ON rt.room_type_id = b.room_type_id
ORDER  BY b.check_in_date DESC
LIMIT  50;



-- ─────────────────────────────────────────────────────────────
-- [VIEW-1] Hotel Performance Summary
-- Shows each hotel with its average rating, total reviews,
-- total bookings, and total revenue in one place.
-- Useful for the RAG pipeline to quickly fetch hotel stats.
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW vw_hotel_performance AS
SELECT
    h.hotel_id,
    h.name                          AS hotel_name,
    h.city,
    h.star_rating,
    h.price_per_night,
    COUNT(DISTINCT r.review_id)     AS total_reviews,
    ROUND(AVG(r.rating), 2)         AS avg_rating,
    COUNT(DISTINCT b.booking_id)    AS total_bookings,
    ROUND(SUM(b.total_price), 2)    AS total_revenue
FROM hotels h
LEFT JOIN reviews  r ON r.hotel_id = h.hotel_id
LEFT JOIN bookings b ON b.hotel_id = h.hotel_id
GROUP BY
    h.hotel_id, h.name, h.city,
    h.star_rating, h.price_per_night;

-- Run it:
SELECT * FROM vw_hotel_performance
ORDER BY avg_rating DESC
LIMIT 10;


-- ─────────────────────────────────────────────────────────────
-- [VIEW-2] Active Bookings Full Detail
-- Shows every confirmed or completed booking with
-- guest name, hotel name, room type, dates, and price.
-- Avoids writing the same 4-table JOIN every time.
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW vw_active_bookings AS
SELECT
    b.booking_id,
    u.name                          AS guest_name,
    u.email,
    h.name                          AS hotel_name,
    h.city,
    rt.type_name                    AS room_type,
    b.check_in_date,
    b.check_out_date,
    (b.check_out_date - b.check_in_date) AS nights,
    b.total_price,
    b.status
FROM bookings b
JOIN users      u  ON u.user_id      = b.user_id
JOIN hotels     h  ON h.hotel_id     = b.hotel_id
JOIN room_types rt ON rt.room_type_id = b.room_type_id
WHERE b.status IN ('confirmed', 'completed');

-- Run it:
SELECT * FROM vw_active_bookings
ORDER BY check_in_date DESC
LIMIT 10;


-- =============================================================================
-- [JOIN-2] JOIN: Top-reviewed hotels with star rating and helpful-vote totals
-- Purpose : Combines hotels and reviews to surface the most positively reviewed
--           properties.  Useful as the final ranking layer in a RAG response.
-- =============================================================================
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


-- =============================================================================
-- [SUB-1]  SUBQUERY: Hotels priced above the overall average nightly rate
-- Purpose : Finds premium hotels whose base price exceeds the portfolio average.
--           Uses a scalar subquery in the WHERE clause.
-- =============================================================================
SELECT
    hotel_id,
    name,
    city,
    category,
    star_rating,
    price_per_night,
    ROUND(price_per_night - (SELECT AVG(price_per_night) FROM hotels), 2) AS premium_over_avg_usd
FROM   hotels
WHERE  price_per_night > (SELECT AVG(price_per_night) FROM hotels)
ORDER  BY price_per_night DESC;


-- =============================================================================
-- [SUB-2]  SUBQUERY: Users who have never placed a booking (window-shoppers)
-- Purpose : Identifies registered users with zero bookings using a correlated
--           NOT EXISTS subquery — more efficient than NOT IN on NULLable FKs.
-- =============================================================================
SELECT
    u.user_id,
    u.first_name || ' ' || u.last_name  AS full_name,
    u.email,
    u.nationality,
    u.created_at                         AS registered_on
FROM   users u
WHERE  NOT EXISTS (
    SELECT 1
    FROM   bookings b
    WHERE  b.user_id = u.user_id
)
ORDER  BY u.created_at DESC;


-- =============================================================================
-- [CTE-1]  CTE: Monthly booking revenue trend
-- Purpose : Uses a CTE to isolate the monthly aggregation step, then the outer
--           query computes month-over-month revenue change.  Useful for trend
--           analysis in a business intelligence dashboard.
-- =============================================================================
WITH monthly_revenue AS (
    SELECT
        DATE_TRUNC('month', b.check_in_date)::DATE  AS booking_month,
        COUNT(b.booking_id)                          AS bookings,
        ROUND(SUM(b.total_price), 2)                 AS revenue_usd
    FROM   bookings b
    WHERE  b.status IN ('confirmed', 'completed')
    GROUP  BY DATE_TRUNC('month', b.check_in_date)
)
SELECT
    booking_month,
    bookings,
    revenue_usd,
    ROUND(
        revenue_usd
        - LAG(revenue_usd) OVER (ORDER BY booking_month),
        2
    )                                                AS mom_revenue_change_usd
FROM   monthly_revenue
ORDER  BY booking_month;


-- =============================================================================
-- [CTE-2]  CTE: Hotel tier classification by average revenue per booking
-- Purpose : Uses two CTEs — one to compute per-hotel revenue stats, another
--           to classify hotels into NTILE revenue tiers — to identify which
--           properties generate the highest per-booking yield.
-- =============================================================================
WITH hotel_revenue AS (
    SELECT
        h.hotel_id,
        h.name                           AS hotel_name,
        h.category,
        h.city,
        COUNT(b.booking_id)              AS booking_count,
        ROUND(AVG(b.total_price), 2)     AS avg_revenue_per_booking
    FROM   hotels  h
    JOIN   bookings b ON b.hotel_id = h.hotel_id
    WHERE  b.status IN ('confirmed', 'completed')
    GROUP  BY h.hotel_id, h.name, h.category, h.city
),
tiered AS (
    SELECT
        *,
        NTILE(4) OVER (ORDER BY avg_revenue_per_booking DESC) AS revenue_tier
    FROM   hotel_revenue
)
SELECT
    hotel_id,
    hotel_name,
    category,
    city,
    booking_count,
    avg_revenue_per_booking,
    CASE revenue_tier
        WHEN 1 THEN 'Platinum'
        WHEN 2 THEN 'Gold'
        WHEN 3 THEN 'Silver'
        ELSE       'Bronze'
    END                                  AS revenue_tier_label
FROM   tiered
ORDER  BY avg_revenue_per_booking DESC;


-- =============================================================================
-- [WIN-1]  WINDOW FUNCTION: Booking revenue ranked within each hotel category
-- Purpose : Uses RANK() to assign a revenue rank to every booking within its
--           hotel's category partition, allowing cross-category comparison of
--           the highest-value bookings in each segment.
-- =============================================================================
SELECT
    b.booking_id,
    h.category,
    h.name                                               AS hotel_name,
    u.first_name || ' ' || u.last_name                   AS guest_name,
    rt.type_name                                         AS room_type,
    b.total_price,
    RANK() OVER (
        PARTITION BY h.category
        ORDER BY b.total_price DESC
    )                                                    AS rank_in_category,
    ROUND(AVG(b.total_price) OVER (PARTITION BY h.category), 2) AS category_avg_price
FROM   bookings   b
JOIN   hotels     h  ON h.hotel_id      = b.hotel_id
JOIN   users      u  ON u.user_id       = b.user_id
JOIN   room_types rt ON rt.room_type_id = b.room_type_id
WHERE  b.status IN ('confirmed', 'completed')
ORDER  BY h.category, rank_in_category;


-- =============================================================================
-- [WIN-2]  WINDOW FUNCTION: Running total of bookings per user over time
-- Purpose : Uses SUM() as a window function to compute a per-user cumulative
--           booking count ordered by check-in date.  Reveals engagement patterns
--           and helps identify loyal repeat customers.
-- =============================================================================
SELECT
    u.user_id,
    u.first_name || ' ' || u.last_name   AS guest_name,
    u.nationality,
    b.booking_id,
    b.check_in_date,
    h.name                               AS hotel_name,
    b.total_price,
    COUNT(b.booking_id) OVER (
        PARTITION BY u.user_id
        ORDER BY b.check_in_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )                                    AS running_booking_count,
    SUM(b.total_price) OVER (
        PARTITION BY u.user_id
        ORDER BY b.check_in_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )                                    AS running_total_spent_usd
FROM   bookings b
JOIN   users    u ON u.user_id  = b.user_id
JOIN   hotels   h ON h.hotel_id = b.hotel_id
WHERE  b.status IN ('confirmed', 'completed')
ORDER  BY u.user_id, b.check_in_date;


-- =============================================================================
-- [CTE-3] Most Luxurious Hotels — Top 5 by Price with Review Stats
-- =============================================================================
WITH ranked_hotels AS (
    SELECT
        h.hotel_id,
        h.name                           AS hotel_name,
        h.city,
        h.category,
        h.star_rating,
        h.price_per_night,
        h.amenities,
        ROUND(AVG(r.rating), 2)          AS avg_review_rating,
        COUNT(r.review_id)               AS review_count,
        SUM(r.helpful_votes)             AS total_helpful_votes,
        RANK() OVER (ORDER BY h.price_per_night DESC) AS price_rank
    FROM   hotels h
    LEFT JOIN reviews r ON r.hotel_id = h.hotel_id
    GROUP  BY h.hotel_id, h.name, h.city, h.category,
              h.star_rating, h.price_per_night, h.amenities
)
SELECT
    price_rank,
    hotel_name,
    city,
    category,
    star_rating,
    price_per_night,
    avg_review_rating,
    review_count,
    total_helpful_votes,
    amenities
FROM   ranked_hotels
WHERE  price_rank <= 5
ORDER  BY price_rank;


-- =============================================================================
-- [CTE-4] Best Budget Hotels — Top 5 by Lowest Price with Review Stats
-- =============================================================================
WITH ranked_hotels AS (
    SELECT
        h.hotel_id,
        h.name                           AS hotel_name,
        h.city,
        h.category,
        h.star_rating,
        h.price_per_night,
        h.amenities,
        ROUND(AVG(r.rating), 2)          AS avg_review_rating,
        COUNT(r.review_id)               AS review_count,
        SUM(r.helpful_votes)             AS total_helpful_votes,
        RANK() OVER (ORDER BY h.price_per_night ASC) AS price_rank
    FROM   hotels h
    LEFT JOIN reviews r ON r.hotel_id = h.hotel_id
    GROUP  BY h.hotel_id, h.name, h.city, h.category,
              h.star_rating, h.price_per_night, h.amenities
)
SELECT
    price_rank,
    hotel_name,
    city,
    category,
    star_rating,
    price_per_night,
    avg_review_rating,
    review_count,
    total_helpful_votes,
    amenities
FROM   ranked_hotels
WHERE  price_rank <= 5
ORDER  BY price_rank;
