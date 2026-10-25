#!/usr/bin/env python3
"""Create/update every watcher in ../watchers via the Elasticsearch Watcher API.

Environment:
    ES_URL      e.g. https://localhost:9200
    ES_API_KEY  base64 API key (preferred), or
    ES_USER / ES_PASSWORD for basic auth
    ES_VERIFY   set to "false" to skip TLS verification (dev only)

Usage:
    python3 deploy_watchers.py            # deploy all
    python3 deploy_watchers.py --dry-run  # validate JSON only
    python3 deploy_watchers.py --delete   # remove them
"""
import argparse
import base64
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

WATCHER_DIR = Path(__file__).resolve().parent.parent / "watchers"


def request(method: str, path: str, body=None):
    url = os.environ["ES_URL"].rstrip("/") + path
    headers = {"Content-Type": "application/json"}
    if os.getenv("ES_API_KEY"):
        headers["Authorization"] = f"ApiKey {os.environ['ES_API_KEY']}"
    elif os.getenv("ES_USER"):
        token = base64.b64encode(f"{os.environ['ES_USER']}:{os.environ.get('ES_PASSWORD', '')}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"

    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    ctx = None
    if os.getenv("ES_VERIFY", "true").lower() == "false":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        return json.loads(resp.read() or b"{}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delete", action="store_true")
    args = parser.parse_args()

    files = sorted(WATCHER_DIR.glob("*.json"))
    if not files:
        print("no watcher files found", file=sys.stderr)
        return 1

    failures = 0
    for f in files:
        watch_id = f.stem
        try:
            body = json.loads(f.read_text())
        except json.JSONDecodeError as exc:
            print(f"INVALID {f.name}: {exc}")
            failures += 1
            continue

        if args.dry_run:
            print(f"valid   {f.name}")
            continue
        try:
            if args.delete:
                request("DELETE", f"/_watcher/watch/{watch_id}")
                print(f"deleted {watch_id}")
            else:
                result = request("PUT", f"/_watcher/watch/{watch_id}", body)
                print(f"{'created' if result.get('created') else 'updated'} {watch_id}")
        except urllib.error.HTTPError as exc:
            print(f"FAILED  {watch_id}: HTTP {exc.code} {exc.read().decode()[:200]}")
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
