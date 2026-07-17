# Setup

You need four things: a Matrix account for the bot, an access token for it, a room,
and the webhook in Jellyseerr. All of it is copy-paste, no Python required.

## 1. Create a Matrix account for the bot

Any homeserver works, including your own. Create a regular user, for example
`@jellyseerr-bot:example.org`. No admin rights needed.

## 2. Get an access token and device ID

The bot logs in with a token, not a password. Get one with a single curl call:

```sh
curl -s -X POST https://matrix.example.org/_matrix/client/v3/login -d '{
  "type": "m.login.password",
  "identifier": {"type": "m.id.user", "user": "jellyseerr-bot"},
  "password": "YOUR_PASSWORD",
  "initial_device_display_name": "jellyseerr-matrix-bot"
}'
```

The response contains `access_token` and `device_id`. Put them into `config.env` as
`MATRIX_TOKEN` and `MATRIX_DEVICE_ID`. They belong together: if you log in again
later, you get a new pair, and the old encryption store won't match. Set both from
the same login response and keep the `store` volume, then encryption keeps working
across restarts.

## 3. Create the room

Create a room (encryption on is fine, that's the point of this bot) and invite the
bot user. The bot accepts the invite on its own once it runs.

Copy the internal room ID from your client's room settings into `MATRIX_ROOM_ID`.
Careful with newer rooms (room version 12+): their IDs look like
`!p0-6r5iIAUpYVarcFhd...` with **no `:domain` suffix**. Paste the ID exactly as
your client shows it, don't append your domain.

## 4. Configure the webhook in Jellyseerr

Jellyseerr → Settings → Notifications → Webhook:

- **Webhook URL**: wherever the bot's port 8080 is reachable from Jellyseerr,
  plus `/webhook`. For example `https://jellyhook.example.org/webhook` behind a
  reverse proxy, or `http://jellyseerr-matrix-bot:8080/webhook` if both share a
  Docker network.
- **Authorization Header**: the exact value of `WEBHOOK_SECRET` from your
  `config.env`. This is the only authentication the endpoint has.
- **JSON Payload**: the template below. It is Jellyseerr's default template and
  the one this bot is tested against. The important parts are the `image` key
  (poster) and `media_status` as a string.
- **Notification Types**: enable what you want to see. The bot handles requests
  (pending, approved, auto-approved, declined, available), issues (created,
  comment, resolved, reopened) and the test notification. Anything else
  (like failure events) is dropped silently, so over-enabling doesn't hurt.

```json
{
  "notification_type": "{{notification_type}}",
  "event": "{{event}}",
  "subject": "{{subject}}",
  "message": "{{message}}",
  "image": "{{image}}",
  "{{media}}": {
    "media_type": "{{media_type}}",
    "tmdbId": "{{media_tmdbid}}",
    "tvdbId": "{{media_tvdbid}}",
    "status": "{{media_status}}",
    "status4k": "{{media_status4k}}"
  },
  "{{request}}": {
    "request_id": "{{request_id}}",
    "requestedBy_email": "{{requestedBy_email}}",
    "requestedBy_username": "{{requestedBy_username}}",
    "requestedBy_avatar": "{{requestedBy_avatar}}",
    "requestedBy_settings_discordId": "{{requestedBy_settings_discordId}}",
    "requestedBy_settings_telegramChatId": "{{requestedBy_settings_telegramChatId}}"
  },
  "{{issue}}": {
    "issue_id": "{{issue_id}}",
    "issue_type": "{{issue_type}}",
    "issue_status": "{{issue_status}}",
    "reportedBy_email": "{{reportedBy_email}}",
    "reportedBy_username": "{{reportedBy_username}}",
    "reportedBy_avatar": "{{reportedBy_avatar}}",
    "reportedBy_settings_discordId": "{{reportedBy_settings_discordId}}",
    "reportedBy_settings_telegramChatId": "{{reportedBy_settings_telegramChatId}}"
  },
  "{{comment}}": {
    "comment_message": "{{comment_message}}",
    "commentedBy_email": "{{commentedBy_email}}",
    "commentedBy_avatar": "{{commentedBy_avatar}}",
    "commentedBy_username": "{{commentedBy_username}}",
    "commentedBy_settings_discordId": "{{commentedBy_settings_discordId}}",
    "commentedBy_settings_telegramChatId": "{{commentedBy_settings_telegramChatId}}"
  },
  "{{extra}}": []
}
```

Click "Save Changes", then "Test" in Jellyseerr. You should see a
🔔 test notification in the room.

## 5. Map users for pings (USER_MAP)

`USER_MAP` in `config.env` maps Jellyseerr usernames to Matrix IDs:

```
USER_MAP={"frodo":"@frodo:example.org","dude":"@dude:example.org"}
```

When frodo's request becomes available, `@frodo:example.org` gets a real Matrix
mention (a pill in the message, plus a push). Unmapped users just appear as plain
text, and the bot logs a warning so you notice new Jellyseerr users.

`ADMIN_IDS` is separate on purpose: those Matrix IDs get pinged on every new
request and new issue, so nothing waits for approval unseen. Being in `USER_MAP`
does not make someone an admin, and vice versa.
