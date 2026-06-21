# Hotel Recommendation System — RAG Pipeline

**Authors:** Emmanuel Mukange (ZDA24B029) · Raudhat Ramadhan (ZDA24B010)  
**Course:** Database Management Systems — IIT Madras Zanzibar  
**Track:** A — Retrieval-Augmented Generation (RAG) Pipeline  
**DBMS:** PostgreSQL 15+  
**Vector Store:** Pinecone  

---

## Overview

This project builds a hotel recommendation and question-answering system that combines a normalised relational database with a semantic vector search layer. Real hotel records from a Kaggle dataset form the core of the system, extended with synthetically generated users, bookings, and reviews to exceed the 1,000-row project minimum.

The system answers natural-language queries like *"Find me a budget-friendly hotel in Miami with a pool and free Wi-Fi"* by embedding the query and retrieving the most semantically relevant hotel reviews and amenity descriptions from Pinecone, then grounding the final answer with structured data from PostgreSQL.

---

## Repository Structure

```
Hotel-Recommendation-System/
├── DBMS_Milestone_1.zip        # Schema design and DDL
│   ├── Schema.sql              # Full DDL + all INSERT statements
│   ├── ER_diagram.png          # Entity-relationship diagram
│   └── README.docx             # Milestone 1 write-up
│
├── Milestone 2.zip             # SQL queries and CSV exports
│   ├── queries.sql             # Ten labelled SQL queries
│   ├── README.md               # Detailed write-up and data dictionary
│   └── csv/
│       ├── hotels.csv
│       ├── users.csv
│       ├── bookings.csv
│       ├── reviews.csv
│       └── room_types.csv
│
└── Milestone 3.zip             # RAG pipeline implementation
```

---

## Database Schema

Five tables in third normal form (3NF):

| Table | Source | Rows |
|-------|--------|-----:|
| `room_types` | Manual | 5 |
| `hotels` | Kaggle (real data) | 474 |
| `users` | Synthetic (Faker, seed 42) | 150 |
| `bookings` | Synthetic (Faker, seed 42) | 450 |
| `reviews` | Synthetic (Faker, seed 42) | 474 |
| **Total** | | **1,553** |

### Table Summaries

**`room_types`** — Lookup table for room categories (Single, Double, Twin, Suite, Penthouse). Stores `max_occupancy` and a `price_multiplier` applied to a hotel's base nightly rate.

**`hotels`** — Core entity. 474 real Miami-area hotels from Kaggle, enriched with synthetic columns: `star_rating` (1.0–5.0), `price_per_night` ($45–$550), `amenities` (comma-separated free text), and `total_rooms`. The `amenities` column is the primary text corpus for sentence-transformer embeddings and is intentionally kept as a flat string rather than a junction table to preserve semantic continuity for vector retrieval.

**`users`** — 150 synthetic travellers generated with `Faker(seed=42)`. Includes nationality drawn from a 15-country pool and a date of birth.

**`bookings`** — Fact table recording each reservation. `total_price` is stored explicitly at booking time rather than derived at query time, ensuring historical accuracy when hotel prices change.

**`reviews`** — One review per (hotel, user) pair. The `review_text` column (6–10 sentences per review) feeds the RAG embedding pipeline. `helpful_votes` allows community ranking of retrieved reviews.

### Indexes

| Index | Table | Column(s) | Purpose |
|-------|-------|-----------|---------|
| `idx_bookings_user_id` | bookings | user_id | Booking lookup by guest |
| `idx_bookings_hotel_id` | bookings | hotel_id | Availability and revenue queries |
| `idx_bookings_checkin` | bookings | check_in_date | Date-range filtering |
| `idx_hotels_city` | hotels | city | Most common search filter |
| `idx_hotels_rating` | hotels | star_rating | Rating-based filtering |
| `idx_hotels_price` | hotels | price_per_night | Price-range filtering |
| `idx_reviews_hotel_id` | reviews | hotel_id | JOIN-heavy RAG retrieval |

---

## RAG Architecture

