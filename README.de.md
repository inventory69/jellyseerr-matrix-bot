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

So sieht eine Benachrichtigung aus:

> 🎬 **Jetzt verfügbar**
> [**Der Herr der Ringe: Die Gefährten (2001)**](#) (Film)
> Status: Verfügbar
> Angefragt von @frodo

mit dem Filmposter über dem Text, dem Titel als Link in dein Jellyseerr, und
`@frodo` ist eine echte Matrix-Mention, die pusht, auch wenn der Raum stumm ist.

## Features

- Funktioniert in E2EE-Räumen, Pushes kommen auch bei "nur Erwähnungen" an
- Poster und Text-Karte in einer Nachricht (m.image mit Caption, MSC2530)
- `USER_MAP` macht aus Jellyseerr-Usernamen Matrix-Mention-Pillen
- Team-Pings bei neuen Anfragen und Problemen, nichts bleibt unbemerkt liegen
- Titel und Issues verlinken zurück in dein Jellyseerr, inklusive Antworten-Link
- Prometheus-Metriken auf `/metrics`, Ausgabe auf Englisch oder Deutsch (`BOT_LANG`)

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
   Token, Device-ID, Raum, Webhook-Secret). Der Rest ist optional und als
   solcher markiert. In [docs/setup.md](docs/setup.md) stehen der
   Token-Einzeiler und das Webhook-Template für Jellyseerr.

3. `docker compose up -d`, dann in Jellyseerrs Webhook-Einstellungen auf "Test"
   klicken. Für deutsche Nachrichten `BOT_LANG=de` setzen.

## Warum nicht matrix-hookshot?

hookshot nimmt auch generische Webhooks an, aber das JS-Transformations-Snippet
schreibst du selbst, und Poster, Mention-Pillen und Push-trotz-Mute gibt es
trotzdem nicht. Dieser Bot macht eine Sache: Jellyseerr nach Matrix, richtig.

## Doku

Die Doku unter [docs/](docs/) ist englisch: [Setup](docs/setup.md),
[Konfiguration](docs/configuration.md),
[Troubleshooting](docs/troubleshooting.md), [Monitoring](docs/monitoring.md).

English version: [README.md](README.md)

## Mitmachen

Issues und PRs gern, auf Englisch. Vor dem Pushen `python bot.py --selfcheck`
laufen lassen, Commits im Conventional-Stil (`feat: ...`, `fix: ...`).

MIT-Lizenz.
