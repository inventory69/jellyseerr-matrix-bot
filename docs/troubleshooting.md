# Troubleshooting

## "Unable to decrypt" in the room

Almost always a store problem. The bot's encryption state lives in `/data/store`
(the `store` volume in the compose file). **Never delete that volume** while
keeping the same token: the bot would start with fresh crypto state and the room
sees undecryptable history or session errors.

If you did lose the store, do a clean cut: log the bot in again (new token + new
device ID, see [setup.md](setup.md)), update both values in `config.env`, keep the
new empty store. New messages decrypt fine, old ones stay lost, that's how E2EE
works.

There is one built-in mitigation you might notice in the logs: after a Megolm
session rotation the bot waits 6 seconds between distributing the new key and
sending the message. Without that gap, clients receive key and message in the
same sync and briefly show "Unable to decrypt" until reload.

## Mentions don't push (room is muted)

Muting a room to "mentions only" and still getting pinged by the bot is a
feature here, and it needs a trick: in an encrypted room the server can't read
`m.mentions` inside the ciphertext, so it can never match its mention rule. This
bot therefore attaches `m.mentions` (the Matrix IDs only, nothing else) to the
cleartext of the encrypted event. Message content stays encrypted.

If mentions don't push at all, check in this order:

1. Is the user in `USER_MAP` (for affected-user pings) or `ADMIN_IDS` (for team
   pings)? The log warns about unmapped Jellyseerr usernames.
2. Does the event type ping that user at all? Team pings fire on new requests
   and new issues; user pings fire on approved/declined/available and issue
   updates. Nobody is pinged for their own comment.
3. Client-side notification settings for keywords/mentions.

## Webhook returns 401

The `Authorization` header in Jellyseerr must be byte-for-byte identical to
`WEBHOOK_SECRET`. No `Bearer ` prefix, no quotes.

## Webhook arrives, nothing in the room

Check `docker logs jellyseerr-matrix-bot`. A line like `Dropping type
'MEDIA_FAILED'` means the event type is intentionally unhandled. `No USER_MAP
entry ...` is harmless (message still sent, just no ping).

## Reverse proxy notes

The container listens on port 8080 and speaks plain HTTP. Put your reverse proxy
in front of `/webhook` and let it terminate TLS. Remember: the webhook secret is
the only authentication, so treat the URL like a password-protected endpoint,
and don't expose `/metrics` publicly.

## Known limitation: libolm

E2EE comes from `matrix-nio[e2e]`, which still builds on libolm, and libolm has
been officially deprecated since mid-2024 (its successor is vodozemac). There is
no released, non-deprecated Python alternative today: matrix-nio's vodozemac
port exists as an unmerged PR
([matrix-nio#555](https://github.com/matrix-nio/matrix-nio/pull/555)), and I'd
rather ship the boring released library than pin someone's unmerged fork. When
nio releases vodozemac support, this bot will switch in a minor release. Nothing
for you to do until then.