```
User Query
    │
    ▼
Sentence-Transformer (multilingual-e5 or similar)
    │  (384-dimensional embedding)
    ▼
Pinecone Vector Search  ──►  Top-K relevant review_text + amenity chunks
    │
    ▼
PostgreSQL  ──►  Structured hotel metadata (price, rating, location)
    │
    ▼
LLM (grounded answer with retrieved context)
```

All relational data lives in PostgreSQL. Only the vector embeddings (generated from `reviews.review_text` and `hotels.amenities`) are stored in Pinecone. This separation keeps the structured query layer clean while enabling semantic similarity search at retrieval time.

---

## SQL Query Coverage

All ten queries are in `queries.sql`:

| Label | Type | Description |
|-------|------|-------------|
| `[AGG-1]` | Aggregation | Total and average booking revenue by hotel category |
| `[AGG-2]` | Aggregation | Average review rating per city (cities with ≥ 5 reviews) |
| `[JOIN-1]` | Join | Full booking ledger joining bookings, users, hotels, room_types |
| `[JOIN-2]` | Join | Top-reviewed hotels with star rating and helpful-vote totals |
| `[SUB-1]` | Subquery | Hotels priced above the portfolio-wide average (scalar subquery) |
| `[SUB-2]` | Subquery | Users who have never made a booking (correlated NOT EXISTS) |
| `[CTE-1]` | CTE | Monthly booking revenue trend with month-over-month change |
| `[CTE-2]` | CTE | Hotel revenue tier classification using two chained CTEs |
| `[WIN-1]` | Window fn | Booking revenue ranked within each hotel category using `RANK()` |
| `[WIN-2]` | Window fn | Running cumulative booking count and spend per user using `SUM() OVER` |

---

## Setup and Reproduction

### Prerequisites

- PostgreSQL 15 or later
- A Pinecone account (free tier is sufficient for development)
- Python 3.10+ with `sentence-transformers` and `pinecone-client` (Milestone 3)

### Load the Relational Database

```bash
# Create the database
psql -U postgres -c "CREATE DATABASE hotel_rag;"

# Run the schema file (DDL + all data in one command)
psql -U postgres -d hotel_rag -f schema.sql

# Verify row counts
psql -U postgres -d hotel_rag -c "
SELECT 'room_types' AS tbl, COUNT(*) FROM room_types
UNION ALL SELECT 'hotels',   COUNT(*) FROM hotels
UNION ALL SELECT 'users',    COUNT(*) FROM users
UNION ALL SELECT 'bookings', COUNT(*) FROM bookings
UNION ALL SELECT 'reviews',  COUNT(*) FROM reviews;"
```

Expected output:

```
    tbl     | count
------------+-------
 room_types |     5
 hotels     |   474
 users      |   150
 bookings   |   450
 reviews    |   474
```

### Run the SQL Queries

```bash
psql -U postgres -d hotel_rag -f queries.sql
```

---

## Design Decisions

**Flat amenities column.** Storing amenities as a comma-separated string rather than a junction table is intentional. The column is embedded whole by the sentence-transformer. Splitting it into rows would fragment the semantic context needed for accurate vector retrieval.

**Stored total_price.** `total_price` in `bookings` is derivable from `price_per_night × price_multiplier × nights`, but hotel prices change over time. Storing the value at booking time is standard practice in reservation systems and does not violate 3NF — it is an atomic fact of the booking event.

**Pinecone over pgvector.** `pgvector` was not available in the lab environment for PostgreSQL 15+. The specification permits Pinecone as an alternative. The relational schema is fully self-contained in PostgreSQL regardless of the vector store choice.

**Synthetic data reproducibility.** All synthetic rows (users, bookings, reviews) were generated with `random.seed(42)` and `Faker.seed(42)`. The `schema.sql` file is the single source of truth — no external CSV files are required to reproduce the database from scratch.

---

## Authors

| Name | Roll Number | Contribution |
|------|-------------|--------------|
| Emmanuel Mukange | ZDA24B029 | Schema design, SQL queries, RAG pipeline |
| Raudhat Ramadhan | ZDA24B010 | Schema design, SQL queries, RAG pipeline |

IIT Madras Zanzibar — Database Management Systems