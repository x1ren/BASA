# Signsight — Claude Code Guidelines

## Mission
Build Signsight within a 4-hour hackathon. Speed and working demo over perfection.
Theme: Document-based RAG for Filipino contracts (Leases, Job Contracts, Loans).

## Disqualification Rules
1. Use ONLY the hackathon's custom API endpoint. Never import or call external APIs (OpenAI, Anthropic, HuggingFace, etc.).
2. The API key must live in `.env` and NEVER be printed, hardcoded, or committed to Git.
3. `.env` MUST be in `.gitignore`.

## Tech Stack
- Python 3.10+
- Streamlit (UI)
- PyMuPDF (`fitz`) for PDF parsing
- Vector / Keyword search: `rank_bm25` (BM25 fallback) and/or `chromadb` / `numpy` cosine similarity
- `python-dotenv` & `requests`
- NO LangChain, NO LlamaIndex (pure plain Python only)

## Execution Protocol
- Build strictly ONE phase at a time.
- After each phase:
  1. Explain what was built in 2–4 sentences.
  2. Provide terminal commands to run and verify.
  3. STOP and wait for user confirmation ("next") before touching the next phase.

## Product
User uploads a contract PDF and gets:
1. Red-flag scan: risky clauses (deposit forfeiture, penalties, auto-renewal, termination, hidden fees), plain-language explanation, Low/Medium/High rating, page citation.
2. Q&A in English, Tagalog, or Bisaya: answers ONLY from the document, in the user's language, with page citations.

## Layout
All code lives in `signsight/`: `app.py` (UI), `llm.py` (`chat()` / `embed()`), `ingest.py` (PDF -> page-tagged chunks),
`retrieve.py` (embeddings or BM25 fallback), `redflags.py` (scan + prompts), `samples/` (test contracts).
Config is in `signsight/.env` (see `.env.example`). Coding stops at 3:00 PM.
