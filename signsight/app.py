"""Signsight Streamlit UI. Run: streamlit run app.py"""
import streamlit as st

import llm
from ingest import extract_chunks_from_pdf
from retrieve import ContractIndex, ask_contract

st.set_page_config(page_title="Signsight — Contract Analyzer", page_icon="📄", layout="centered")

st.session_state.setdefault("indexed_pdf_name", None)
st.session_state.setdefault("contract_index", None)
st.session_state.setdefault("chat_history", [])


def render_sources(sources):
    with st.expander("View Cited Clauses"):
        for s in sources:
            st.markdown(f"**Page {s['page']}**")
            st.markdown("> " + s["text"].replace("\n", "\n> "))


st.title("Signsight — See what you're signing.")
st.caption("Upload a lease, job contract, or loan agreement and ask about it in English, Tagalog, or Bisaya.")

with st.sidebar:
    st.header("Your contract")
    uploaded = st.file_uploader("Upload a PDF", type=["pdf"])

if uploaded is not None:
    file_key = f"{uploaded.name}:{uploaded.size}"
    if st.session_state.indexed_pdf_name != file_key:
        with st.spinner("Reading your contract..."):
            try:
                chunks = extract_chunks_from_pdf(uploaded)
            except Exception:
                st.error("Could not read this PDF. Is it a valid, non-password-protected file?")
                st.stop()
            if not chunks:
                st.error("No text found in this PDF. It may be a scanned image; please upload a text-based PDF.")
                st.stop()
            st.session_state.contract_index = ContractIndex(chunks)
            st.session_state.indexed_pdf_name = file_key
            st.session_state.chat_history = []
        pages = len({c["page"] for c in chunks})
        st.success(f"Indexed {len(chunks)} clauses across {pages} pages.")

    with st.sidebar:
        st.caption(f"📄 {uploaded.name} · search: {st.session_state.contract_index.mode}")
else:
    st.info("⬅️ Upload a contract PDF to get started.")
    st.stop()

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            render_sources(msg["sources"])

question = st.chat_input("Ask a question about this contract in English, Tagalog, or Bisaya...")
if question:
    st.session_state.chat_history.append({"role": "user", "content": question, "sources": []})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Checking the contract..."):
            try:
                result = ask_contract(st.session_state.contract_index, question)
            except llm.LLMError as e:
                result = None
                st.error(f"Signsight couldn't reach the AI service: {e}")
        if result:
            st.markdown(result["answer"])
            render_sources(result["sources"])
            st.session_state.chat_history.append(
                {"role": "assistant", "content": result["answer"], "sources": result["sources"]}
            )
