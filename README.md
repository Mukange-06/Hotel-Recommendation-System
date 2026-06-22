# Hotel Recommendation System — RAG Pipeline

**Track A · Z2004 Database Management Systems · IIT Madras Zanzibar**
**Authors:** Emmanuel Mukange (ZDA24B029) · Raudhat Ramadhan (ZDA24B010)
**Supervisor:** Dr. Innocent Nyalala · Even Semester 2026

---

## What This Project Does

A question-answering system that lets you ask hotel questions in plain English
and get a grounded answer with source citations backed by a live relational
database and a vector store.

**Example:**
> You: "Best hotel in Miami under $150 with a pool?"
> System: Courtyard Miami Downtown · $128/night · Pool & Free WiFi
> Source: Review #47 — "Pool was great, location perfect."

---

## Project Structure

```
Hotel-Recommendation-System/
├── schema/
│   ├── schema.sql          # Full DDL + all INSERT statements
│   └── ER_diagram.png      # Entity-relationship diagram
├── data/
│   ├── hotels.csv
│   ├── users.csv
│   ├── bookings.csv
│   ├── reviews.csv
│   └── room_types.csv
├── queries/
│   ├── queries.sql         # 10 labelled SQL queries
│   ├── performance.sql     # EXPLAIN ANALYZE + indexes + stored procedure
│   └── views.sql           # vw_hotel_performance, vw_active_bookings
├── app/
│   ├── embed.py            # Generate embeddings and upload to Pinecone
│   └── query.py            # Python Q&A interface
├── .env.example            # Required environment variables
├── requirements.txt        # Python dependencies
└── README.md
```

---

## Prerequisites

- PostgreSQL 15 or later
- Python 3.10 or later
- A Pinecone account (free tier is enough for development)

---

## Setup Instructions

### Step 1 — Clone the repository

```bash
git clone https://github.com/Mukange-06/Hotel-Recommendation-System.git
cd Hotel-Recommendation-System
```

### Step 2 — Create the database

```bash
psql -U postgres -c "CREATE DATABASE hotel_rag;"
```

### Step 3 — Load the schema and all data

```bash
psql -U postgres -d hotel_rag -f schema/schema.sql
```

This single command creates all five tables and inserts all 1,553 rows.
No separate CSV import is needed.

### Step 4 — Verify row counts

```bash
psql -U postgres -d hotel_rag -c "
SELECT 'room_types' AS table_name, COUNT(*) FROM room_types
UNION ALL SELECT 'hotels',   COUNT(*) FROM hotels
UNION ALL SELECT 'users',    COUNT(*) FROM users
UNION ALL SELECT 'bookings', COUNT(*) FROM bookings
UNION ALL SELECT 'reviews',  COUNT(*) FROM reviews;"
```

Expected output:

```
 table_name | count
------------+-------
 room_types |     5
 hotels     |   474
 users      |   150
 bookings   |   450
 reviews    |   474
```

### Step 5 — Run the SQL queries

```bash
psql -U postgres -d hotel_rag -f queries/queries.sql
```

### Step 6 — Run performance evidence

```bash
psql -U postgres -d hotel_rag -f queries/performance.sql
```

### Step 7 — Create views

```bash
psql -U postgres -d hotel_rag -f queries/views.sql
```

---

## Python Application Setup

### Step 1 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 2 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```
DATABASE_URL=postgresql://postgres:yourpassword@localhost/hotel_rag
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_ENV=your_pinecone_environment
PINECONE_INDEX=hotel-recommendations
```

> Never commit your `.env` file. It is already listed in `.gitignore`.

### Step 3 — Generate embeddings and upload to Pinecone

```bash
python app/embed.py
```

### Step 4 — Run the Q&A interface

```bash
python app/query.py
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `PINECONE_API_KEY` | Your Pinecone API key |
| `PINECONE_ENV` | Pinecone environment region |
| `PINECONE_INDEX` | Name of your Pinecone index |

---

## Database Summary

| Table | Source | Rows |
|---|---|---|
| `room_types` | Manual | 5 |
| `hotels` | Kaggle | 474 |
| `users` | Faker (seed 42) | 150 |
| `bookings` | Faker (seed 42) | 450 |
| `reviews` | Faker (seed 42) | 474 |
| **Total** | | **1,553** |

---

## AI Usage Disclosure

Artificial intelligence tools were used in the making of this project.
All AI-generated content was reviewed, understood, and adapted by the
project team. We take full responsibility for the correctness and
integrity of everything submitted.

---

## Academic Context

This project was submitted in partial fulfillment of the requirements
for Z2004 — Database Management Systems at IIT Madras Zanzibar,
Even Semester 2026.
