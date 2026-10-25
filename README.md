# kibana-watcher-examples

Version-controlled **Elasticsearch/Kibana Watcher** definitions for environment health monitoring, plus a small script to deploy them through the Watcher API. Treating alerts as code means they're reviewable, repeatable across environments and easy to roll back.

## Watchers

| File | Index | Fires when |
|------|-------|-----------|
| `high-cpu.json` | `metricbeat-*` | A host's average CPU stays above 85% over 5 min (lists offending hosts) |
| `error-spike.json` | `filebeat-*` | More than 50 `error` logs in 10 min, with top services |
| `service-heartbeat-missing.json` | `heartbeat-*` | Any monitor reports `down`; includes a throttled webhook action |

Thresholds and windows live in each watcher's `metadata` block so they're easy to tune. Field names follow ECS conventions - adjust index patterns and fields to match your data.

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
