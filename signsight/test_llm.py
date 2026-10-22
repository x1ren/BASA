"""Phase 1 smoke test: python test_llm.py"""
import llm

print(f"Endpoint: {llm.BASE_URL or '(not set)'}  Model: {llm.MODEL or '(not set)'}")

try:
    reply = llm.chat([{"role": "user", "content": "Hello! Reply in one short sentence."}])
    print(f"Chat OK -> {reply}")
except llm.LLMError as e:
    print(f"Chat FAILED -> {e}")

if llm.has_embeddings():
    try:
        vecs = llm.embed(["Ang deposito ay hindi ibabalik.", "The deposit is non-refundable."])
        print(f"Embeddings OK -> {len(vecs)} vectors, dim={len(vecs[0])}")
    except llm.LLMError as e:
        print(f"Embeddings FAILED -> {e}")
else:
    print("Embeddings: skipped (HACKATHON_EMBED_MODEL blank -> BM25 fallback)")
