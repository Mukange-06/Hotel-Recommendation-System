# =============================================================================
# StayFinder — rag.py
# Retrieval-Augmented Generation pipeline
# Pinecone (vector search) + sentence-transformers (embeddings) + OpenAI (LLM)
# =============================================================================

import os
import json
from typing import Optional

from dotenv import load_dotenv
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
import google.generativeai as genai

from db import get_hotels_by_ids, get_hotels_by_category, get_recent_reviews

load_dotenv()

# =============================================================================
# CLIENTS  (initialised once at module load)
# =============================================================================

_embedder: SentenceTransformer | None = None
_pinecone_index = None
_genai: genai.GenerativeModel | None = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def _get_index():
    global _pinecone_index
    if _pinecone_index is None:
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        _pinecone_index = pc.Index(os.getenv("PINECONE_INDEX", "stayfinder-hotels"))
    return _pinecone_index


def _get_genai():
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    return genai.GenerativeModel("gemini-2.5-flash")


# =============================================================================
# EMBEDDING
# =============================================================================

def embed(text: str) -> list[float]:
    """
    Convert a query string into a dense vector using sentence-transformers.
    all-MiniLM-L6-v2 produces 384-dimensional vectors and runs fast on CPU.
    """
    return _get_embedder().encode(text, normalize_embeddings=True).tolist()


# =============================================================================
# RETRIEVAL
# =============================================================================

def retrieve(query: str, category: Optional[str] = None, top_k: int = 8) -> list[int]:
    """
    Embed the query and search Pinecone for the nearest hotel vectors.
    If a category filter is provided it is applied as a Pinecone metadata filter.
    Returns a ranked list of hotel_ids.
    """
    index  = _get_index()
    vector = embed(query)

    filter_dict = {}
    if category:
        filter_dict["category"] = {"$eq": category.lower()}

    response = index.query(
        vector=vector,
        top_k=top_k,
        include_metadata=True,
        filter=filter_dict if filter_dict else None
    )

    return [int(match["id"]) for match in response.get("matches", [])]


# =============================================================================
# CONTEXT BUILDER
# =============================================================================

def _build_hotel_context(hotel: dict, reviews: list[dict]) -> str:
    """
    Serialise one hotel + its recent reviews into a compact text block
    that fits neatly inside the LLM prompt.
    """
    lines = [
        f"Hotel: {hotel['name']}",
        f"Location: {hotel['city']}, {hotel.get('state', '')}",
        f"Category: {hotel['category']}  |  Stars: {hotel['star_rating']}",
        f"Price per night: ${hotel['price_per_night']}",
        f"Average rating: {hotel.get('avg_review_rating', 'N/A')} "
        f"({hotel.get('review_count', 0)} reviews)",
    ]

    if hotel.get("amenities"):
        lines.append(f"Amenities: {hotel['amenities']}")

    if hotel.get("description"):
        lines.append(f"Description: {hotel['description']}")

    if reviews:
        lines.append("Recent guest reviews:")
        for r in reviews[:3]:
            lines.append(
                f"  [{r['rating']}/5] \"{r['review_text'][:200]}...\""
                if len(r.get("review_text", "")) > 200
                else f"  [{r['rating']}/5] \"{r.get('review_text', '')}\""
            )

    return "\n".join(lines)


def _build_prompt(query: str, hotel_contexts: list[str]) -> str:
    context_block = "\n\n---\n\n".join(hotel_contexts)

    return f"""You are StayFinder, a hotel recommendation assistant.
A guest has asked: "{query}"

Below are the most relevant hotels retrieved from the database.
Use only the information provided — do not invent details.

{context_block}

---

Write a concise, helpful recommendation (3 to 5 sentences) that:
- Directly addresses the guest's query
- Highlights the best matching hotel(s) and why they fit
- Mentions price range and standout amenities where relevant
- Stays factual and grounded in the data above

Recommendation:"""


# =============================================================================
# GENERATION
# =============================================================================

async def _generate(prompt: str) -> str:
    """
    Send the assembled prompt to the Generative Model and return the text response.
    """
    client = _get_genai()

    response = await client.generate_content(prompt)

    return response.text


# =============================================================================
# MAIN PIPELINE
# =============================================================================

async def get_recommendations(query: str, category: Optional[str] = None) -> dict:
    """
    Full RAG pipeline:
      1. Embed the query
      2. Retrieve top-k hotel IDs from Pinecone
      3. Fetch full hotel records + recent reviews from Postgres
      4. Build a grounded prompt
      5. Generate an AI summary via OpenAI
      6. Return { answer, hotels }

    Falls back to a Postgres category query if Pinecone returns nothing.
    """

    # -- 1 & 2: Retrieve ---------------------------------------------------
    hotel_ids = retrieve(query, category, top_k=8)

    # -- 3: Fetch from Postgres --------------------------------------------
    if hotel_ids:
        hotels = get_hotels_by_ids(hotel_ids)
    else:
        # Pinecone returned nothing — fall back to top-rated by category
        hotels = get_hotels_by_category(category or "budget", limit=8)

    if not hotels:
        return {
            "answer": "No hotels matched your search. Try adjusting your query or removing the category filter.",
            "hotels": []
        }

    # -- 4: Build context --------------------------------------------------
    hotel_contexts = []
    for hotel in hotels[:5]:           # cap context at top 5 to stay within token budget
        reviews = get_recent_reviews(hotel["hotel_id"], limit=3)
        hotel_contexts.append(_build_hotel_context(hotel, reviews))

    prompt = _build_prompt(query, hotel_contexts)

    # -- 5: Generate -------------------------------------------------------
    try:
        answer = await _generate(prompt)
    except Exception as e:
        # Generation failure should not kill the whole response —
        # return the hotel list without an AI summary
        answer = f"AI summary unavailable: {e}"

    # -- 6: Return ---------------------------------------------------------
    return {
        "answer": answer,
        "hotels": hotels
    }


# =============================================================================
# INDEXING UTILITY  (run once to populate Pinecone)
# =============================================================================

def index_hotels(hotels: list[dict]):
    """
    Embed all hotels and upsert them into Pinecone.
    Call this once after loading the schema — not during normal app startup.

    Usage from a one-off script:
        from db  import run_query
        from rag import index_hotels
        hotels = run_query("SELECT * FROM hotels")
        index_hotels(hotels)
    """
    index = _get_index()

    vectors = []
    for hotel in hotels:
        # Build a rich text representation for embedding
        text = " ".join(filter(None, [
            hotel.get("name", ""),
            hotel.get("city", ""),
            hotel.get("state", ""),
            hotel.get("category", ""),
            hotel.get("amenities", ""),
            hotel.get("description", ""),
            f"{hotel.get('star_rating', '')} stars",
            f"${hotel.get('price_per_night', '')} per night",
        ]))

        vector = embed(text)

        vectors.append({
            "id":       str(hotel["hotel_id"]),
            "values":   vector,
            "metadata": {
                "name":             hotel.get("name", ""),
                "city":             hotel.get("city", ""),
                "category":         (hotel.get("category") or "").lower(),
                "star_rating":      hotel.get("star_rating"),
                "price_per_night":  float(hotel.get("price_per_night", 0)),
            }
        })

        # Upsert in batches of 100
        if len(vectors) == 100:
            index.upsert(vectors=vectors)
            vectors = []

    if vectors:
        index.upsert(vectors=vectors)

    print(f"Indexed {len(hotels)} hotels into Pinecone.")