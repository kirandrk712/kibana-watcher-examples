"""Offline check that the sample data really trips each watcher's condition (and only the intended targets).

This re-implements each watcher's window/threshold logic in Python against the generated documents, reading the
thresholds out of the watcher JSON files - it does not need Elasticsearch.
"""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import generate_sample_data as gen  # noqa: E402

NOW = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)


def parse(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.000Z").replace(tzinfo=timezone.utc)


def window_minutes(w):
    return int(w.rstrip("m"))


class SampleDataTripsWatchers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = gen.generate(now=NOW)

    def watcher(self, name):
        return json.loads((ROOT / "watchers" / f"{name}.json").read_text())

    def test_every_watcher_file_is_valid_json_with_required_sections(self):
        for f in (ROOT / "watchers").glob("*.json"):
            w = json.loads(f.read_text())
            for key in ("trigger", "input", "condition", "actions"):
                self.assertIn(key, w, f"{f.name} missing {key}")

    def test_cpu_watcher_flags_only_app_02(self):
        w = self.watcher("high-cpu")
        since = NOW - timedelta(minutes=window_minutes(w["metadata"]["window"]))
        per_host = {}
        for idx, d in self.docs:
            if idx == "metricbeat-demo" and parse(d["@timestamp"]) >= since:
                per_host.setdefault(d["host"]["name"], []).append(d["system"]["cpu"]["total"]["norm"]["pct"])
        hot = {h for h, v in per_host.items() if sum(v) / len(v) > w["metadata"]["threshold"]}
        self.assertEqual(hot, {"app-02"})

    def test_error_watcher_exceeds_threshold_and_names_checkout(self):
        w = self.watcher("error-spike")
        since = NOW - timedelta(minutes=window_minutes(w["metadata"]["window"]))
        errors = [d for idx, d in self.docs if idx == "filebeat-demo" and d["log"]["level"] == "error"
                  and parse(d["@timestamp"]) >= since]
        self.assertGreater(len(errors), w["condition"]["compare"]["ctx.payload.hits.total"]["gt"])
        top = max({d["service"]["name"] for d in errors}, key=lambda s: sum(1 for d in errors if d["service"]["name"] == s))
        self.assertEqual(top, "checkout")

    def test_heartbeat_watcher_sees_payments_down_in_window(self):
        w = self.watcher("service-heartbeat-missing")
        since = NOW - timedelta(minutes=window_minutes(w["metadata"]["window"]))
        down = {d["monitor"]["name"] for idx, d in self.docs
                if idx == "heartbeat-demo" and d["monitor"]["status"] == "down" and parse(d["@timestamp"]) >= since}
        self.assertEqual(down, {"payments-api"})

    def test_healthy_hosts_stay_below_threshold(self):
        w = self.watcher("high-cpu")
        for idx, d in self.docs:
            if idx == "metricbeat-demo" and d["host"]["name"] != "app-02":
                self.assertLess(d["system"]["cpu"]["total"]["norm"]["pct"], w["metadata"]["threshold"])

    def test_bulk_format(self):
        lines = gen.to_bulk(self.docs).strip().split("\n")
        self.assertEqual(len(lines), len(self.docs) * 2)
        self.assertIn("index", json.loads(lines[0]))


if __name__ == "__main__":
    unittest.main()
