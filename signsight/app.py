"""Basa Streamlit UI. Run: streamlit run app.py  (add ?sample=1 to the URL to auto-load the sample lease)"""
import html
import re
from pathlib import Path
from urllib.parse import quote

import streamlit as st

import llm
from ingest import extract_chunks_from_pdf
from redflags import scan_contract
from retrieve import ContractIndex, ask_contract, summarize_contract

st.set_page_config(page_title="Basa — Know What You're About to Sign", page_icon="👁️", layout="wide",
                   initial_sidebar_state="collapsed")

SAMPLE_PDF = Path(__file__).with_name("samples") / "sample_lease.pdf"

for key, value in {
    "indexed_pdf_name": None, "contract_index": None, "doc_name": "", "index_summary": "", "messages": [],
    "redflags": None, "redflags_error": None, "view": "home", "use_sample": False, "uploader_key": 0,
    "pending": None, "notice": None, "show_starters": False,
}.items():
    st.session_state.setdefault(key, value)

RISK_STYLE = {  # risk -> (Streamlit markdown color, badge label, metric label)
    "High": ("red", "🚨 High Risk", "🚨 High"),
    "Medium": ("orange", "⚠️ Medium Risk", "⚠️ Medium"),
    "Low": ("green", "ℹ️ Low Risk", "ℹ️ Low"),
}

LANGUAGES = {  # selector label -> reply language passed to the model (None = match the question)
    "🌐 Explain in my language": None,
    "🌐 Explain in English": "English",
    "🌐 Explain in Tagalog": "Tagalog",
    "🌐 Explain in Bisaya": "Bisaya (Cebuano)",
}

STARTERS = [  # (language tag, question)
    ("EN", "Can I get my deposit back if I leave early?"),
    ("TL", "May penalty ba kapag late ang upa?"),
    ("CEB", "Unsa mahitabo kung mo-hawa ko sayo?"),
    ("TEST", "Allowed ba ang pets sa property?"),
]

ASSISTANT_AVATAR = ":material/visibility:"
CITATION = re.compile(r"\[p\.\s*(\d+)\]")  # \s also matches the narrow no-break space some models emit
NO_DOC = "Upload a contract first, or try the sample boarding house lease below."

ICONS = {  # inline line icons (feather/lucide style)
    "flag": '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>',
    "chat": '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 '
            '8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
    "check": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>'
             '<path d="m9 15 2 2 4-4"/>',
    "file": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
    "chip": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 '
            '1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>',
}

FEATURES = [  # (icon, badge class, icon color, text, caption)
    ("flag", "coral", "#EF4444", "Scan any contract for red flags like lost deposits, penalties, and hidden fees.",
     "Red-flag scan"),
    ("chat", "teal", "#0D9488",
     "Ask anything in English, Tagalog, or Bisaya and get answers straight from your document.", "Ask in your language"),
    ("check", "blue", "#2563EB", "Every answer cites the exact clause and page, so you can check it yourself.",
     "Cited answers"),
]

