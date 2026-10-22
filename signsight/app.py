"""Signsight Streamlit UI. Run: streamlit run app.py"""
import html
import re

import streamlit as st

import llm
from ingest import extract_chunks_from_pdf
from redflags import scan_contract
from retrieve import ContractIndex, ask_contract

st.set_page_config(page_title="Signsight — Contract Analyzer", page_icon="📄", layout="centered")

st.session_state.setdefault("indexed_pdf_name", None)
st.session_state.setdefault("contract_index", None)
st.session_state.setdefault("index_summary", "")
st.session_state.setdefault("messages", [])
st.session_state.setdefault("redflags", None)
st.session_state.setdefault("redflags_error", None)

RISK_STYLE = {  # risk -> (Streamlit markdown color, badge label, metric label)
    "High": ("red", "🚨 High Risk", "🚨 High"),
    "Medium": ("orange", "⚠️ Medium Risk", "⚠️ Medium"),
    "Low": ("green", "ℹ️ Low Risk", "ℹ️ Low"),
}

STARTERS = [  # (language tag, question)
    ("EN", "Can I get my deposit back if I leave early?"),
    ("TL", "May penalty ba kapag late ang upa?"),
    ("CEB", "Unsa mahitabo kung mo-hawa ko sayo?"),
    ("TEST", "Allowed ba ang pets sa property?"),
]

BADGES = [":blue-badge[English]", ":blue-badge[Tagalog]", ":blue-badge[Bisaya]",
          ":violet-badge[Document-Grounded RAG]", ":green-badge[Zero Data Retention • In-Memory RAG]"]

CITATION = re.compile(r"\[p\.\s*(\d+)\]")  # \s also matches the narrow no-break space some models emit

CSS = """
<style>
:root { --bg: #0B0F17; --surface: #131924; --border: rgba(255, 255, 255, 0.08); --accent: #6366F1; --cite: #818CF8; }

/* chrome: hide Streamlit header/menu/footer but keep the button that reopens a collapsed sidebar */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stExpandSidebarButton"] { visibility: visible; }

.stApp, [data-testid="stHeader"] { background: var(--bg); }
[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--border); }

/* cards: red-flag findings, chat turns, expanders */
[class*="st-key-flag_"], [data-testid="stChatMessage"], [data-testid="stExpander"] details {
    background: var(--surface); border: 1px solid var(--border) !important; border-radius: 12px;
}
[data-testid="stChatMessage"] { padding: 0.9rem 1rem; }

/* red-flag scoreboard: glass tiles */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.01));
    border: 1px solid var(--border) !important; border-radius: 14px;
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06), 0 8px 24px rgba(0, 0, 0, 0.35);
}

/* starter questions: glowing chips */
[class*="st-key-starter_"] button {
    background: var(--surface); border: 1px solid var(--border); border-radius: 999px;
    text-align: left; justify-content: flex-start; transition: all 0.15s ease;
}
[class*="st-key-starter_"] button:hover {
    border-color: var(--accent); color: #fff; background: rgba(99, 102, 241, 0.12);
    box-shadow: 0 0 0 1px var(--accent), 0 0 18px rgba(99, 102, 241, 0.45);
}
[class*="st-key-starter_"] button code { color: var(--cite); background: rgba(129, 140, 248, 0.12); }

/* page citations */
.cite {
    display: inline-block; padding: 0 0.45em; border-radius: 6px; font-size: 0.8em; font-weight: 600;
    color: var(--cite); background: rgba(129, 140, 248, 0.14); border: 1px solid rgba(129, 140, 248, 0.35);
    white-space: nowrap;
}
</style>
"""


def with_citation_badges(text):
    """Escape model output (it may echo contract text) and turn [p. N] tags into styled badges."""
    return CITATION.sub(r'<span class="cite">p. \1</span>', html.escape(text, quote=False))


def render_sources(sources):
    with st.expander("View Cited Clauses"):
        for s in sources:
            st.markdown(f"**Page {s['page']}**")
            st.markdown("> " + s["text"].replace("\n", "\n> "))


