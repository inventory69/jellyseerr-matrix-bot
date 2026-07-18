<p align="center">
  <img src="assets/banner.svg" alt="jellyseerr-matrix-bot" width="640">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/inventory69/jellyseerr-matrix-bot" alt="License"></a>
  <a href="https://github.com/inventory69/jellyseerr-matrix-bot/releases"><img src="https://img.shields.io/github/v/release/inventory69/jellyseerr-matrix-bot" alt="Release"></a>
  <a href="https://github.com/inventory69/jellyseerr-matrix-bot/pkgs/container/jellyseerr-matrix-bot"><img src="https://img.shields.io/badge/ghcr.io-image-blue" alt="ghcr"></a>
  <a href="https://github.com/inventory69/jellyseerr-matrix-bot/actions"><img src="https://img.shields.io/github/actions/workflow/status/inventory69/jellyseerr-matrix-bot/ci.yml" alt="CI"></a>
</p>

Jellyseerr-Benachrichtigungen in einem Ende-zu-Ende-verschlüsselten Matrix-Raum.
Poster, Request-Status und eine echte Mention für die Person, die angefragt hat,
alles in einer Nachricht. Eine Python-Datei, ein Container.

Ich habe das gebaut, weil Jellyseerr zwar Discord-, Telegram-, Slack- und
Pushover-Agents mitbringt, aber kein Matrix. Funktioniert mit Seerr, Jellyseerr
und Overseerr, das Webhook-Payload ist identisch.

<p align="center">
  <img src="assets/screenshot-de.png" alt="Benachrichtigung in Element: Poster, fette Headline, verlinkter Titel, Status-Zeile, Beschreibung, Mention-Pille" width="400">
</p>

Poster und Text-Karte sind eine Nachricht, der Titel verlinkt in dein
Jellyseerr, und `frodo` ist eine echte Matrix-Mention-Pille, die pusht, auch
wenn der Raum stumm ist.

## Schnellstart

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

1. Compose-Datei und Config-Vorlage holen:

   ```sh
   curl -O https://raw.githubusercontent.com/inventory69/jellyseerr-matrix-bot/main/compose.yml
   curl -o config.env https://raw.githubusercontent.com/inventory69/jellyseerr-matrix-bot/main/config.env.example
   ```

2. Die sechs Pflicht-Variablen in `config.env` ausfüllen (Homeserver, Bot-User,
   Token, Device-ID, Raum, Webhook-Secret). In [docs/setup.md](docs/setup.md)
   stehen der Token-Einzeiler und das Webhook-Template für Jellyseerr.

3. `docker compose up -d`, dann in Jellyseerrs Webhook-Einstellungen auf "Test"
   klicken. Für deutsche Nachrichten `BOT_LANG=de` setzen.

## Alles Weitere

Features, Vergleich mit matrix-hookshot, Doku ([Setup](docs/setup.md),
[Konfiguration](docs/configuration.md),
[Troubleshooting](docs/troubleshooting.md), [Monitoring](docs/monitoring.md))
und Contributing-Hinweise stehen in der englischen [README.md](README.md), die
immer die maßgebliche Version ist.

MIT-Lizenz.