CSS = """
<style>
:root {
    --canvas: #EEF2F7; --card: #FFFFFF; --line: #E2E8F0; --ink: #0F172A; --ink-2: #475569; --muted: #94A3B8;
    --pill: #111827; --pill-hover: #1F2937; --teal: #2DD4BF; --cite: #4F46E5;
    --shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 10px 30px -14px rgba(15, 23, 42, 0.18);
}

/* chrome: no Streamlit header/menu/footer; the sidebar is unused (upload lives in the top bar) */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stSidebar"], [data-testid="stExpandSidebarButton"] { display: none; }

/* canvas + elevated white card */
.stApp {
    background:
        radial-gradient(1100px 600px at 0% 0%, #E0E7FF 0%, transparent 60%),
        radial-gradient(900px 600px at 100% 100%, #DBEAFE 0%, transparent 55%),
        var(--canvas);
}
[data-testid="stMainBlockContainer"] {
    max-width: 1040px; margin: 28px auto 40px; padding: 24px 40px 28px;
    background: var(--card); border: 1px solid var(--line); border-radius: 24px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 30px 70px -30px rgba(15, 23, 42, 0.25);
}

/* left icon dock */
.st-key-rail {
    position: fixed; top: 28px; bottom: 28px; left: max(16px, calc(50% - 520px - 80px)); width: 56px; z-index: 99;
    display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 4px 0;
}
.st-key-rail .stElementContainer { width: auto !important; }
.st-key-rail button {
    width: 44px; height: 44px; min-height: 44px; padding: 0; border-radius: 50%;
    background: #fff; color: var(--ink); border: 1px solid var(--line); box-shadow: var(--shadow);
}
.st-key-rail button:hover { border-color: var(--pill); color: var(--ink); }
.st-key-rail button p, .st-key-rail button span[role="img"] { font-size: 20px !important; line-height: 1; }
.st-key-nav_new button, .st-key-nav_home button { background: var(--pill); color: #fff; border-color: var(--pill); }
.st-key-nav_home button { color: var(--teal); }
.st-key-nav_new button:hover, .st-key-nav_home button:hover { background: var(--pill-hover); color: #fff; }
.st-key-nav_home { margin-top: auto; }

/* top utility bar */
.st-key-lang { max-width: 250px; }
.st-key-lang [role="group"] { border-color: transparent; background: transparent; box-shadow: none; }
.st-key-lang [role="group"]:hover { background: #F4F6FB; }
.st-key-lang input { color: var(--ink-2); font-weight: 500; cursor: pointer; }
.brand-label { text-align: center; font-weight: 600; font-size: 15px; color: var(--ink); }
.st-key-upload_pop button {
    background: var(--pill); color: #fff; border: none; border-radius: 999px; padding: 8px 20px; font-weight: 600;
}
.st-key-upload_pop button:hover { background: var(--pill-hover); color: #fff; }
[data-testid="stPopoverBody"] { border-radius: 16px; border: 1px solid var(--line); }

/* hero + mascot */
.hero { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin: 36px 0 24px; }
.hero-title {
    font-size: clamp(34px, 5vw, 50px); font-weight: 700; line-height: 1.08; letter-spacing: -0.02em; color: var(--ink);
    max-width: 560px;
}
.hero-title span { color: #64748B; }
.hero-sub { margin-top: 14px; font-size: 16px; color: var(--ink-2); max-width: 520px; }
.hero-sub b { color: var(--ink); }
.mascot { position: relative; width: 240px; height: 140px; flex-shrink: 0; }
.bot {
    position: absolute; left: 10px; top: 26px; width: 100px; height: 100px; border-radius: 50%;
    background: radial-gradient(circle at 35% 30%, #FFFFFF 0%, #EEF2F7 60%, #DCE3EE 100%);
    box-shadow: 0 18px 40px -12px rgba(79, 70, 229, 0.35), inset 0 -6px 14px rgba(15, 23, 42, 0.06);
    display: flex; align-items: center; justify-content: center; animation: float 4s ease-in-out infinite;
}
.visor {
    width: 64px; height: 36px; border-radius: 12px; background: var(--pill);
    display: flex; align-items: center; justify-content: center; gap: 12px;
}
.visor i { width: 12px; height: 7px; border: 3px solid var(--teal); border-bottom: none; border-radius: 10px 10px 0 0; }
.bubble {
    position: absolute; right: 0; top: 0; background: #fff; border: 1px solid var(--line); border-radius: 14px;
    padding: 8px 12px; font-size: 13px; line-height: 1.35; color: var(--ink); box-shadow: var(--shadow);
}
@keyframes float { 50% { transform: translateY(-6px); } }

/* feature cards */
.features { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 8px; }
.feature {
    background: #fff; border: 1px solid var(--line); border-radius: 20px; padding: 22px; box-shadow: var(--shadow);
    display: flex; flex-direction: column;
}
.badge-icon { width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; }
.badge-icon .ico { width: 20px; height: 20px; }
.coral { background: #FEE2E2; } .teal { background: #CCFBF1; } .blue { background: #DBEAFE; }
.feature p { font-size: 18px; line-height: 1.4; color: var(--ink); margin: 26px 0 28px; flex-grow: 1; }
.feature small { font-size: 13px; color: #64748B; }

/* document header + scoreboard */
.doc-chip { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 18px 0 6px; font-size: 15px; }
.doc-chip .ico { width: 18px; height: 18px; }
.doc-chip span { color: #64748B; font-size: 13px; }
[data-testid="stMetric"] {
    background: #fff; border: 1px solid var(--line) !important; border-radius: 16px; padding: 14px 18px;
    box-shadow: var(--shadow);
}

/* cards: red-flag findings, clauses, chat turns, expanders */
[class*="st-key-flag_"], [class*="st-key-clause_"] {
    background: #fff; border: 1px solid var(--line) !important; border-radius: 16px; box-shadow: var(--shadow);
}
[data-testid="stChatMessage"] { background: #F8FAFC; border: 1px solid var(--line); border-radius: 16px; padding: 0.9rem 1rem; }
[data-testid="stExpander"] details { border-radius: 12px; border-color: var(--line); }

/* page citations */
.cite {
    display: inline-block; padding: 0 0.45em; border-radius: 6px; font-size: 0.8em; font-weight: 600; white-space: nowrap;
    color: var(--cite); background: #EEF2FF; border: 1px solid #C7D2FE;
}

/* bottom command dock */
.st-key-dock {
    background: #F1F5F9; border: 1px solid var(--line); border-radius: 22px; padding: 4px 8px 8px; margin-top: 22px; gap: 2px;
}
.st-key-sample_btn button { color: var(--ink-2); font-size: 13px; }
.st-key-sample_btn button:hover { color: var(--ink); }
.powered { display: flex; align-items: center; justify-content: flex-end; gap: 6px; font-size: 13px; color: var(--ink-2); padding-right: 8px; }
.powered .ico { width: 15px; height: 15px; }
.st-key-dock_inner {
    background: #fff; border: 1px solid var(--line); border-radius: 18px; padding: 10px 14px 14px; box-shadow: var(--shadow);
}
.st-key-dock_inner [data-testid="stChatInput"], .st-key-dock_inner [data-testid="stChatInput"] > div {
    border: none; background: transparent; box-shadow: none;
}
[data-testid="stChatInputSubmitButton"] { background: var(--pill); color: #fff; border-radius: 50%; }
[data-testid="stChatInputSubmitButton"]:disabled { background: var(--pill); color: #fff; opacity: 0.85; }
.st-key-chips button {
    background: var(--pill); color: #fff; border: none; border-radius: 999px; padding: 6px 16px; min-height: 38px;
    font-weight: 600; font-size: 14px;
}
.st-key-chips button:hover { background: var(--pill-hover); color: #fff; }
.st-key-chips button:focus:not(:active) { color: #fff; }
.st-key-starters { margin-top: 2px; }
.st-key-starters button {
    background: #F8FAFC; color: var(--ink); border: 1px solid var(--line); border-radius: 999px; min-height: 34px;
    font-size: 13px; padding: 4px 14px;
}
.st-key-starters button:hover { border-color: var(--pill); color: var(--ink); background: #fff; }
.st-key-starters code { background: #EEF2FF; color: var(--cite); font-size: 11px; }

/* narrow screens: rail would overlap the card */
@media (max-width: 1200px) {
    [data-testid="stMainBlockContainer"] { margin-left: 84px; margin-right: 16px; max-width: calc(100vw - 100px); }
}
@media (max-width: 720px) {
    .st-key-rail { display: none; }
    [data-testid="stMainBlockContainer"] { margin: 12px 8px; padding: 16px; max-width: calc(100vw - 16px); }
    .hero { flex-direction: column; align-items: flex-start; }
    .features { grid-template-columns: 1fr; }
}
</style>
"""


