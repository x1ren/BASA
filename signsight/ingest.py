"""PDF -> page-tagged clause chunks.

Usage: python ingest.py [path/to/contract.pdf]
"""
import re
import sys
from pathlib import Path

import pymupdf as fitz  # `import fitz` is deprecated in current PyMuPDF

MAX_CHARS = 800
OVERLAP = 80

SAMPLES_DIR = Path(__file__).with_name("samples")
_SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+")


def _open(pdf_source):
    if isinstance(pdf_source, (str, Path)):
        return fitz.open(str(pdf_source))
    if isinstance(pdf_source, (bytes, bytearray)):
        return fitz.open(stream=bytes(pdf_source), filetype="pdf")
    if hasattr(pdf_source, "getvalue"):  # io.BytesIO, Streamlit UploadedFile
        return fitz.open(stream=pdf_source.getvalue(), filetype="pdf")
    if hasattr(pdf_source, "read"):
        return fitz.open(stream=pdf_source.read(), filetype="pdf")
    raise TypeError(f"Unsupported pdf_source type: {type(pdf_source).__name__}")


def _page_paragraphs(page):
    """Text blocks are PyMuPDF's paragraphs; join wrapped lines and squash whitespace."""
    paras = []
    for block in page.get_text("blocks", sort=True):
        if block[6] != 0:  # skip image blocks
            continue
        text = re.sub(r"\s+", " ", block[4]).strip()
        if text:
            paras.append(text)
    return paras


def _split_long(text, limit):
    """Break an oversized paragraph on sentence boundaries (words as a last resort)."""
    pieces, buf = [], ""
    for sent in _SENTENCE_END.split(text):
        while len(sent) > limit:  # a single monster sentence: cut on a word boundary
            cut = sent.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            if buf:
                pieces.append(buf)
                buf = ""
            pieces.append(sent[:cut].strip())
            sent = sent[cut:].strip()
        if buf and len(buf) + 1 + len(sent) > limit:
            pieces.append(buf)
            buf = sent
        else:
            buf = f"{buf} {sent}".strip()
    if buf:
        pieces.append(buf)
    return pieces


def _tail(text, n):
    """Last ~n chars of text, starting at a word boundary."""
    if len(text) <= n:
        return text
    tail = text[-n:]
    space = tail.find(" ")
    return tail[space + 1:] if space != -1 else tail


def _chunk_page(paras):
    budget = MAX_CHARS - OVERLAP  # leave room for the overlap prefix
    units = []
    for p in paras:
        units.extend(_split_long(p, budget) if len(p) > budget else [p])

    # greedily pack paragraphs up to the budget (so chunk + overlap <= MAX_CHARS)
    chunks, buf = [], ""
    for unit in units:
        if buf and len(buf) + 1 + len(unit) > budget:
            chunks.append(buf)
            buf = unit
        else:
            buf = f"{buf}\n{unit}" if buf else unit
    if buf:
        chunks.append(buf)
    if not chunks:
        return []

    # prefix each chunk (after the first on a page) with the tail of the previous one
    return [chunks[0]] + [f"{_tail(prev, OVERLAP)} {cur}" for prev, cur in zip(chunks, chunks[1:])]


def extract_chunks_from_pdf(pdf_source):
    """Return [{"chunk_id", "page", "text"}] — chunks never span pages, so citations stay exact."""
    chunks = []
    with _open(pdf_source) as doc:
        for page_no, page in enumerate(doc, start=1):
            for text in _chunk_page(_page_paragraphs(page)):
                if text.strip():
                    chunks.append({"chunk_id": len(chunks), "page": page_no, "text": text.strip()})
    return chunks


SAMPLE_LEASE_PAGES = [
    """CONTRACT OF LEASE (BOARDING HOUSE)

This Contract of Lease is entered into this 1st day of August 2026 in Cebu City, Philippines, by and between MARIA L. SANTOS, of legal age, Filipino, owner of Santos Boarding House, Brgy. Lahug, Cebu City (the "LESSOR"), and JUAN P. DELA CRUZ, of legal age, Filipino, student (the "LESSEE").

1. PREMISES. The LESSOR leases to the LESSEE one (1) bedspace in Room 4, 2nd Floor, Santos Boarding House, including shared use of the common kitchen and comfort room.

2. TERM. This lease shall be for a period of twelve (12) months starting August 1, 2026 until July 31, 2027. This lease shall automatically renew for another twelve (12) months unless the LESSEE gives written notice of non-renewal at least sixty (60) days before expiry.

3. RENT. The monthly rent is THREE THOUSAND FIVE HUNDRED PESOS (PHP 3,500.00), payable on or before the 5th day of each month. Rent paid after the 5th day shall incur a late penalty of PHP 200.00 per day until fully paid. Electricity and water are NOT included and shall be billed separately at rates determined solely by the LESSOR.

4. ADVANCE AND DEPOSIT. Upon signing, the LESSEE shall pay one (1) month advance rent and two (2) months security deposit, totaling PHP 10,500.00. The security deposit shall answer for unpaid bills and damages and is non-refundable if the LESSEE leaves before the end of the term for any reason.""",
    """5. EARLY TERMINATION. Should the LESSEE terminate this lease before the end of the term, the LESSEE shall forfeit the entire security deposit and shall pay the rent for the remaining months of the term as liquidated damages. The LESSOR may terminate this lease at any time with seven (7) days notice.

6. HOUSE RULES. The LESSEE shall observe a 10:00 PM curfew. Visitors are not allowed inside the rooms. Violation of house rules three (3) times shall be a ground for immediate eviction without refund of any amount paid.

7. INSPECTION. The LESSOR or her representative may enter the leased premises at any time, with or without notice, for inspection purposes.

8. MAINTENANCE FEE. The LESSEE shall pay a monthly maintenance and Wi-Fi fee of PHP 300.00, which may be adjusted by the LESSOR without prior notice.

IN WITNESS WHEREOF, the parties have signed this Contract of Lease on the date and place first above written.

MARIA L. SANTOS (Lessor)                JUAN P. DELA CRUZ (Lessee)""",
]


def make_sample_lease(path):
    doc = fitz.open()
    for body in SAMPLE_LEASE_PAGES:
        page = doc.new_page()  # A4-ish default (595 x 842)
        page.insert_textbox(fitz.Rect(60, 60, 535, 790), body, fontsize=10.5, fontname="helv")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    doc.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        pdf_path = Path(sys.argv[1])
    else:
        existing = sorted(SAMPLES_DIR.glob("*.pdf"))
        pdf_path = existing[0] if existing else SAMPLES_DIR / "sample_lease.pdf"
        if not existing:
            make_sample_lease(pdf_path)
            print(f"Created dummy contract: {pdf_path}")

    with fitz.open(str(pdf_path)) as d:
        total_pages = d.page_count
    chunks = extract_chunks_from_pdf(pdf_path)

    print(f"File:         {pdf_path.name}")
    print(f"Total pages:  {total_pages}")
    print(f"Total chunks: {len(chunks)}")
    print(f"Chunks/page:  { {p: sum(c['page'] == p for c in chunks) for p in range(1, total_pages + 1)} }")
    for c in chunks[:3]:
        preview = c["text"][:200].replace("\n", " | ")
        print(f"\n--- chunk {c['chunk_id']} | page {c['page']} | {len(c['text'])} chars ---\n{preview}...")
