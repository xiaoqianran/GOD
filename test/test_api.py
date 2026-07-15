"""Call NewAPI-compatible chat completions and print raw JSON output."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# Defaults from the earlier manual test; override via env if needed.
BASE_URL = os.environ.get("API_BASE_URL", "https://newapi-jp2.xiaoqianran.xyz").rstrip("/")
API_KEY = (
    os.environ.get("API_KEY")
    or os.environ.get("GOD_LLM_API_KEY")
    or ""
)
MODEL = os.environ.get("MODEL") or os.environ.get("GOD_LLM_MODEL") or "openai/gpt-oss-120b"
PROMPT = os.environ.get("PROMPT", "Say hello in one short sentence.")
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "100"))


def main() -> int:
    if not API_KEY:
        print(
            "API_KEY (or GOD_LLM_API_KEY) is required. Export it before running.",
            file=sys.stderr,
        )
        return 2
    url = f"{BASE_URL}/v1/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False,
        "max_tokens": MAX_TOKENS,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            # Cloudflare often blocks the default Python-urllib User-Agent (1010).
            "User-Agent": "curl/8.5.0",
            "Accept": "application/json",
        },
    )

    print("=== request ===", file=sys.stderr)
    print(json.dumps({"url": url, **payload}, ensure_ascii=False, indent=2), file=sys.stderr)
    print("=== raw response ===", file=sys.stderr)

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        status = e.code
        print(raw)
        print(f"\n---HTTP_STATUS:{status}---", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"request failed: {e}", file=sys.stderr)
        return 1

    # Pretty-print if JSON; otherwise dump as-is.
    try:
        parsed = json.loads(raw)
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        print(raw)

    print(f"\n---HTTP_STATUS:{status}---", file=sys.stderr)
    return 0 if status == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