def svg(name, color="#0F172A"):
    """Icon as a data-URI <img>: st.html strips inline <svg> elements."""
    body = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')
    return f'<img class="ico" alt="" src="data:image/svg+xml;utf8,{quote(body)}">'


def with_citation_badges(text):
    """Escape model output (it may echo contract text) and turn [p. N] tags into styled badges."""
    return CITATION.sub(r'<span class="cite">p. \1</span>', html.escape(text, quote=False))


# ---- callbacks: widgets only record what to do; the script body does the work in the right place ----

def notify(message):
    st.session_state.notice = message


def queue(kind, text, language=None):
    st.session_state.pending = {"kind": kind, "text": text, "language": language}
    st.session_state.show_starters = False


def toggle_starters():
    st.session_state.show_starters = not st.session_state.show_starters


def on_chat_submit():
    text = (st.session_state.get("chat_box") or "").strip()
    if text:
        queue("ask", text)


def set_view(view):
    if st.session_state.contract_index is None and view != "home":
        notify(NO_DOC)
    else:
        st.session_state.view = view


def load_sample():
    st.session_state.use_sample = True
    st.session_state.uploader_key += 1  # clears any uploaded file so the sample wins


def on_upload():
    st.session_state.use_sample = False


def new_session():
    for key in ("indexed_pdf_name", "contract_index", "redflags", "redflags_error", "pending"):
        st.session_state[key] = None
    st.session_state.update(messages=[], doc_name="", index_summary="", use_sample=False, view="home")
    st.session_state.uploader_key += 1


# ---- rendering ----

