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


# canned red-flag scan for samples/sample_lease.pdf (deliberately unsorted, so the app's sorting is exercised)
MOCK_FLAGS = [
    {"category": "Rent & Price Escalation", "risk": "Medium", "page": 2,
     "clause_summary": "The PHP 300 monthly maintenance and Wi-Fi fee may be adjusted by the lessor without prior notice.",
     "plain_explanation": "The landlord can raise this fee whenever they want and you have no say or warning."},
    {"category": "Deposit & Refund", "risk": "High", "page": 1,
     "clause_summary": "The two-month security deposit is non-refundable if the lessee leaves before the end of the term for any reason.",
     "plain_explanation": "If you move out early for any reason, even an emergency, you lose PHP 7,000."},
    {"category": "Rent & Price Escalation", "risk": "Low", "page": 1,
     "clause_summary": "Electricity and water are billed separately at rates set solely by the lessor.",
     "plain_explanation": "You can't check if utility charges are fair. Ask to see the actual meter readings and bills."},
    {"category": "Termination & Eviction", "risk": "High", "page": 2,
     "clause_summary": "If the lessee ends the lease early, they forfeit the deposit and must pay rent for all remaining months.",
     "plain_explanation": "Leaving early could cost you the deposit plus up to a year of rent, even though you no longer live there."},
    {"category": "Auto-Renewal", "risk": "Medium", "page": 1,
     "clause_summary": "The lease renews for another 12 months unless the lessee gives written notice 60 days before expiry.",
     "plain_explanation": "If you forget to send written notice 2 months early, you are locked in for another full year."},
    {"category": "Penalties & Surcharges", "risk": "High", "page": 1,
     "clause_summary": "Rent paid after the 5th incurs a PHP 200 penalty per day until fully paid.",
     "plain_explanation": "Being 2 weeks late adds PHP 2,800, almost a full month's rent. This penalty is very high."},
    {"category": "Termination & Eviction", "risk": "High", "page": 2,
     "clause_summary": "The lessor may terminate the lease at any time with only seven days notice.",
     "plain_explanation": "The landlord can make you leave with just one week's warning, while you are locked in for a year."},
]


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
        if "red-flag scan" in last.lower():
            reply = f"```json\n{json.dumps(MOCK_FLAGS, indent=2)}\n```"  # fenced, like real models often do
        elif "Keywords:" in last:
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
