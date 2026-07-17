# Monitoring

The bot exposes health metrics in Prometheus format on `GET /metrics` (same port
as the webhook, 8080). No dashboard ships with this repo, four metrics don't
need one. Scrape them and alert on the three rules below, that covers the ways
this bot can actually break.

## Metrics

| Metric | Meaning |
|---|---|
| `bot_notifications_total{type=...}` | Notifications sent to Matrix, per Jellyseerr event type. The one you'd graph: requests and availability per day. |
| `bot_webhooks_total{status=ok\|unauthorized\|dropped}` | Incoming webhook requests. `unauthorized` spikes mean someone probes the endpoint or the secret is wrong; `dropped` counts unhandled types and bad JSON. |
| `bot_errors_total` | Every `log.error`/`log.exception` in the bot, including errors inside matrix-nio. |
| `bot_last_sync_timestamp` | Unix time of the last successful `/sync` with the homeserver. If this goes stale, the bot lost its Matrix connection. |

## Example alert rules

```yaml
groups:
  - name: jellyseerr-matrix-bot
    rules:
      - alert: JellyseerrBotDown
        expr: up{job="jellyseerr-matrix-bot"} == 0
        for: 5m
        annotations:
          summary: "jellyseerr-matrix-bot is not being scraped"

      - alert: JellyseerrBotSyncStale
        expr: time() - bot_last_sync_timestamp > 300
        for: 5m
        annotations:
          summary: "Bot has not synced with the homeserver for 5+ minutes"

      - alert: JellyseerrBotErrors
        expr: increase(bot_errors_total[15m]) > 0
        annotations:
          summary: "Bot logged errors in the last 15 minutes, check the container logs"
```

All label values are pre-created at startup, so `increase()` and `rate()` work
from the first scrape instead of missing the first event of each series.