def render_hero():
    st.html(
        '<div class="hero">'
        '<div><div class="hero-title" role="heading" aria-level="1"><span>Hi there,</span> Know What You\'re About to '
        'Sign?</div><div class="hero-sub"><b>Basa</b> — AI-powered contract risk scanner &amp; multilingual legal '
        'assistant for Filipinos.</div></div>'
        '<div class="mascot" aria-hidden="true"><div class="bubble">Got a contract?<br>Let me read it first.</div>'
        '<div class="bot"><div class="visor"><i></i><i></i></div></div></div>'
        '</div>'
    )
    cards = "".join(
        f'<div class="feature"><div class="badge-icon {cls}">{svg(icon, color)}</div><p>{text}</p>'
        f'<small>{caption}</small></div>'
        for icon, cls, color, text, caption in FEATURES
    )
    st.html(f'<div class="features">{cards}</div>')


def render_doc_header():
    st.html(f'<div class="doc-chip">{svg("file")}<b>{html.escape(st.session_state.doc_name)}</b>'
            f'<span>{st.session_state.index_summary}</span></div>')
    flags = st.session_state.redflags
    if flags is not None:
        for col, (risk, (_, _, metric_label)) in zip(st.columns(len(RISK_STYLE)), RISK_STYLE.items()):
            col.metric(metric_label, sum(f["risk"] == risk for f in flags))


def render_redflags(flags, error):
    st.subheader("Red flags")
    if error:
        st.warning(f"Red-flag scan unavailable: {error}")
        return
    if not flags:
        st.success("No major red flags detected.")
        return
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


def render_sources(sources):
    with st.expander("View Cited Clauses"):
        for s in sources:
            st.markdown(f"**Page {s['page']}**")
            st.markdown("> " + s["text"].replace("\n", "\n> "))


def render_message(msg):
    with st.chat_message(msg["role"], avatar=ASSISTANT_AVATAR if msg["role"] == "assistant" else None):
        if msg.get("error"):
            st.error(msg["content"])
        elif msg["role"] == "assistant":
            st.markdown(with_citation_badges(msg["content"]), unsafe_allow_html=True)
        else:
            st.markdown(msg["content"])
        if msg.get("sources"):
            render_sources(msg["sources"])


def render_chat(pending):
    if not st.session_state.messages and not pending:
        st.caption(f"Ask anything about {st.session_state.doc_name} in English, Tagalog, or Bisaya, "
                   "or tap a chip below.")
    for msg in st.session_state.messages:
        render_message(msg)


def render_clauses(index):
    st.subheader("Contract clauses")
    for c in index.chunks:
        with st.container(border=True, key=f"clause_{c['chunk_id']}"):
            st.html(f'<span class="cite">p. {c["page"]}</span>')
            st.markdown(c["text"])


def render_history():
    st.subheader("History")
    questions = [m for m in st.session_state.messages if m["role"] == "user"]
    if not questions:
        st.caption("No questions yet.")
    for n, q in enumerate(questions, start=1):
        st.markdown(f"{n}. {q['content']}")


def run_pending(action, language):
    """Show the request, call the model, and store both turns in st.session_state.messages.

    Both turns are stored only once the reply exists: clicking anything mid-request interrupts this
    script run, and we'd rather drop the question than leave it unanswered in the history.
    """
    user_msg = {"role": "user", "content": action["text"]}
    render_message(user_msg)
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        with st.spinner("Consulting contract context..."):
            index = st.session_state.contract_index
            try:
                if action["kind"] == "summary":
                    result = summarize_contract(index, action["language"] or language or "English")
                else:
                    result = ask_contract(index, action["text"], language=language)
                reply = {"role": "assistant", "content": result["answer"], "sources": result["sources"]}
            except llm.LLMError as e:
                reply = {"role": "assistant", "content": f"Basa couldn't reach the AI service: {e}", "error": True}
            except Exception:
                reply = {"role": "assistant", "content": "Something went wrong while answering. Please try again.",
                         "error": True}
    st.session_state.messages.extend([user_msg, reply])


def load_contract(source, file_key, name, size):
    """Ingest + red-flag scan, once per file. Returns a friendly error message, or None on success."""
    if size == 0:
        return "This file is empty. Please upload the contract PDF again."
    with st.spinner("Ingesting contract clauses..."):
        try:
            chunks = extract_chunks_from_pdf(source)
            index = ContractIndex(chunks) if chunks else None
        except Exception:
            return "Could not read this PDF. Please make sure it is a valid, non-password-protected PDF."
    if not chunks:
        return "No text found in this PDF. It may be a scanned photo; please upload a text-based (digital) PDF."
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
    st.session_state.update(doc_name=name, view="flags",
                            index_summary=f"{len(chunks)} clauses · {pages} pages · search: {index.mode}")
    st.session_state.indexed_pdf_name = file_key  # set last so a crash mid-scan retries on rerun
    return None


# ---- page ----

st.html(CSS)
st.html(f"<style>.st-key-nav_{st.session_state.view} button {{ border-color: var(--pill); }}</style>")

