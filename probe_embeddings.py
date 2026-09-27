"""Real embedding probe: check API key availability and compute real cosine similarities."""

import os
import math

# --- 1. API key check ---
gemini_key = os.getenv("GEMINI_API_KEY")
google_key = os.getenv("GOOGLE_API_KEY")
groq_key = os.getenv("GROQ_API_KEY")
any_key = gemini_key or google_key or groq_key

print("=== API Key Availability ===")
print(f"GEMINI_API_KEY : {'SET (len=' + str(len(gemini_key)) + ')' if gemini_key else 'NOT SET'}")
print(f"GOOGLE_API_KEY : {'SET (len=' + str(len(google_key)) + ')' if google_key else 'NOT SET'}")
print(f"GROQ_API_KEY   : {'SET (len=' + str(len(groq_key)) + ')' if groq_key else 'NOT SET'}")
print(f"Any key for embedding: {bool(any_key)}")
print()

if not any_key:
    print("NO API KEY AVAILABLE — get_dense_embedding will return None and fall back to TF-IDF.")
    print("To run real embedding verification, set GEMINI_API_KEY or GOOGLE_API_KEY in .env")
    raise SystemExit(0)

# --- 2. Import and call the real get_dense_embedding ---
from pwa.agent.models import get_dense_embedding  # noqa: E402
from pwa.agent.pipeline.schema_agent import _CATALOG_SEMANTIC_DESCRIPTIONS  # noqa: E402

QUERIES = [
    "how much stuff do we have sitting around",
    "money we paid vendors",
    "folks who reached out about buying",
]

TARGET_ENTITIES = [
    "fact_inventory",
    "fact_purchase_order",
    "fact_marketing_lead",
    "fact_closed_deal",  # the real-world confusable case
]


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if (na > 0 and nb > 0) else 0.0


print("=== Fetching query embeddings ===")
query_vecs = {}
for q in QUERIES:
    v = get_dense_embedding(q)
    if v is None:
        print(f"  FAILED to get embedding for query: '{q}'")
    else:
        print(f"  OK  '{q[:50]}' -> dim={len(v)}")
    query_vecs[q] = v

print()
print("=== Fetching entity description embeddings ===")
entity_vecs = {}
for ent in TARGET_ENTITIES:
    desc = _CATALOG_SEMANTIC_DESCRIPTIONS.get(ent, "")
    v = get_dense_embedding(desc)
    if v is None:
        print(f"  FAILED: {ent}")
    else:
        print(f"  OK  {ent} (desc={repr(desc[:60])}...)")
    entity_vecs[ent] = v

print()
print("=== Real Cosine Similarities ===")
print(f"{'QUERY':<45} | {'ENTITY':<25} | SIMILARITY")
print("-" * 95)
for q in QUERIES:
    qv = query_vecs.get(q)
    for ent in TARGET_ENTITIES:
        ev = entity_vecs.get(ent)
        if qv is None or ev is None:
            sim_str = "N/A (embedding failed)"
        else:
            sim_str = f"{cosine(qv, ev):.6f}"
        print(f"{q:<45} | {ent:<25} | {sim_str}")
    print()

print("=== Winner per query (highest similarity entity) ===")
for q in QUERIES:
    qv = query_vecs.get(q)
    if qv is None:
        print(f"  '{q}' -> N/A")
        continue
    scores = []
    for ent in TARGET_ENTITIES:
        ev = entity_vecs.get(ent)
        if ev is not None:
            scores.append((ent, cosine(qv, ev)))
    scores.sort(key=lambda x: x[1], reverse=True)
    top = scores[0] if scores else ("?", 0.0)
    gap = (scores[0][1] - scores[1][1]) if len(scores) > 1 else 0.0
    print(f"  '{q}'")
    for ent, sc in scores:
        print(f"      {ent:<25} : {sc:.6f}")
    print(f"    -> winner: {top[0]}  (gap to #2: {gap:.6f})")
    print()
