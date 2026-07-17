<p align="center">
  <img src="assets/banner.svg" alt="jellyseerr-matrix-bot" width="640">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/inventory69/jellyseerr-matrix-bot" alt="License"></a>
  <a href="https://github.com/inventory69/jellyseerr-matrix-bot/releases"><img src="https://img.shields.io/github/v/release/inventory69/jellyseerr-matrix-bot" alt="Release"></a>
  <a href="https://github.com/inventory69/jellyseerr-matrix-bot/pkgs/container/jellyseerr-matrix-bot"><img src="https://img.shields.io/badge/ghcr.io-image-blue" alt="ghcr"></a>
  <a href="https://github.com/inventory69/jellyseerr-matrix-bot/actions"><img src="https://img.shields.io/github/actions/workflow/status/inventory69/jellyseerr-matrix-bot/ci.yml" alt="CI"></a>
</p>

Jellyseerr notifications in an end-to-end encrypted Matrix room. Poster, request
status and a real mention for the person who asked, all in one message. One
Python file, one container.

I built this because Jellyseerr ships Discord, Telegram, Slack and Pushover
agents, but no Matrix. Works with Seerr, Jellyseerr and Overseerr, they all send
the same webhook payload.

<!-- TODO: hero screenshot (staged test room, fake cast), see assets/ -->

What a notification looks like:

> 🎬 **Now available**
> [**The Lord of the Rings: The Fellowship of the Ring (2001)**](#) (Movie)
> Status: Available
> Requested by @frodo

with the movie poster above the text, the title linking to your Jellyseerr, and
`@frodo` being an actual Matrix mention that pings, even if the room is muted.

## Features

- Works in E2EE rooms, and pushes still arrive in rooms muted to "mentions only"
- Poster and text card in a single message (m.image with caption, MSC2530)
- `USER_MAP` turns Jellyseerr usernames into Matrix mention pills
- Team pings on new requests and new issues, so nothing sits unapproved
- Titles and issues link back to your Jellyseerr, including a reply link
- Prometheus metrics on `/metrics`, English and German output (`BOT_LANG`)

## Quick start

```yaml
services:
  jellyseerr-matrix-bot:
    image: ghcr.io/inventory69/jellyseerr-matrix-bot:latest
    container_name: jellyseerr-matrix-bot
    restart: unless-stopped
    env_file: config.env
    volumes:
      - store:/data/store

volumes:
  store:
```

1. Grab the compose file and the config template:

   ```sh
   curl -O https://raw.githubusercontent.com/inventory69/jellyseerr-matrix-bot/main/compose.yml
   curl -o config.env https://raw.githubusercontent.com/inventory69/jellyseerr-matrix-bot/main/config.env.example
   ```

2. Fill in the six required variables in `config.env` (homeserver, bot user,
   token, device ID, room, webhook secret). The rest is optional and marked as
   such. [docs/setup.md](docs/setup.md) has the token one-liner and the webhook
   template for Jellyseerr.

3. `docker compose up -d`, then hit "Test" in Jellyseerr's webhook settings.

## Why not matrix-hookshot?

hookshot receives generic webhooks too, but you'd write the JS transformation
snippet yourself and still have no posters, no mention pills and no
push-through-mute. This bot does one thing: Jellyseerr to Matrix, done properly.

## Docs

- [Setup](docs/setup.md): token, room, webhook template, USER_MAP
- [Configuration](docs/configuration.md): every environment variable
- [Troubleshooting](docs/troubleshooting.md): decryption, pushes, libolm status
- [Monitoring](docs/monitoring.md): metrics and example alert rules

Deutsche Version: [README.de.md](README.de.md)

## Contributing

Issues and PRs welcome. Run `python bot.py --selfcheck` before pushing, keep
commits in conventional style (`feat: ...`, `fix: ...`), English please.

MIT licensed.
