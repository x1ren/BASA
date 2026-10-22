"""Index contract chunks and answer questions grounded in them.

Usage: python retrieve.py
"""
import re
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

import llm

# tiny EN / Tagalog / Bisaya stopword list so BM25 isn't dominated by filler words
STOPWORDS = set("""
a an the of to in on at for and or is are be by with as this that it its shall will may any all from
i my me you your can do does what how if when who which there their
ang ng sa mga na ba ko ako mo ka kung ano paano po ay si at
unsa sayo ko nako nimo ug og kay man ba diay
""".split())


def tokenize(text):
    return [t for t in re.findall(r"\w+", text.lower()) if t not in STOPWORDS]


class ContractIndex:
    def __init__(self, chunks):
        self.chunks = chunks
        self.vectors = None
        self.bm25 = None
        try:
            vecs = llm.embed([c["text"] for c in chunks])
            if not vecs:
                raise ValueError("empty embeddings")
            arr = np.array(vecs, dtype=np.float32)
            self.vectors = arr / (np.linalg.norm(arr, axis=1, keepdims=True) + 1e-10)
            self.mode = "embeddings"
        except Exception:
            self.bm25 = BM25Okapi([tokenize(c["text"]) or ["_"] for c in chunks])
            self.mode = "bm25"

    def search(self, query, k=4):
        if not self.chunks:
            return []
        if self.vectors is not None:
            q = np.array(llm.embed([query])[0], dtype=np.float32)
            scores = self.vectors @ (q / (np.linalg.norm(q) + 1e-10))
        else:
            scores = self.bm25.get_scores(tokenize(query) or ["_"])
        top = np.argsort(scores)[::-1][:k]
        return [{**self.chunks[i], "score": float(scores[i])} for i in top]


SYSTEM_PROMPT = """You are Signsight, a Philippine contract assistant helping ordinary Filipinos understand a contract before they sign it.

Rules:
1. Answer ONLY based on the contract clauses provided. Do NOT use outside legal knowledge or speculate.
2. If the clauses do not answer the question, say plainly that the contract does not mention it, in the user's language
   (e.g. "The contract does not mention this." / "Hindi ito binanggit sa kontrata." / "Wala kini gihisgoti sa kontrata.").
   Do NOT guess what is "probably" allowed and do NOT invent rules, amounts, or clauses.
3. Cite the page for every claim using the exact tag format [p. 1] or [p. 2], with a normal space.
4. Use simple, plain words. Keep answers short (2-5 sentences or a few bullets). Keep amounts (e.g. PHP 7,000) exactly as written.
5. CRITICAL LANGUAGE RULE: Reply in the exact language the user asked in.
   - English question -> English answer.
   - Tagalog/Filipino question (e.g. "ano", "paano", "ba", "kapag", "ibabalik") -> Tagalog answer.
   - Bisaya/Cebuano question (e.g. "unsa", "unsaon", "mahitabo", "nako", "nimo", "mo-") -> Bisaya answer.
   Never answer in English if the question was in Tagalog or Bisaya.
6. ONLY when the question itself is in Tagalog or Bisaya, use natural everyday phrasing, the way a Filipino friend who
   knows contracts would explain it. Common English contract terms (deposit, penalty, lease, forfeited) may stay in English
   (Taglish/Bislish is fine). These phrases never apply to English questions.
   - Tagalog: lost or non-refundable money -> "hindi na maibabalik", "mafo-forfeit" / "forfeited"; fees or fines -> "may multa",
     "penalty"; leaving early -> "aalis bago matapos ang kontrata".
   - Bisaya: lost or non-refundable money -> "ma-forfeit", "dili na mabalik", "mawala ang kwarta"; fees or fines -> "naay multa",
     "penalty"; leaving early -> "mo-hawa / mo-biya sa dili pa mahuman ang kontrata".
     NEVER use "ipangayo" (it means "to ask for", the opposite meaning) when describing money the tenant loses."""

REWRITE_PROMPT = """Translate this question about a contract into a short list of English search keywords (5-10 words, no explanation). Include likely contract terms (e.g. deposit, refund, termination, penalty, renewal).

Question: {q}
Keywords:"""


def _expand_query(question):
    """Contracts are usually in English, so add English keywords for Tagalog/Bisaya questions."""
    try:
        return f"{question} {llm.chat([{'role': 'user', 'content': REWRITE_PROMPT.format(q=question)}], temperature=0, max_tokens=40)}"
    except llm.LLMError:
        return question


def ask_contract(index, question, k=4):
    sources = index.search(_expand_query(question), k=k)
    context = "\n\n".join(f"Clause [p. {c['page']}]: {c['text']}" for c in sources)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Contract clauses:\n{context}\n\n"
            f"Question: {question}\n\n"
            "Answer using only the clauses above and cite pages. Reply in the same language as the question: "
            "an English question gets a fully English answer."
        )},
    ]
    return {"answer": llm.chat(messages, temperature=0.1), "sources": sources}


if __name__ == "__main__":
    from ingest import extract_chunks_from_pdf

    pdf = Path(__file__).with_name("samples") / "sample_lease.pdf"
    index = ContractIndex(extract_chunks_from_pdf(pdf))
    print(f"Indexed {len(index.chunks)} chunks from {pdf.name} (mode: {index.mode})")

    for q in ["Can I get my deposit back if I leave early?", "May penalty ba kapag late ang upa?",
              "Unsa mahitabo kung mo-hawa ko sayo?", "Allowed ba ang pets sa property?"]:
        print(f"\n=== Q: {q}")
        try:
            result = ask_contract(index, q)
            print(f"A: {result['answer']}")
            sources = result["sources"]
        except llm.LLMError as e:
            print(f"A: (LLM unavailable: {e})")
            sources = index.search(q)
        for s in sources:
            print(f"  - chunk {s['chunk_id']} [p. {s['page']}] score={s['score']:.2f}: {s['text'][:70]!r}")
