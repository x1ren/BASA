"""Phase 5 headless UI test (uses the live API in .env): python test_app.py

Uploads samples/sample_lease.pdf, clicks every starter question, types one question,
asks for a Bisaya summary, and checks the red-flag scan ran exactly once.
"""
import sys
import time
from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

import redflags

HERE = Path(__file__).parent
PDF = HERE / "samples" / "sample_lease.pdf"


class FakeUpload:  # stands in for Streamlit's UploadedFile (AppTest can't drive file_uploader)
    def __init__(self, path):
        self.name, self._data = path.name, path.read_bytes()
        self.size = len(self._data)

    def getvalue(self):
        return self._data


scan_calls = 0
_real_scan = redflags.scan_contract


def counting_scan(index):
    global scan_calls
    scan_calls += 1
    return _real_scan(index)


redflags.scan_contract = counting_scan
st.file_uploader = lambda *a, **k: FakeUpload(PDF)
sys.stdout.reconfigure(errors="replace")

at = AppTest.from_file(str(HERE / "app.py"), default_timeout=180).run()
assert not at.exception, at.exception
flags = at.session_state["redflags"]
print(f"Upload -> scan_calls={scan_calls}, red flags={len(flags or [])}, error={at.session_state['redflags_error']}")
print("Metrics:", [(m.label, m.value) for m in at.metric])

PAUSE = 20  # seconds between questions, like a human demo (Groq free tier: ~1000 output tokens/min)
for i in range(4):
    time.sleep(PAUSE)
    at.button(key="chip_more").click().run()  # "•••" reveals the starter questions
    at.button(key=f"starter_{i}").click().run()
    assert not at.exception, at.exception
time.sleep(PAUSE)
at.chat_input[0].set_value("Pwede ba mag-alaga ng aso?").run()
assert not at.exception, at.exception
time.sleep(PAUSE)
at.button(key="chip_bisaya").click().run()  # whole-contract summary in Bisaya
assert not at.exception, at.exception

msgs = at.session_state["messages"]
for m in msgs:
    tag = "Q" if m["role"] == "user" else ("ERR" if m.get("error") else "A")
    print(f"\n{tag}: {m['content']}")

print(f"\nscan_calls after 6 requests = {scan_calls} (expected 1)")
print(f"messages = {len(msgs)} (expected 12)")
assert scan_calls == 1 and len(msgs) == 12
assert not any(m.get("error") for m in msgs), "an answer failed (rate limit?)"
assert all("[p." in m["content"] for m in msgs[1:6:2]), "expected page citations on deposit/penalty/Bisaya answers"
print("PASS")
