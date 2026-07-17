# Configuration

Everything is configured through environment variables, usually via `config.env`
(see [config.env.example](../config.env.example)).

## Required

| Variable | Meaning |
|---|---|
| `MATRIX_URL` | Homeserver URL (client API), e.g. `https://matrix.example.org`. |
| `MATRIX_USER_ID` | The bot's full Matrix ID, e.g. `@jellyseerr-bot:example.org`. |
| `MATRIX_TOKEN` | Access token from the login call in [setup.md](setup.md). |
| `MATRIX_DEVICE_ID` | Device ID from the **same** login call as the token. |
| `MATRIX_ROOM_ID` | Internal ID of the target room. Room v12+ IDs have no `:domain` suffix, paste them as-is. |
| `WEBHOOK_SECRET` | Shared secret. Must equal the Authorization header configured in Jellyseerr. |

## Optional

| Variable | Meaning |
|---|---|
| `USER_MAP` | JSON object mapping Jellyseerr usernames to Matrix IDs for mentions, e.g. `{"frodo":"@frodo:example.org"}`. Default: empty, no user pings. |
| `ADMIN_IDS` | Comma-separated Matrix IDs of the operator team. Pinged on `MEDIA_PENDING`, `ISSUE_CREATED` and `ISSUE_REOPENED`. Default: empty, no team pings. |
| `JELLYSEERR_URL` | Base URL of your Jellyseerr. Turns titles into links (`/movie/{id}`, `/tv/{id}`) and adds a reply link to issues. Default: empty, plain text. |
| `BOT_LANG` | Message language, `en` or `de`. Default `en`; unknown values fall back to `en` with a log warning. |

A broken `USER_MAP` (invalid JSON) does not stop the bot. It logs an error and
runs without mentions, because messages without pings beat no messages.

## Ports and paths

The bot listens on container port `8080`: `POST /webhook` for Jellyseerr,
`GET /metrics` for Prometheus. The E2EE store lives in `/data/store` and must
persist (the compose file mounts a named volume there).
