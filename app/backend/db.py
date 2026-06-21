# =============================================================================
# StayFinder — db.py
# PostgreSQL connection pool + query runner (psycopg v3)
# =============================================================================

import os
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CONNECTION POOL
# =============================================================================

_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=_build_dsn(),
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row}
        )
    return _pool


def _build_dsn() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    host     = os.getenv("DB_HOST",     "localhost")
    port     = os.getenv("DB_PORT",     "5432")
    dbname   = os.getenv("DB_NAME",     "stayfinder")
    user     = os.getenv("DB_USER",     "postgres")
    password = os.getenv("DB_PASSWORD", "")

    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


# =============================================================================
# QUERY RUNNER
# =============================================================================

def run_query(sql: str, params=None) -> list[dict]:
    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def run_write(sql: str, params=None) -> int:
    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount


def fetch_one(sql: str, params=None) -> dict | None:
    rows = run_query(sql, params)
    return rows[0] if rows else None


# =============================================================================
# HOTEL HELPERS (called by rag.py)
# =============================================================================

def get_hotels_by_ids(hotel_ids: list[int]) -> list[dict]:
    if not hotel_ids:
        return []

    sql = """
        SELECT
            h.hotel_id,
            h.name,
            h.city,
            h.state,
            h.category,
            h.star_rating,
            h.price_per_night,
            h.amenities,
            h.description,
            ROUND(AVG(r.rating), 2)   AS avg_review_rating,
            COUNT(r.review_id)        AS review_count
        FROM   hotels h
        LEFT JOIN reviews r ON r.hotel_id = h.hotel_id
        WHERE  h.hotel_id = ANY(%s)
        GROUP  BY h.hotel_id, h.name, h.city, h.state, h.category,
                  h.star_rating, h.price_per_night, h.amenities, h.description
    """
    rows = run_query(sql, (hotel_ids,))
    order = {hid: i for i, hid in enumerate(hotel_ids)}
    return sorted(rows, key=lambda r: order.get(r["hotel_id"], 999))


def get_hotels_by_category(category: str, limit: int = 20) -> list[dict]:
    sql = """
        SELECT
            h.hotel_id,
            h.name,
            h.city,
            h.state,
            h.category,
            h.star_rating,
            h.price_per_night,
            h.amenities,
            h.description,
            ROUND(AVG(r.rating), 2)   AS avg_review_rating,
            COUNT(r.review_id)        AS review_count
        FROM   hotels h
        LEFT JOIN reviews r ON r.hotel_id = h.hotel_id
        WHERE  LOWER(h.category) = LOWER(%s)
        GROUP  BY h.hotel_id, h.name, h.city, h.state, h.category,
                  h.star_rating, h.price_per_night, h.amenities, h.description
        ORDER  BY avg_review_rating DESC NULLS LAST
        LIMIT  %s
    """
    return run_query(sql, (category, limit))


def get_recent_reviews(hotel_id: int, limit: int = 5) -> list[dict]:
    sql = """
        SELECT
            r.rating,
            r.review_text,
            r.review_date,
            r.helpful_votes,
            u.first_name || ' ' || u.last_name  AS reviewer_name,
            u.nationality
        FROM   reviews r
        JOIN   users   u ON u.user_id = r.user_id
        WHERE  r.hotel_id = %s
        ORDER  BY r.review_date DESC
        LIMIT  %s
    """
    return run_query(sql, (hotel_id, limit))


# =============================================================================
# CONNECTION TEARDOWN
# =============================================================================

def close_pool():
    global _pool
    if _pool:
        _pool.close()
        _pool = None