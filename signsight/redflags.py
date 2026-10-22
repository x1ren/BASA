"""Red-flag scan: retrieve risky clauses per category, then one LLM call returns JSON findings.

Usage: python redflags.py [path/to/contract.pdf]
"""
import json
import re
import sys
from pathlib import Path

import llm

# category -> English search query (contracts are usually written in English)
CATEGORIES = {
    "Deposit & Refund": "security deposit advance refund non-refundable forfeit return",
    "Penalties & Surcharges": "late payment penalty surcharge interest fine fee per day damages",
    "Termination & Eviction": "terminate termination eviction notice lock-in pre-termination vacate",
    "Auto-Renewal": "automatically renew renewal extend term notice non-renewal expiry",
    "Liability & Repairs": "damage repair liability maintenance responsible cost structural",
    "Rent & Price Escalation": "rent increase adjust adjusted fee rates escalation without notice",
}
RISK_ORDER = {"High": 0, "Medium": 1, "Low": 2}
PER_CATEGORY = 3
FALLBACK_CHUNKS = 12  # if retrieval finds nothing (e.g. a Tagalog contract under BM25), scan the first N chunks

SYSTEM_PROMPT = f"""You are Signsight, a contract reviewer protecting ordinary Filipinos (tenants, workers, borrowers) before they sign.

Inspect the contract clauses for terms that are unfair, one-sided, or predatory under common Philippine contract and tenancy conventions. Check these categories: {", ".join(CATEGORIES)}.

Rules:
- Use ONLY the clauses given. Do not invent clauses, amounts, or facts.
- One finding per risky term. Skip categories with nothing risky.
- risk: "High" = could cost the signer a lot of money, their home, or their job with little recourse; "Medium" = one-sided or vague, worth negotiating; "Low" = minor, just be aware.
- page: the number from the clause's [p. N] tag.
- Write in simple English that a non-lawyer understands.

Output ONLY a JSON array: no prose, no code fences. Output [] if nothing is risky. Each item:
{{"category": "<one of the categories>", "clause_summary": "<1-sentence summary of the clause>", "plain_explanation": "<why this is risky for the signer>", "risk": "High|Medium|Low", "page": <int>}}"""

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def gather_clauses(index, k=PER_CATEGORY):
    """Top clauses for every category, deduped by chunk_id, in document order."""
    seen = {}
    for query in CATEGORIES.values():
        for c in index.search(query, k=k):
            if c["score"] > 0:  # BM25 gives 0 when no keyword matches
                seen.setdefault(c["chunk_id"], c)
    return sorted(seen.values(), key=lambda c: c["chunk_id"])


def _load_json_array(reply):
    """Best-effort JSON array from an LLM reply; None if nothing usable."""
    m = _FENCE.search(reply)
    text = (m.group(1) if m else reply).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        try:
            data = json.loads(text[start:end + 1]) if 0 <= start < end else None
        except json.JSONDecodeError:
            data = None
    if data is None:  # last resort: salvage individual flat {...} objects
        data = []
        for obj in re.findall(r"\{[^{}]*\}", text):
            try:
                data.append(json.loads(obj))
            except json.JSONDecodeError:
                pass
        if not data and "[]" not in text:
            return None
    if isinstance(data, dict):  # e.g. {"flags": [...]}
        data = next((v for v in data.values() if isinstance(v, list)), [data])
    return data if isinstance(data, list) else None


def _normalize(item, valid_pages):
    if not isinstance(item, dict):
        return None
    explanation = str(item.get("plain_explanation") or "").strip()
    if not explanation:
        return None
    raw_risk = str(item.get("risk") or "").lower()
    risk = next((r for r in RISK_ORDER if r.lower() in raw_risk), "Medium")
    page = re.search(r"\d+", str(item.get("page")))
    page = int(page.group()) if page else None
    return {
        "category": str(item.get("category") or "Other").strip(),
        "clause_summary": str(item.get("clause_summary") or "").strip(),
        "plain_explanation": explanation,
        "risk": risk,
        "page": page if page in valid_pages else None,  # never show a citation the LLM made up
    }


def scan_contract(index):
    """-> [{"category", "clause_summary", "plain_explanation", "risk", "page"}], High first.

    Raises llm.LLMError if the API fails or the reply can't be parsed.
    """
    clauses = gather_clauses(index) or index.chunks[:FALLBACK_CHUNKS]
    if not clauses:
        return []
    context = "\n\n".join(f"Clause [p. {c['page']}]: {c['text']}" for c in clauses)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Red-flag scan. Contract clauses:\n\n{context}\n\nReturn the JSON array of red flags."},
    ]
    items = _load_json_array(llm.chat(messages, temperature=0, max_tokens=1500))
    if items is None:
        raise llm.LLMError("The red-flag scan reply was not valid JSON.")
    valid_pages = {c["page"] for c in clauses}
    flags = [f for f in (_normalize(i, valid_pages) for i in items) if f]
    return sorted(flags, key=lambda f: (RISK_ORDER[f["risk"]], f["page"] or 0))


if __name__ == "__main__":
    from ingest import extract_chunks_from_pdf
    from retrieve import ContractIndex

    sys.stdout.reconfigure(errors="replace")  # Windows consoles choke on some LLM characters
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("samples") / "sample_lease.pdf"
    index = ContractIndex(extract_chunks_from_pdf(pdf))
    clauses = gather_clauses(index)
    print(f"Indexed {len(index.chunks)} chunks from {pdf.name} (mode: {index.mode})")
    print(f"Clauses sent to LLM: {len(clauses)} (chunk ids {[c['chunk_id'] for c in clauses]})")

    try:
        flags = scan_contract(index)
    except llm.LLMError as e:
        sys.exit(f"Scan failed: {e}")

    print(json.dumps(flags, indent=2, ensure_ascii=False))
    print(f"\n{'RISK':<7} {'PAGE':<5} {'CATEGORY':<24} SUMMARY")
    for f in flags:
        print(f"{f['risk']:<7} {f['page'] or '-':<5} {f['category']:<24} {f['clause_summary'][:70]}")
    counts = {r: sum(f["risk"] == r for f in flags) for r in RISK_ORDER}
    print(f"\n{counts['High']} High | {counts['Medium']} Medium | {counts['Low']} Low")
