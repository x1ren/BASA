"""Local fake of the hackathon API for testing without credentials. NOT a real model.

Usage:
  python mock_server.py            # terminal 1 (serves http://127.0.0.1:8765/v1)
  $env:HACKATHON_API_URL="http://127.0.0.1:8765/v1"; $env:HACKATHON_API_KEY="mock"; $env:HACKATHON_MODEL="mock"
  python retrieve.py               # terminal 2 (or: streamlit run app.py)

Env vars set in the shell take priority over signsight/.env.
"""
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8765

# crude keyword "translation" so query expansion can be exercised
KEYWORDS = {
    r"hawa|aalis|leave|terminat|umalis": "early termination leave lease forfeit",
    r"deposit|deposito|refund|ibabalik|balik": "security deposit refund non-refundable",
    r"late|na-late|bayad|upa|rent|abang": "rent late penalty payment per day",
    r"iro|iring|aso|pusa|pet|alaga": "pets animals dog cat",
    r"renew|renewal": "automatic renewal notice",
}


def fake_keywords(question):
    q = question.lower()
    return " ".join(v for pat, v in KEYWORDS.items() if re.search(pat, q)) or question


def fake_answer(user_msg):
    pages = sorted(set(re.findall(r"Clause \[p\. (\d+)\]", user_msg)))
    q = user_msg.rsplit("Question:", 1)[-1].split("\n")[0].strip()
    cites = " ".join(f"[p. {p}]" for p in pages)
    return f"[MOCK — not a real model] Question received: \"{q}\". Retrieved clauses from {cites}."


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[mock] {self.path}")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if not self.path.endswith("/chat/completions"):
            self.send_error(404)
            return
        last = body["messages"][-1]["content"]
        if "Keywords:" in last:
            reply = fake_keywords(last.split("Question:", 1)[1].split("Keywords:")[0])
        else:
            reply = fake_answer(last)
        out = json.dumps({"choices": [{"message": {"content": reply}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


if __name__ == "__main__":
    print(f"Mock API on http://127.0.0.1:{PORT}/v1  (Ctrl+C to stop)")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
