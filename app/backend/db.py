# =============================================================================
# StayFinder — db.py
# PostgreSQL connection pool + query runner
# =============================================================================

import os

import psycopg2
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CONNECTION POOL
# =============================================================================

_pool: ConnectionPool | None = None


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=_build_dsn()
        )
    return _pool


def _build_dsn() -> str:
    # Prefer a full DATABASE_URL if provided (e.g. from Render / Railway)
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    # Otherwise build from individual vars
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
    """
    Execute a read-only SQL statement and return all rows as a list of dicts.
    Column names come from the cursor description so app.js can build
    the table headers automatically.
    """
    pool = _get_pool()
    conn = pool.getconn()

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    except psycopg2.Error as e:
        conn.rollback()
        raise RuntimeError(f"Database query failed: {e}") from e
    finally:
        pool.putconn(conn)


def run_write(sql: str, params=None) -> int:
    """
    Execute an INSERT / UPDATE / DELETE and return the number of affected rows.
    Not used by the current analytics endpoints but available for future use
    (e.g. saving a booking from the frontend).
    """
    pool = _get_pool()
    conn = pool.getconn()

    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount
    except psycopg2.Error as e:
        conn.rollback()
        raise RuntimeError(f"Database write failed: {e}") from e
    finally:
        pool.putconn(conn)


def fetch_one(sql: str, params=None) -> dict | None:
    """
    Convenience wrapper — returns a single row or None.
    Used by rag.py to pull hotel details by ID after vector search.
    """
    rows = run_query(sql, params)
    return rows[0] if rows else None


# =============================================================================
# HOTEL HELPERS  (called by rag.py)
# =============================================================================

def get_hotels_by_ids(hotel_ids: list[int]) -> list[dict]:
    """
    Fetch full hotel records for a list of IDs returned by Pinecone.
    Preserves the order of hotel_ids (Pinecone returns them ranked by
    similarity score, so order matters).
    """
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

    # Re-sort to match Pinecone ranking order
    order = {hid: i for i, hid in enumerate(hotel_ids)}
    return sorted(rows, key=lambda r: order.get(r["hotel_id"], 999))


def get_hotels_by_category(category: str, limit: int = 20) -> list[dict]:
    """
    Fallback fetch when Pinecone returns no results — pulls top-rated
    hotels for the requested category directly from Postgres.
    """
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
    """
    Pull the most recent reviews for a hotel.
    Passed to the LLM as context in rag.py so the summary reflects
    real guest sentiment rather than just structured fields.
    """
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
# CONNECTION TEARDOWN  (call on app shutdown)
# =============================================================================

def close_pool():
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None