#!/usr/bin/env python3
"""Generate realistic Beats-style documents containing three incidents, so each watcher has something to catch.

Incidents (all relative to "now", so they fall inside the watchers' time windows):
    cpu     host app-02 sustains ~93% CPU for the last 8 minutes   -> high-cpu
    errors  'checkout' logs ~90 error lines in the last 8 minutes   -> error-spike
    down    monitor 'payments-api' reports DOWN for the last 4 min  -> service-heartbeat-missing

Usage:
    python3 generate_sample_data.py --out sample.ndjson          # write Elasticsearch _bulk file
    ES_URL=http://localhost:9200 python3 generate_sample_data.py --push   # template + bulk load
"""
import argparse
import json
import os
import random
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

HOSTS = ["app-01", "app-02", "app-03"]
SERVICES = ["checkout", "search", "profile"]

TEMPLATE = {
    "index_patterns": ["metricbeat-demo*", "filebeat-demo*", "heartbeat-demo*"],
    "template": {
        "mappings": {
            "properties": {
                "@timestamp": {"type": "date"},
                "host": {"properties": {"name": {"type": "keyword"}}},
                "event": {"properties": {"module": {"type": "keyword"}}},
                "log": {"properties": {"level": {"type": "keyword"}}},
                "service": {"properties": {"name": {"type": "keyword"}}},
                "monitor": {"properties": {"name": {"type": "keyword"}, "status": {"type": "keyword"}}},
                "system": {"properties": {"cpu": {"properties": {"total": {"properties": {
                    "norm": {"properties": {"pct": {"type": "float"}}}}}}}}},
            }
        }
    },
}


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def generate(now=None, seed=7):
    rnd = random.Random(seed)
    now = now or datetime.now(timezone.utc)
    docs = []

    # --- metricbeat: 30-minute history, a CPU sustained spike on app-02 in the last 8 minutes ---
    for step in range(60):                       # every 30 s
        ts = now - timedelta(seconds=30 * step)
        for host in HOSTS:
            spiking = host == "app-02" and step < 16
            cpu = rnd.uniform(0.90, 0.97) if spiking else rnd.uniform(0.15, 0.45)
            docs.append(("metricbeat-demo", {
                "@timestamp": iso(ts), "host": {"name": host}, "event": {"module": "system"},
                "system": {"cpu": {"total": {"norm": {"pct": round(cpu, 3)}}}},
            }))

    # --- filebeat: background noise + an error burst from checkout in the last 8 minutes ---
    for i in range(300):
        ts = now - timedelta(seconds=rnd.uniform(0, 1800))
        docs.append(("filebeat-demo", {"@timestamp": iso(ts), "log": {"level": rnd.choice(["info", "info", "warn"])},
                                       "service": {"name": rnd.choice(SERVICES)}}))
    for i in range(90):
        ts = now - timedelta(seconds=rnd.uniform(0, 480))
        docs.append(("filebeat-demo", {"@timestamp": iso(ts), "log": {"level": "error"}, "service": {"name": "checkout"}}))
    for i in range(5):  # a little unrelated error noise
        ts = now - timedelta(seconds=rnd.uniform(600, 1800))
        docs.append(("filebeat-demo", {"@timestamp": iso(ts), "log": {"level": "error"}, "service": {"name": "search"}}))

    # --- heartbeat: payments-api goes DOWN 4 minutes ago ---
    for step in range(30):                       # every minute
        ts = now - timedelta(minutes=step)
        for mon in ("web-frontend", "payments-api"):
            down = mon == "payments-api" and step < 4
            docs.append(("heartbeat-demo", {"@timestamp": iso(ts),
                                            "monitor": {"name": mon, "status": "down" if down else "up"}}))
    return docs


def to_bulk(docs) -> str:
    lines = []
    for index, doc in docs:
        lines.append(json.dumps({"index": {"_index": index}}))
        lines.append(json.dumps(doc))
    return "\n".join(lines) + "\n"


def _req(method, url, body, ctype="application/json"):
    req = urllib.request.Request(url, data=body.encode() if isinstance(body, str) else body, method=method,
                                 headers={"Content-Type": ctype})
    token = os.getenv("ES_API_KEY")
    if token:
        req.add_header("Authorization", f"ApiKey {token}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", help="write _bulk NDJSON to this file")
    ap.add_argument("--push", action="store_true", help="install index template and bulk-load into $ES_URL")
    args = ap.parse_args()
    docs = generate()
    bulk = to_bulk(docs)

    if args.out:
        with open(args.out, "w") as fh:
            fh.write(bulk)
        print(f"wrote {len(docs)} documents to {args.out}")
    if args.push:
        es = os.environ.get("ES_URL", "http://localhost:9200").rstrip("/")
        _req("PUT", f"{es}/_index_template/demo-beats", json.dumps(TEMPLATE))
        res = _req("POST", f"{es}/_bulk?refresh=true", bulk, "application/x-ndjson")
        print(f"bulk indexed {len(docs)} docs, errors={res.get('errors')}")
        if res.get("errors"):
            return 1
    if not args.out and not args.push:
        ap.error("use --out and/or --push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
