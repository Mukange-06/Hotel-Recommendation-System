# =============================================================================
# StayFinder — main.py
# FastAPI backend: search endpoint + analytics query endpoints
# =============================================================================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os

from db  import run_query
from rag import get_recommendations

# =============================================================================
# APP SETUP
# =============================================================================

app = FastAPI(
    title="StayFinder API",
    description="Hotel Recommendation System — RAG Pipeline",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # tighten this in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# SCHEMAS
# =============================================================================

class SearchRequest(BaseModel):
    query:    str
    category: Optional[str] = None   # luxury | boutique | business | budget | None

# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.get("/")
def root():
    return {"status": "ok", "project": "StayFinder — Hotel Recommendation System"}

@app.get("/health")
def health():
    return {"status": "healthy"}

# =============================================================================
# SEARCH — RAG pipeline
# =============================================================================

@app.post("/recommend")
async def recommend(req: SearchRequest):
    """
    Accepts a natural-language query and an optional category filter.
    Returns an AI-generated summary and a ranked list of matching hotels.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    try:
        result = await get_recommendations(req.query, req.category)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# ANALYTICS — one endpoint per SQL query (mirrors queries.sql)
# =============================================================================

# -- [AGG-1] Revenue summary by hotel category --------------------------------
@app.get("/query/agg1")
def query_agg1():
    sql = """
        SELECT
            h.category,
            COUNT(b.booking_id)              AS total_bookings,
            ROUND(SUM(b.total_price), 2)     AS total_revenue_usd,
            ROUND(AVG(b.total_price), 2)     AS avg_booking_value_usd,
            ROUND(MIN(b.total_price), 2)     AS min_booking_usd,
            ROUND(MAX(b.total_price), 2)     AS max_booking_usd
        FROM   bookings b
        JOIN   hotels   h ON h.hotel_id = b.hotel_id
        WHERE  b.status IN ('confirmed', 'completed')
        GROUP  BY h.category
        ORDER  BY total_revenue_usd DESC;
    """
    return {"rows": run_query(sql)}


# -- [AGG-2] Average review rating per city -----------------------------------
@app.get("/query/agg2")
def query_agg2():
    sql = """
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
    """
    return {"rows": run_query(sql)}


# -- [JOIN-1] Full booking ledger ---------------------------------------------
@app.get("/query/join1")
def query_join1():
    sql = """
        SELECT
            b.booking_id,
            b.check_in_date,
            b.check_out_date,
            (b.check_out_date - b.check_in_date)         AS nights,
            u.first_name || ' ' || u.last_name           AS guest_name,
            u.nationality,
            h.name                                       AS hotel_name,
            h.city,
            h.category                                   AS hotel_category,
            rt.type_name                                 AS room_type,
            b.num_guests,
            b.total_price,
            b.status
        FROM   bookings   b
        JOIN   users      u  ON u.user_id       = b.user_id
        JOIN   hotels     h  ON h.hotel_id      = b.hotel_id
        JOIN   room_types rt ON rt.room_type_id = b.room_type_id
        ORDER  BY b.check_in_date DESC
        LIMIT  50;
    """
    return {"rows": run_query(sql)}


# -- [JOIN-2] Top-reviewed hotels ---------------------------------------------
@app.get("/query/join2")
def query_join2():
    sql = """
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
        GROUP  BY h.hotel_id, h.name, h.city, h.category,
                  h.star_rating, h.price_per_night
        ORDER  BY avg_review_rating DESC, total_helpful_votes DESC
        LIMIT  20;
    """
    return {"rows": run_query(sql)}


# -- [SUB-1] Hotels above average price ---------------------------------------
@app.get("/query/sub1")
def query_sub1():
    sql = """
        SELECT
            hotel_id,
            name,
            city,
            category,
            star_rating,
            price_per_night,
            ROUND(price_per_night - (SELECT AVG(price_per_night) FROM hotels), 2)
                AS premium_over_avg_usd
        FROM   hotels
        WHERE  price_per_night > (SELECT AVG(price_per_night) FROM hotels)
        ORDER  BY price_per_night DESC;
    """
    return {"rows": run_query(sql)}


# -- [SUB-2] Users who have never booked --------------------------------------
@app.get("/query/sub2")
def query_sub2():
    sql = """
        SELECT
            u.user_id,
            u.first_name || ' ' || u.last_name  AS full_name,
            u.email,
            u.nationality,
            u.created_at                         AS registered_on
        FROM   users u
        WHERE  NOT EXISTS (
            SELECT 1 FROM bookings b WHERE b.user_id = u.user_id
        )
        ORDER  BY u.created_at DESC;
    """
    return {"rows": run_query(sql)}


# -- [CTE-1] Monthly revenue trend --------------------------------------------
@app.get("/query/cte1")
def query_cte1():
    sql = """
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
                revenue_usd - LAG(revenue_usd) OVER (ORDER BY booking_month),
                2
            ) AS mom_revenue_change_usd
        FROM   monthly_revenue
        ORDER  BY booking_month;
    """
    return {"rows": run_query(sql)}


# -- [CTE-2] Hotel tier classification ----------------------------------------
@app.get("/query/cte2")
def query_cte2():
    sql = """
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
            SELECT *, NTILE(4) OVER (ORDER BY avg_revenue_per_booking DESC)
                AS revenue_tier
            FROM hotel_revenue
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
            END AS revenue_tier_label
        FROM   tiered
        ORDER  BY avg_revenue_per_booking DESC;
    """
    return {"rows": run_query(sql)}


# -- [WIN-1] Booking revenue ranked within category ---------------------------
@app.get("/query/win1")
def query_win1():
    sql = """
        SELECT
            b.booking_id,
            h.category,
            h.name                                               AS hotel_name,
            u.first_name || ' ' || u.last_name                  AS guest_name,
            rt.type_name                                         AS room_type,
            b.total_price,
            RANK() OVER (
                PARTITION BY h.category
                ORDER BY b.total_price DESC
            )                                                    AS rank_in_category,
            ROUND(AVG(b.total_price) OVER (PARTITION BY h.category), 2)
                                                                 AS category_avg_price
        FROM   bookings   b
        JOIN   hotels     h  ON h.hotel_id      = b.hotel_id
        JOIN   users      u  ON u.user_id       = b.user_id
        JOIN   room_types rt ON rt.room_type_id = b.room_type_id
        WHERE  b.status IN ('confirmed', 'completed')
        ORDER  BY h.category, rank_in_category
        LIMIT  60;
    """
    return {"rows": run_query(sql)}


# -- [WIN-2] Running total of bookings per user -------------------------------
@app.get("/query/win2")
def query_win2():
    sql = """
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
            ROUND(SUM(b.total_price) OVER (
                PARTITION BY u.user_id
                ORDER BY b.check_in_date
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ), 2)                                AS running_total_spent_usd
        FROM   bookings b
        JOIN   users    u ON u.user_id  = b.user_id
        JOIN   hotels   h ON h.hotel_id = b.hotel_id
        WHERE  b.status IN ('confirmed', 'completed')
        ORDER  BY u.user_id, b.check_in_date
        LIMIT  60;
    """
    return {"rows": run_query(sql)}


# =============================================================================
# RUN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)