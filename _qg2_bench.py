"""
Quality Gate 2 benchmark — hermes-4.3-36b via /api/load + OpenAI client gen.
Assumes the FastAPI server is already listening on :5000.
"""
import time, json, sys
import urllib.request
import urllib.error

API = "http://127.0.0.1:5000"
LMS_OPENAI = "http://127.0.0.1:1234/v1"

def http_json(method, path, body=None, timeout=300):
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={"Content-Type": "application/json"} if body else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read()) if e.headers.get("content-type","" ).startswith("application/json") else e.read().decode("utf-8","replace")

print("=== 1. POST /api/load — hermes-4.3-36b ===")
body = {
    "model_key": "hermes-4.3-36b",
    "identifier": "_qg2_hermes",
    "config": {
        "context_length": 131072,
        "flashAttention": True,
        "maxParallelPredictions": 1,
    },
    "ttl": None,
    "force_reload": True,
}
t0 = time.monotonic()
code, resp = http_json("POST", "/api/load", body, timeout=600)
elapsed = time.monotonic() - t0
print(f"HTTP {code} | wall-clock load: {elapsed:.2f}s")
print(json.dumps(resp, indent=2, default=str))
if code != 200:
    sys.exit(2)

print()
print("=== 2. Real generation through OpenAI client ===")
try:
    from openai import OpenAI
except ImportError:
    print("openai package not available, skipping gen")
    sys.exit(0)
c = OpenAI(base_url=LMS_OPENAI, api_key="lm-studio")
prompt = ("Write a 200-word description of a baroque-mechanical clock tower at twilight, "
          "with a focus on the gears and brass mechanisms.")
t0 = time.monotonic()
r = c.chat.completions.create(
    model="_qg2_hermes",
    messages=[{"role":"user","content": prompt}],
    temperature=0.7,
    max_tokens=400,
)
gen_elapsed = time.monotonic() - t0
text = r.choices[0].message.content or ""
pt = r.usage.prompt_tokens
ct = r.usage.completion_tokens
print(f"prompt_tokens: {pt}")
print(f"completion_tokens: {ct}")
print(f"wall_clock_s: {gen_elapsed:.2f}")
print(f"tokens_per_second: {ct / gen_elapsed:.2f}" if gen_elapsed > 0 else "tps: n/a")
print()
print("=== first 400 chars of output ===")
print(text[:400])

print()
print("=== 3. Cleanup ===")
code, resp = http_json("DELETE", "/api/load/_qg2_hermes")
print(f"DELETE HTTP {code}: {resp}")
