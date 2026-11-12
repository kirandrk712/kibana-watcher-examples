# kibana-watcher-examples

[![Validate](https://github.com/kirandrk712/kibana-watcher-examples/actions/workflows/validate.yml/badge.svg)](https://github.com/kirandrk712/kibana-watcher-examples/actions/workflows/validate.yml)

Version-controlled **Elasticsearch/Kibana Watcher** definitions for environment health monitoring, plus a small script to deploy them through the Watcher API. Treating alerts as code means they're reviewable, repeatable across environments and easy to roll back.

## Watchers

| File | Index | Fires when |
|------|-------|-----------|
| `high-cpu.json` | `metricbeat-*` | A host's average CPU stays above 85% over 5 min (lists offending hosts) |
| `error-spike.json` | `filebeat-*` | More than 50 `error` logs in 10 min, with top services |
| `service-heartbeat-missing.json` | `heartbeat-*` | Any monitor reports `down`; includes a throttled webhook action |

Thresholds and windows live in each watcher's `metadata` block so they're easy to tune. Field names follow ECS conventions - adjust index patterns and fields to match your data.

## Try it live (about 5 minutes, needs Docker)

The repo ships a local Elastic stack and a generator that creates **three incidents** in Beats-style data, so every watcher has something real to catch:

| Incident in the data | Watcher that should fire |
|---|---|
| `app-02` sustains ~93% CPU for 8 minutes (other hosts normal) | `high-cpu` - names only `app-02` |
| `checkout` logs ~90 errors in 8 minutes | `error-spike` - lists `checkout` as the top service |
| `payments-api` heartbeat is DOWN for 4 minutes | `service-heartbeat-missing` |

```bash
docker compose up -d                                   # Elasticsearch + Kibana (trial licence, security off: dev only)
export ES_URL=http://localhost:9200
python3 scripts/generate_sample_data.py --push         # index template + sample incidents
python3 scripts/deploy_watchers.py                     # create the 3 watchers

# Run one now instead of waiting for its schedule:
curl -s -X POST "$ES_URL/_watcher/watch/high-cpu/_execute" -H 'Content-Type: application/json' \
     -d '{"record_execution": false}' | python3 -c "import sys,json; r=json.load(sys.stdin)['watch_record']; print('condition met:', r['result']['condition']['met'])"

docker compose logs elasticsearch | grep "High CPU"    # the logging action's output
```

Sample data is timestamped relative to "now", so re-run `--push` if more than ~10 minutes pass before you execute the watchers.

The unit tests (`python -m unittest discover -s tests -v`) verify offline that the generated data crosses each watcher's threshold **and only for the intended host/service**, so the demo data and watcher definitions can't drift apart.

## Deploy

```bash
export ES_URL=https://localhost:9200
export ES_API_KEY=<base64-api-key>        # or ES_USER / ES_PASSWORD

python3 scripts/deploy_watchers.py --dry-run   # validate JSON
python3 scripts/deploy_watchers.py             # create/update
python3 scripts/deploy_watchers.py --delete    # clean up
```

Test one without waiting for the schedule:

```bash
curl -X POST "$ES_URL/_watcher/watch/high-cpu/_execute" -H "Authorization: ApiKey $ES_API_KEY"
```

## Notes

- Watchers require a Gold+ / Platinum / trial license in self-managed Elastic.
- Swap the `logging` action for `email`, `slack` or `webhook` once connectors are configured.
- Use `throttle_period` on actions to avoid alert storms.