def render_redflags(flags, error):
    st.subheader("🚩 Red-flag scan")
    if error:
        st.warning(f"Red-flag scan unavailable: {error}")
        return
    if not flags:
        st.success("No major red flags detected.")
        return

    for col, (risk, (_, _, metric_label)) in zip(st.columns(len(RISK_STYLE)), RISK_STYLE.items()):
        col.metric(metric_label, sum(f["risk"] == risk for f in flags), border=True)

    for i, f in enumerate(flags):
        color, label, _ = RISK_STYLE[f["risk"]]
        page = f' &nbsp; <span class="cite">p. {f["page"]}</span>' if f["page"] else ""
        with st.container(border=True, key=f"flag_{i}"):
            st.markdown(f":{color}-background[**{label}**] &nbsp; **{html.escape(f['category'])}**{page}",
                        unsafe_allow_html=True)
            st.markdown(f["plain_explanation"])
            if f["clause_summary"]:
                with st.expander("What the clause says"):
                    st.markdown(f["clause_summary"])


def answer(prompt):
    """Show the question, ask the contract, and store both turns in st.session_state.messages."""
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Consulting contract context..."):
            try:
                result = ask_contract(st.session_state.contract_index, prompt)
                reply = {"role": "assistant", "content": result["answer"], "sources": result["sources"]}
            except llm.LLMError as e:
                reply = {"role": "assistant", "content": f"Signsight couldn't reach the AI service: {e}", "error": True}
            except Exception:
                reply = {"role": "assistant", "content": "Something went wrong while answering. Please try again.",
                         "error": True}
    st.session_state.messages.append(reply)


st.markdown(CSS, unsafe_allow_html=True)
st.title("Signsight — See what you're signing.")
st.markdown("AI-powered contract risk scanner & multilingual legal assistant for Filipinos.")
st.markdown(" ".join(BADGES))

with st.sidebar:
    st.header("Your contract")
    uploaded = st.file_uploader("Upload a PDF", type=["pdf"])

if uploaded is None:
    st.info("⬅️ Upload a lease, job contract, or loan agreement (PDF) to get started.")
    st.stop()

file_key = f"{uploaded.name}:{uploaded.size}"
if st.session_state.indexed_pdf_name != file_key:  # ingest + scan run once per uploaded file
    if uploaded.size == 0:
        st.warning("This file is empty. Please upload the contract PDF again.")
        st.stop()
    with st.spinner("Ingesting contract clauses..."):
        try:
            chunks = extract_chunks_from_pdf(uploaded)
            index = ContractIndex(chunks) if chunks else None
        except Exception:
            st.warning("Could not read this PDF. Please make sure it is a valid, non-password-protected PDF.")
            st.stop()
    if not chunks:
        st.warning("No text found in this PDF. It may be a scanned photo; please upload a text-based (digital) PDF.")
        st.stop()
    st.session_state.contract_index = index
    st.session_state.messages = []
    with st.spinner("Scanning contract for predatory clauses & red flags..."):
        try:
            st.session_state.redflags = scan_contract(index)
            st.session_state.redflags_error = None
        except llm.LLMError as e:
            st.session_state.redflags, st.session_state.redflags_error = None, str(e)
        except Exception:
            st.session_state.redflags, st.session_state.redflags_error = None, "unexpected error while scanning."
    pages = len({c["page"] for c in chunks})
    st.session_state.index_summary = f"{len(chunks)} clauses · {pages} pages · search: {index.mode}"
    st.session_state.indexed_pdf_name = file_key  # set last so a crash mid-scan retries on rerun

with st.sidebar:
    st.caption(f"📄 {uploaded.name}")
    st.caption(st.session_state.index_summary)

render_redflags(st.session_state.redflags, st.session_state.redflags_error)

st.divider()
st.subheader("💬 Ask about your contract")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("error"):
            st.error(msg["content"])
        elif msg["role"] == "assistant":
            st.markdown(with_citation_badges(msg["content"]), unsafe_allow_html=True)
        else:
            st.markdown(msg["content"])
        if msg.get("sources"):
            render_sources(msg["sources"])

typed = st.chat_input("Ask a question about this contract in English, Tagalog, or Bisaya...")
prompt = typed or st.session_state.pop("pending_prompt", None)
if prompt:
    answer(prompt)
    st.rerun()

st.caption("Try a starter question:")
for i, (col, (tag, question)) in enumerate(zip(st.columns(2) * 2, STARTERS)):
    col.button(f"`[{tag}]` {question}", key=f"starter_{i}", width="stretch",
               on_click=st.session_state.__setitem__, args=("pending_prompt", question))