if st.query_params.get("sample") == "1" and not st.session_state.get("sample_param_used"):
    st.session_state.sample_param_used = True
    load_sample()

with st.container(key="rail"):
    st.button(":material/add:", key="nav_new", help="New contract", on_click=new_session)
    st.button(":material/search:", key="nav_ask", help="Ask about the contract", on_click=set_view, args=("ask",))
    st.button(":material/flag:", key="nav_flags", help="Red flags", on_click=set_view, args=("flags",))
    st.button(":material/description:", key="nav_doc", help="Contract clauses", on_click=set_view, args=("doc",))
    st.button(":material/history:", key="nav_history", help="History", on_click=set_view, args=("history",))
    st.button(":material/visibility:", key="nav_home", help="Basa home", on_click=set_view, args=("home",))

left, center, right = st.columns([3, 2, 3], vertical_alignment="center")
with left:
    language = LANGUAGES[st.selectbox("Answer language", list(LANGUAGES), key="lang", label_visibility="collapsed")]
with center:
    st.html('<div class="brand-label">Basa</div>')
with right:
    with st.container(horizontal=True, horizontal_alignment="right"):
        with st.popover("Upload contract", icon=":material/upload:", key="upload_pop"):
            uploaded = st.file_uploader("Upload a contract PDF", type=["pdf"], on_change=on_upload,
                                        key=f"uploader_{st.session_state.uploader_key}")
            st.caption("Leases, job contracts, or loan agreements. Text-based PDFs only.")

source = None
if uploaded is not None:
    source, file_key, name, size = uploaded, f"{uploaded.name}:{uploaded.size}", uploaded.name, uploaded.size
elif st.session_state.use_sample:
    source, file_key, name, size = SAMPLE_PDF, f"sample:{SAMPLE_PDF.name}", SAMPLE_PDF.name, SAMPLE_PDF.stat().st_size

if source is not None and st.session_state.indexed_pdf_name != file_key:
    error = load_contract(source, file_key, name, size)
    if error:
        st.warning(error)
has_doc = source is not None and st.session_state.indexed_pdf_name == file_key

pending = st.session_state.pending
st.session_state.pending = None
if pending and not has_doc:
    notify(NO_DOC)
    pending = None
if pending:
    st.session_state.view = "ask"

if st.session_state.notice:
    st.toast(st.session_state.notice, icon=":material/info:")
    st.session_state.notice = None

view = st.session_state.view if has_doc else "home"
if view == "home":
    render_hero()
else:
    render_doc_header()
    if view == "flags":
        render_redflags(st.session_state.redflags, st.session_state.redflags_error)
    elif view == "doc":
        render_clauses(st.session_state.contract_index)
    elif view == "history":
        render_history()
    else:
        render_chat(pending)
        if pending:
            run_pending(pending, language)
            st.rerun()

with st.container(key="dock"):
    head_left, head_right = st.columns([3, 2], vertical_alignment="center")
    head_left.button("Try it with a sample boarding house lease", icon=":material/auto_awesome:", key="sample_btn",
                     type="tertiary", on_click=load_sample)
    model_name = html.escape(llm.MODEL.split("/")[-1]) or "the hackathon model"
    with head_right:
        st.html(f'<div class="powered">{svg("chip", "#475569")}Powered by {model_name}</div>')
    with st.container(key="dock_inner"):
        st.chat_input('Example: "Pwede ba ko mobalhin before 6 months?"', key="chat_box", on_submit=on_chat_submit)
        with st.container(key="chips", horizontal=True, wrap=True, gap="small"):
            st.button("Scan for red flags", icon=":material/flag:", key="chip_flags", on_click=set_view,
                      args=("flags",))
            st.button("Summarize contract", icon=":material/notes:", key="chip_summary", on_click=queue,
                      args=("summary", "Summarize this contract."))
            st.button("Explain in Bisaya", icon=":material/translate:", key="chip_bisaya", on_click=queue,
                      args=("summary", "I-explain ang kontrata sa Bisaya.", "Bisaya (Cebuano)"))
            st.button("Compare two contracts", icon=":material/compare:", key="chip_compare", on_click=notify,
                      args=("Compare two contracts is coming soon.",))
            st.button(":material/more_horiz:", key="chip_more", help="Starter questions", on_click=toggle_starters)
        if st.session_state.show_starters:
            with st.container(key="starters", horizontal=True, wrap=True, gap="small"):
                for i, (tag, question) in enumerate(STARTERS):
                    st.button(f"`[{tag}]` {question}", key=f"starter_{i}", on_click=queue, args=("ask", question))
