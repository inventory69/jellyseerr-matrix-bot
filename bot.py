#!/usr/bin/env python3
"""Jellyseerr webhook -> E2EE Matrix room. One process: nio sync_forever + aiohttp."""
import asyncio
import hmac
import html
import io
import json
import logging
import os
import sys
import time
from uuid import uuid4

import aiohttp
from aiohttp import web
from nio import (
    Api,
    AsyncClient,
    InviteMemberEvent,
    MatrixRoom,
    RoomSendResponse,
    SyncResponse,
    UploadResponse,
)
from nio.exceptions import LocalProtocolError
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Gauge, generate_latest

log = logging.getLogger("jellyseerr-bot")

ERRORS = Counter("bot_errors_total", "Errors (log.error/log.exception) anywhere in the bot")
WEBHOOKS = Counter("bot_webhooks_total", "Incoming webhook requests", ["status"])
NOTIFICATIONS = Counter("bot_notifications_total", "Notifications sent to Matrix", ["type"])
LAST_SYNC = Gauge("bot_last_sync_timestamp", "Unix time of the last /sync from the homeserver")


class ErrorCounter(logging.Handler):
    """Counts every log.error/log.exception — attached to the root logger so nio
    errors count too, without touching individual code paths."""

    def emit(self, record):
        ERRORS.inc()


# Emoji per Jellyseerr notification_type. Types not listed here (e.g. *_FAILED)
# are dropped. Headlines live in STRINGS, keyed by the same names.
EMOJI = {
    "TEST_NOTIFICATION": "🔔",
    "MEDIA_PENDING": "📥",
    "MEDIA_APPROVED": "✅",
    "MEDIA_AUTO_APPROVED": "✅",
    "MEDIA_DECLINED": "❌",
    "MEDIA_AVAILABLE": "🎬",
    "ISSUE_CREATED": "⚠️",
    "ISSUE_COMMENT": "💬",
    "ISSUE_RESOLVED": "✔️",
    "ISSUE_REOPENED": "🔁",
}

# ponytail: two languages = two dicts; switch to a locale framework at 3+.
STRINGS = {
    "en": {
        "events": {
            "TEST_NOTIFICATION": "Test notification",
            "MEDIA_PENDING": "New request – waiting for approval",
            "MEDIA_APPROVED": "Request approved",
            "MEDIA_AUTO_APPROVED": "Request auto-approved",
            "MEDIA_DECLINED": "Request declined",
            "MEDIA_AVAILABLE": "Now available",
            "ISSUE_CREATED": "New issue reported",
            "ISSUE_COMMENT": "New comment on issue",
            "ISSUE_RESOLVED": "Issue resolved",
            "ISSUE_REOPENED": "Issue reopened",
        },
        "media_types": {"movie": "Movie", "tv": "Series"},
        "status": {
            "PENDING": "Pending",
            "PROCESSING": "Processing",
            "PARTIALLY_AVAILABLE": "Partially available",
            "AVAILABLE": "Available",
        },
        "issue_types": {"VIDEO": "Video", "AUDIO": "Audio", "SUBTITLES": "Subtitles",
                        "OTHER": "Other"},
        "issue_status": {"OPEN": "Open", "RESOLVED": "Resolved"},
        "untitled": "(untitled)",
        "status_label": "Status",
        "seasons": "Seasons",
        "season": "Season",
        "episode": "Episode",
        "comment_by": "Comment by",
        "requested_by": "Requested by",
        "reported_by": "Reported by",
        "reply": "Reply",
        "reopen": "Reopen",
    },
    "de": {
        "events": {
            "TEST_NOTIFICATION": "Test-Benachrichtigung",
            "MEDIA_PENDING": "Neue Anfrage – wartet auf Freigabe",
            "MEDIA_APPROVED": "Anfrage genehmigt",
            "MEDIA_AUTO_APPROVED": "Anfrage automatisch genehmigt",
            "MEDIA_DECLINED": "Anfrage abgelehnt",
            "MEDIA_AVAILABLE": "Jetzt verfügbar",
            "ISSUE_CREATED": "Neues Problem gemeldet",
            "ISSUE_COMMENT": "Neuer Kommentar zum Problem",
            "ISSUE_RESOLVED": "Problem gelöst",
            "ISSUE_REOPENED": "Problem wieder geöffnet",
        },
        "media_types": {"movie": "Film", "tv": "Serie"},
        "status": {
            "PENDING": "Ausstehend",
            "PROCESSING": "In Bearbeitung",
            "PARTIALLY_AVAILABLE": "Teilweise verfügbar",
            "AVAILABLE": "Verfügbar",
        },
        "issue_types": {"VIDEO": "Video", "AUDIO": "Ton", "SUBTITLES": "Untertitel",
                        "OTHER": "Sonstiges"},
        "issue_status": {"OPEN": "Offen", "RESOLVED": "Gelöst"},
        "untitled": "(ohne Titel)",
        "status_label": "Status",
        "seasons": "Staffeln",
        "season": "Staffel",
        "episode": "Episode",
        "comment_by": "Kommentar von",
        "requested_by": "Angefragt von",
        "reported_by": "Gemeldet von",
        "reply": "Antworten",
        "reopen": "Wieder öffnen",
    },
}

S = STRINGS["en"]


def set_lang(code: str):
    global S
    if code not in STRINGS:
        log.warning("Unknown BOT_LANG %r, falling back to en", code)
        code = "en"
    S = STRINGS[code]


# Events where the affected user themselves gets pinged. MEDIA_AUTO_APPROVED is
# deliberately absent: MEDIA_AVAILABLE follows shortly after and pings anyway.
PING_EVENTS = {
    "MEDIA_APPROVED",
    "MEDIA_DECLINED",
    "MEDIA_AVAILABLE",
    "ISSUE_COMMENT",
    "ISSUE_RESOLVED",
    "ISSUE_REOPENED",
}

# Events where the operator team (ADMIN_IDS) is pinged as well: nobody should
# miss a new request / new issue. ISSUE_REOPENED carries no actor in the
# payload -> ping both sides.
ADMIN_PING_EVENTS = {"MEDIA_PENDING", "ISSUE_CREATED", "ISSUE_REOPENED"}

# Issue follow-ups: no poster (the card for ISSUE_CREATED already showed it) and
# candidates for the close/reopen-with-comment merge (Jellyseerr fires two
# webhooks for that single action).
ISSUE_FOLLOWUPS = {"ISSUE_COMMENT", "ISSUE_RESOLVED", "ISSUE_REOPENED"}
MERGE_WINDOW = 5  # seconds to wait for the second webhook of a close-with-comment

POSTER_MAX_BYTES = 10 * 1024 * 1024  # sanity limit; Jellyseerr posters are ~200 KB


def render(
    payload: dict, user_map: dict, admin_ids: list[str] = (), jellyseerr_url: str = ""
) -> tuple[str, str, list[str]] | None:
    """-> (body, formatted_body, mention_ids), or None if this type is not sent."""
    ntype = payload.get("notification_type") or ""
    if ntype not in EMOJI:
        return None
    emoji, headline = EMOJI[ntype], S["events"][ntype]

    media = payload.get("media") or {}
    request = payload.get("request") or {}
    issue = payload.get("issue") or {}
    comment = payload.get("comment") or {}

    subject = payload.get("subject") or S["untitled"]
    message = payload.get("message") or ""
    kind = S["media_types"].get(media.get("media_type") or "", media.get("media_type") or "")

    # The affected user: the reporter for issue events, the requester otherwise.
    # notifyuser_username is NOT part of the standard payload template, but is
    # preferred if someone adds it to theirs.
    target = payload.get("notifyuser_username") or (
        issue.get("reportedBy_username") if issue else request.get("requestedBy_username")
    )

    lines, html_lines, mentions = [], [], []
    lines.append(f"{emoji} {headline}")
    html_lines.append(f"<b>{html.escape(emoji + ' ' + headline)}</b>")

    title = f"{subject} ({kind})" if kind else subject
    lines.append(title)
    title_html = f"<b>{html.escape(subject)}</b>" + (f" ({html.escape(kind)})" if kind else "")
    # Link the title to the Jellyseerr portal (/movie/{id} or /tv/{id}) when
    # base URL + tmdbId + a known media_type are present. Bold plaintext otherwise.
    mtype = media.get("media_type")
    tmdb = media.get("tmdbId")
    if jellyseerr_url and tmdb and mtype in ("movie", "tv"):
        href = f"{jellyseerr_url.rstrip('/')}/{mtype}/{tmdb}"
        title_html = f'<a href="{html.escape(href)}">{title_html}</a>'
    html_lines.append(title_html)

    def extra(name):
        return next(
            (e.get("value") for e in (payload.get("extra") or []) if e.get("name") == name), None
        )

    # Status + requested seasons as one line (only the parts that exist).
    parts = []
    status = S["status"].get(media.get("status") or "")
    if status:
        parts.append(f"{S['status_label']}: {status}")
    seasons = extra("Requested Seasons")
    if seasons:
        parts.append(f"{S['seasons']}: {seasons}")
    if parts:
        meta = " · ".join(parts)
        lines.append(meta)
        html_lines.append(f'<font color="#9e9e9e">{html.escape(meta)}</font>')

    if issue.get("issue_type"):
        t = issue["issue_type"]
        detail = S["issue_types"].get(str(t).upper(), t)
        s = issue.get("issue_status")
        if s:
            detail += f" · {S['issue_status'].get(str(s).upper(), s)}"
        season, episode = extra("Affected Season"), extra("Affected Episode")
        if season:
            detail += f" · {S['season']} {season}" + (f", {S['episode']} {episode}" if episode else "")
        lines.append(detail)
        html_lines.append(f'<font color="#9e9e9e">{html.escape(detail)}</font>')

    body_text = comment.get("comment_message") or message
    if body_text:
        lines.append(body_text)
        # Blank line + italics set the free text apart from the header block.
        html_lines.append("")
        html_lines.append(f"<em>{html.escape(body_text)}</em>")

    def name_html(username: str) -> str:
        """Matrix link when mapped - plain text otherwise (plus a log warning)."""
        mxid = user_map.get(username)
        if not mxid:
            log.warning("No USER_MAP entry for Jellyseerr user %r", username)
            return html.escape(username)
        return f'<a href="https://matrix.to/#/{html.escape(mxid)}">{html.escape(username)}</a>'

    # Footer group (people + links), separated from the card by a blank line.
    footer = []

    author = comment.get("commentedBy_username")
    if author:
        lines.append(f"{S['comment_by']}: {author}")
        footer.append(f"{S['comment_by']} {name_html(author)}")

    if target:
        label = S["reported_by"] if issue else S["requested_by"]
        lines.append(f"{label}: {target}")
        footer.append(f"{label} {name_html(target)}")
        mxid = user_map.get(target)
        if mxid and ntype in PING_EVENTS:
            mentions.append(mxid)

    # Direct link to the issue page (team and reporter alike). On a resolved
    # issue "reply" is the wrong invitation - the page's actual affordance is
    # the reopen button, so label the same link accordingly.
    if jellyseerr_url and issue.get("issue_id"):
        href = f"{jellyseerr_url.rstrip('/')}/issues/{issue['issue_id']}"
        icon, label = ("🔁", S["reopen"]) if ntype == "ISSUE_RESOLVED" else ("💬", S["reply"])
        lines.append(f"{label}: {href}")
        footer.append(f'{icon} <a href="{html.escape(href)}">{label}</a>')

    # Ping the other side: when the reporter comments on (or closes) their own
    # issue, the team should see it.
    admin_ping = ntype in ADMIN_PING_EVENTS or (author and author == target)
    if admin_ping and admin_ids:
        mentions.extend(admin_ids)
        # m.mentions alone only triggers highlight/push and is invisible - the
        # matrix.to links make the pings visible as pills in the text.
        lines.append("cc: " + " ".join(admin_ids))
        footer.append(
            "cc: "
            + " ".join(
                f'<a href="https://matrix.to/#/{html.escape(i)}">{html.escape(i)}</a>'
                for i in admin_ids
            )
        )

    if footer:
        html_lines.append("")
        html_lines.extend(footer)

    # Keep order, drop duplicate pings (a user can also be on the team), and
    # nobody pings themselves (the commenter gets no ping for their own comment).
    author_mxid = user_map.get(author) if author else None
    mentions = [m for m in dict.fromkeys(mentions) if m != author_mxid]
    return "\n".join(lines), "<br>".join(html_lines), mentions


def encrypt_with_cleartext_mentions(encrypt_fn, room_id, inner, mentions):
    """Like nio does for m.relates_to: put m.mentions in the CLEARTEXT of the
    m.room.encrypted envelope too, so Synapse can evaluate .m.rule.is_user_mention
    and push despite a room mute."""
    _type, enc = encrypt_fn(room_id, "m.room.message", inner)
    if mentions:
        enc["m.mentions"] = {"user_ids": mentions}  # ponytail: only MXIDs cleartext, body stays E2EE
    return enc


def image_content(uri, keys, size, mimetype, body, formatted, mentions):
    """m.image with caption (MSC2530): body/formatted_body carry the text card,
    filename holds the real file name -> clients render body as the caption."""
    return {
        "msgtype": "m.image",
        "body": body,
        "filename": "poster.jpg",
        "format": "org.matrix.custom.html",
        "formatted_body": formatted,
        "info": {"mimetype": mimetype, "size": size},
        "file": {
            "url": uri,
            "key": keys["key"],
            "iv": keys["iv"],
            "hashes": keys["hashes"],
            "v": keys["v"],
        },
        "m.mentions": {"user_ids": mentions} if mentions else {},
    }


def text_content(body, formatted, mentions):
    return {
        "msgtype": "m.text",
        "body": body,
        "format": "org.matrix.custom.html",
        "formatted_body": formatted,
        "m.mentions": {"user_ids": mentions} if mentions else {},
    }


async def upload_poster(client: AsyncClient, url: str):
    """Fetch the poster + upload it E2EE-encrypted to the media repo.
    -> (mxc, keys, size, mimetype). Raises on any failure; the caller catches
    and falls back to text."""
    async with aiohttp.ClientSession() as s:
        async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            r.raise_for_status()
            mimetype = (r.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip()
            data = await r.read()
    if not data or len(data) > POSTER_MAX_BYTES:
        raise ValueError(f"Poster {len(data)} B outside the limit")
    resp, keys = await client.upload(
        io.BytesIO(data), content_type=mimetype, filename="poster.jpg",
        filesize=len(data), encrypt=True,
    )
    if not isinstance(resp, UploadResponse):
        raise RuntimeError(f"Upload failed: {resp}")
    return resp.content_uri, keys, len(data), mimetype


async def send(
    client: AsyncClient, room_id: str, body: str, formatted: str,
    mentions: list[str], poster_url: str | None = None,
):
    if client.should_query_keys:
        await client.keys_query()
    # Decouple key distribution from sending the event: ship the Megolm key via
    # to-device first, wait briefly, then send - otherwise the recipient sees
    # key and event in the same /sync and shows "Unable to decrypt" until reload.
    # Raises LocalProtocolError when the session is still valid -> no sleep then.
    try:
        await client.share_group_session(room_id, ignore_unverified_devices=True)
        # ponytail: 6s heuristic; only runs after a session rotation.
        await asyncio.sleep(6)
    except LocalProtocolError:
        pass

    # client.encrypt requires fully synced members (room_send does that on its
    # internal retry path, which we bypass here) -> MembersSyncError otherwise.
    room = client.rooms.get(room_id)
    if room and not room.members_synced:
        await client.joined_members(room_id)

    # Poster as m.image with caption; any failure falls back to plain text -
    # the notification must never fail because of the poster.
    inner = None
    if poster_url:
        try:
            uri, keys, size, mimetype = await upload_poster(client, poster_url)
            inner = image_content(uri, keys, size, mimetype, body, formatted, mentions)
        except Exception:
            log.exception("Poster upload failed, sending text only")
    if inner is None:
        inner = text_content(body, formatted, mentions)  # m.mentions ALSO stays inside (client highlight)
    # Encrypt ourselves and attach m.mentions cleartext to the envelope: nio's
    # room_send would encrypt the ENTIRE content, making m.mentions invisible to
    # Synapse so .m.rule.is_user_mention cannot override a room mute.
    enc = encrypt_with_cleartext_mentions(client.encrypt, room_id, inner, mentions)
    method, path, data = Api.room_send(
        client.access_token, room_id, "m.room.encrypted", enc, uuid4()
    )
    resp = await client._send(RoomSendResponse, method, path, data, (room_id,))
    if not isinstance(resp, RoomSendResponse):
        log.error("Matrix send failed: %s", resp)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger().addHandler(ErrorCounter(level=logging.ERROR))
    set_lang(os.environ.get("BOT_LANG") or "en")
    # Create label values up front, otherwise the series are missing until the
    # first event and increase()/rate() see nothing.
    for status in ("ok", "unauthorized", "dropped"):
        WEBHOOKS.labels(status)
    for ntype in EMOJI:
        NOTIFICATIONS.labels(ntype)

    homeserver = os.environ["MATRIX_URL"]
    user_id = os.environ["MATRIX_USER_ID"]
    device_id = os.environ["MATRIX_DEVICE_ID"]
    room_id = os.environ["MATRIX_ROOM_ID"]
    secret = os.environ["WEBHOOK_SECRET"]
    try:
        user_map = json.loads(os.environ.get("USER_MAP") or "{}")
    except json.JSONDecodeError as e:
        # A hand-typed broken USER_MAP must not take the bot down: messages
        # without pings beat no messages. The log says why they are missing.
        log.error("USER_MAP is not valid JSON (%s) — continuing WITHOUT mentions!", e)
        user_map = {}
    admin_ids = [x.strip() for x in (os.environ.get("ADMIN_IDS") or "").split(",") if x.strip()]
    jellyseerr_url = os.environ.get("JELLYSEERR_URL") or ""
    store = "/data/store"

    os.makedirs(store, exist_ok=True)
    client = AsyncClient(homeserver, user_id, device_id=device_id, store_path=store)
    client.access_token = os.environ["MATRIX_TOKEN"]
    client.user_id = user_id
    client.load_store()
    log.info(
        "Starting as %s / device %s / %d mapped users / team ping to %s",
        user_id, client.device_id, len(user_map), admin_ids or "nobody",
    )

    async def on_invite(room: MatrixRoom, event: InviteMemberEvent):
        if event.state_key == client.user_id and room.room_id == room_id:
            log.info("Invited to %s -> joining", room.room_id)
            await client.join(room.room_id)

    client.add_event_callback(on_invite, InviteMemberEvent)

    async def on_sync(_resp: SyncResponse):
        LAST_SYNC.set(time.time())

    client.add_response_callback(on_sync, SyncResponse)

    if client.should_upload_keys:
        await client.keys_upload()
    await client.sync(timeout=30000, full_state=True)
    # Join at startup (no-op when already joined); later invites are handled by on_invite.
    await client.join(room_id)

    lock = asyncio.Lock()
    pending: dict = {}  # issue_id -> (payload, flush task) buffered for the merge window

    async def deliver(payload: dict):
        out = render(payload, user_map, admin_ids, jellyseerr_url)
        ntype = payload["notification_type"]
        # Poster only on first sight of a media item; issue follow-ups stay compact.
        poster_url = (payload.get("image") or None) if ntype not in ISSUE_FOLLOWUPS else None
        log.info("Sending %s (image=%s)", ntype, poster_url)
        async with lock:  # ponytail: one room, one sender - a global lock is enough
            await send(client, room_id, *out, poster_url=poster_url)
        NOTIFICATIONS.labels(ntype).inc()

    async def webhook(req: web.Request) -> web.Response:
        if not hmac.compare_digest(req.headers.get("Authorization", ""), secret):
            log.warning("Webhook with wrong/missing secret from %s", req.remote)
            WEBHOOKS.labels("unauthorized").inc()
            return web.Response(status=401, text="unauthorized")
        try:
            payload = await req.json()
        except json.JSONDecodeError:
            WEBHOOKS.labels("dropped").inc()
            return web.Response(status=400, text="bad json")

        ntype = payload.get("notification_type") or ""
        if ntype not in EMOJI:
            log.info("Dropping type %r", ntype)
            WEBHOOKS.labels("dropped").inc()
            return web.Response(text="ignored")
        WEBHOOKS.labels("ok").inc()

        # Close/reopen with comment arrives as TWO webhooks (status + comment) in
        # either order. Buffer issue follow-ups briefly and merge the pair into
        # one message: status payload as the card, comment attached.
        issue_id = (payload.get("issue") or {}).get("issue_id")
        if ntype in ISSUE_FOLLOWUPS and issue_id:
            buffered = pending.pop(issue_id, None)
            if buffered:
                other, task = buffered
                task.cancel()
                if (ntype == "ISSUE_COMMENT") != (other["notification_type"] == "ISSUE_COMMENT"):
                    status_p, comment_p = (other, payload) if ntype == "ISSUE_COMMENT" else (payload, other)
                    merged = dict(status_p)
                    merged["comment"] = comment_p.get("comment") or {}
                    log.info("Merging %s + %s for issue %s", ntype, other["notification_type"], issue_id)
                    await deliver(merged)
                    return web.Response(text="ok")
                await deliver(other)  # same kind twice: flush the old one, buffer the new

            async def flush():
                await asyncio.sleep(MERGE_WINDOW)
                p, _ = pending.pop(issue_id, (None, None))
                if p:  # ponytail: tiny race vs. a webhook landing mid-flush -> worst case two messages
                    await deliver(p)

            pending[issue_id] = (payload, asyncio.create_task(flush()))
            return web.Response(text="buffered")

        await deliver(payload)
        return web.Response(text="ok")

    async def metrics(_req: web.Request) -> web.Response:
        # Content-Type as a header, not via content_type=: the value contains a
        # charset and aiohttp rejects that in content_type=.
        return web.Response(body=generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})

    app = web.Application()
    app.router.add_post("/webhook", webhook)
    app.router.add_get("/metrics", metrics)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()
    log.info("Webhook listening on :8080/webhook, metrics on :8080/metrics")

    await client.sync_forever(timeout=30000)


def selfcheck():
    umap = {"frodo": "@frodo:example.org"}
    team = ["@gandalf:example.org", "@dude:example.org"]
    assert render({"notification_type": "MEDIA_FAILED"}, umap) is None

    body, fmt, m = render(
        {
            "notification_type": "MEDIA_AVAILABLE",
            "subject": "The Lord of the Rings (2001)",
            "message": "One ring to rule them all...",
            "media": {"media_type": "movie", "status": "AVAILABLE"},
            "request": {"requestedBy_username": "frodo"},
        },
        umap,
    )
    assert "The Lord of the Rings (2001) (Movie)" in body and "Requested by: frodo" in body, body
    assert '<a href="https://matrix.to/#/@frodo:example.org">frodo</a>' in fmt, fmt
    assert m == ["@frodo:example.org"], m

    # New request: the team is pinged, the requester themselves is not.
    pending = {
        "notification_type": "MEDIA_PENDING",
        "subject": "The Lord of the Rings",
        "media": {"media_type": "tv"},
        "request": {"requestedBy_username": "frodo"},
    }
    body, fmt, m = render(pending, umap, team)
    assert m == team, m
    assert "Requested by: frodo" in body, body
    # The team ping must be VISIBLE too, not just in m.mentions.
    assert "cc: @gandalf:example.org @dude:example.org" in body, body
    for mxid in team:
        assert f'<a href="https://matrix.to/#/{mxid}">{mxid}</a>' in fmt, fmt
    # With no team configured it stays a pure mention-by-name event, no cc line.
    body, _, m = render(pending, umap)
    assert m == [] and "cc:" not in body, body

    # New issue: team ping as well.
    _, _, m = render(
        {"notification_type": "ISSUE_CREATED", "subject": "The Big Lebowski",
         "issue": {"reportedBy_username": "frodo"}},
        umap, team,
    )
    assert m == team, m

    # Team ping and user ping must not add up to a double ping.
    _, _, m = render(pending, umap, team + ["@gandalf:example.org"])
    assert m == team, m

    # Unknown user -> no link, no ping, no crash.
    _, fmt, m = render(
        {
            "notification_type": "MEDIA_AVAILABLE",
            "subject": "X",
            "request": {"requestedBy_username": "stranger"},
        },
        umap,
    )
    assert "matrix.to" not in fmt and m == []

    # Issue comment: the reporter is pinged, the commenter is named.
    body, _, m = render(
        {
            "notification_type": "ISSUE_COMMENT",
            "subject": "The Big Lebowski",
            "issue": {"issue_type": "Video", "issue_status": "OPEN",
                      "reportedBy_username": "frodo"},
            "comment": {"comment_message": "The audio is missing", "commentedBy_username": "gandalf"},
        },
        umap,
    )
    assert "The audio is missing" in body and "Reported by: frodo" in body and m == ["@frodo:example.org"]

    # Issue type/status localized, affected season/episode, reply link.
    body, fmt, _ = render(
        {
            "notification_type": "ISSUE_CREATED",
            "subject": "The Big Lebowski",
            "issue": {"issue_id": "7", "issue_type": "VIDEO", "issue_status": "OPEN",
                      "reportedBy_username": "frodo"},
            "extra": [{"name": "Affected Season", "value": "1"},
                      {"name": "Affected Episode", "value": "3"}],
        },
        umap, jellyseerr_url="https://jf.example/",
    )
    assert "Video · Open · Season 1, Episode 3" in body, body
    assert "Reply: https://jf.example/issues/7" in body, body
    assert '<a href="https://jf.example/issues/7">Reply</a>' in fmt, fmt

    # Resolved: same link, but labeled as reopen (the page's real affordance).
    body, fmt, _ = render(
        {"notification_type": "ISSUE_RESOLVED", "subject": "X",
         "issue": {"issue_id": "7", "reportedBy_username": "frodo"}},
        umap, jellyseerr_url="https://jf.example/",
    )
    assert "Reopen: https://jf.example/issues/7" in body and "Reply" not in body, body
    assert '🔁 <a href="https://jf.example/issues/7">Reopen</a>' in fmt, fmt
    # No link without issue_id / without URL; season only, no episode.
    body, fmt, _ = render(
        {"notification_type": "ISSUE_RESOLVED", "subject": "X",
         "issue": {"issue_type": "AUDIO", "issue_status": "RESOLVED",
                   "reportedBy_username": "frodo"},
         "extra": [{"name": "Affected Season", "value": "2"}]},
        umap,
    )
    assert "Audio · Resolved · Season 2" in body and "Reply" not in body, body

    # Other-side ping: the reporter comments on their own issue -> team pinged
    # (visibly), the reporter is not.
    self_comment = {
        "notification_type": "ISSUE_COMMENT",
        "subject": "The Big Lebowski",
        "issue": {"issue_id": "7", "issue_type": "VIDEO", "reportedBy_username": "frodo"},
        "comment": {"comment_message": "still broken", "commentedBy_username": "frodo"},
    }
    body, _, m = render(self_comment, umap, team)
    assert m == team and "cc:" in body, (m, body)
    # ...and with no team configured nobody pings (the reporter not even themselves).
    _, _, m = render(self_comment, umap)
    assert m == [], m

    # Merged close-with-comment (status payload + attached comment): resolved
    # headline, comment text and author present, self-close still pings the team.
    merged = {
        "notification_type": "ISSUE_RESOLVED",
        "subject": "The Big Lebowski",
        "issue": {"issue_id": "7", "issue_type": "VIDEO", "issue_status": "RESOLVED",
                  "reportedBy_username": "frodo"},
        "comment": {"comment_message": "fixed it myself", "commentedBy_username": "frodo"},
    }
    body, _, m = render(merged, umap, team)
    assert "Issue resolved" in body and "fixed it myself" in body, body
    assert "Comment by: frodo" in body, body
    assert m == team, m  # frodo closed his own issue -> team pinged, frodo not

    # Auto-approved stays visible but pings nobody (MEDIA_AVAILABLE follows anyway).
    _, _, m = render(
        {"notification_type": "MEDIA_AUTO_APPROVED", "subject": "X",
         "request": {"requestedBy_username": "frodo"}}, umap,
    )
    assert m == [], m

    # ISSUE_REOPENED: both sides pinged, no double ping.
    body, _, m = render(
        {"notification_type": "ISSUE_REOPENED", "subject": "The Big Lebowski",
         "issue": {"issue_id": "7", "issue_type": "VIDEO", "reportedBy_username": "frodo"}},
        umap, team,
    )
    assert "Issue reopened" in body, body
    assert m == ["@frodo:example.org"] + team, m

    # Unknown issue type/status falls back to the raw value.
    body, _, _ = render(
        {"notification_type": "ISSUE_CREATED", "subject": "X",
         "issue": {"issue_type": "WEIRD", "issue_status": "LIMBO"}}, umap
    )
    assert "WEIRD · LIMBO" in body, body

    # HTML escaping at the trust boundary (the title comes from a foreign payload).
    _, fmt, _ = render(
        {"notification_type": "MEDIA_AVAILABLE", "subject": "<img src=x onerror=1>"}, umap
    )
    assert "<img" not in fmt, fmt

    # Error counter: attached to the root logger, counts every log.error from
    # foreign loggers (nio) too - and WARNING must not trigger it.
    logging.getLogger().addHandler(ErrorCounter(level=logging.ERROR))
    before = REGISTRY.get_sample_value("bot_errors_total") or 0
    logging.getLogger("nio.something").error("boom")
    log.warning("just a warning")
    after = REGISTRY.get_sample_value("bot_errors_total") or 0
    assert after == before + 1, f"{before} -> {after}"

    # Notification counter: one series per type.
    NOTIFICATIONS.labels("MEDIA_AVAILABLE").inc()
    assert REGISTRY.get_sample_value("bot_notifications_total", {"type": "MEDIA_AVAILABLE"}) == 1

    # m.mentions must sit cleartext on the m.room.encrypted envelope (no push
    # despite "mentions only" otherwise); with empty mentions the key must not appear.
    fake_encrypt = lambda room, mtype, content: ("m.room.encrypted", {"ciphertext": "x"})
    enc = encrypt_with_cleartext_mentions(fake_encrypt, "!r", {}, ["@gandalf:example.org"])
    assert enc["m.mentions"]["user_ids"] == ["@gandalf:example.org"], enc
    enc = encrypt_with_cleartext_mentions(fake_encrypt, "!r", {}, [])
    assert "m.mentions" not in enc, enc

    # Status + seasons + title link (all parts present).
    body, fmt, _ = render(
        {
            "notification_type": "MEDIA_AVAILABLE",
            "subject": "Poker Face (2023)",
            "media": {"media_type": "tv", "status": "AVAILABLE", "tmdbId": "123"},
            "extra": [{"name": "Requested Seasons", "value": "1"}],
        },
        umap, jellyseerr_url="https://jf.example/",
    )
    assert "Status: Available · Seasons: 1" in body, body
    assert '<a href="https://jf.example/tv/123">' in fmt, fmt

    # Only status / only seasons / neither -> line partial or gone.
    b, _, _ = render({"notification_type": "MEDIA_AVAILABLE", "subject": "X",
                      "media": {"status": "PROCESSING"}}, umap)
    assert "Status: Processing" in b and "Seasons" not in b, b
    b, _, _ = render({"notification_type": "MEDIA_AVAILABLE", "subject": "X",
                      "extra": [{"name": "Requested Seasons", "value": "2"}]}, umap)
    assert "Seasons: 2" in b and "Status" not in b, b
    b, _, _ = render({"notification_type": "MEDIA_AVAILABLE", "subject": "X"}, umap)
    assert "Status" not in b and "Seasons" not in b, b

    # No link without URL or without tmdbId; unknown status -> no line.
    _, fmt, _ = render({"notification_type": "MEDIA_AVAILABLE", "subject": "X",
                        "media": {"media_type": "movie", "tmdbId": "9", "status": "UNKNOWN"}}, umap)
    assert "<a href" not in fmt and "Status" not in fmt, fmt

    # Link escaping: a hostile base URL/tmdbId from config/payload must not break
    # out of the attribute.
    _, fmt, _ = render(
        {"notification_type": "MEDIA_AVAILABLE", "subject": "X",
         "media": {"media_type": "movie", "tmdbId": '"><script>'}},
        umap, jellyseerr_url="https://jf.example",
    )
    assert "<script>" not in fmt and 'href="https://jf.example/movie/&quot;' in fmt, fmt

    # m.image builder: complete file object, caption + m.mentions attached.
    ic = image_content("mxc://x/y", {"key": {"k": 1}, "iv": "iv", "hashes": {"sha256": "h"}, "v": "v2"},
                       200, "image/jpeg", "caption", "<b>caption</b>", ["@gandalf:example.org"])
    assert ic["msgtype"] == "m.image" and ic["file"]["url"] == "mxc://x/y", ic
    assert ic["file"]["key"] == {"k": 1} and ic["file"]["v"] == "v2", ic
    assert ic["body"] == "caption" and ic["filename"] == "poster.jpg", ic
    assert ic["m.mentions"]["user_ids"] == ["@gandalf:example.org"], ic
    assert image_content("m", {"key": {}, "iv": "", "hashes": {}, "v": "v2"},
                         1, "image/jpeg", "b", "f", [])["m.mentions"] == {}

    # i18n: BOT_LANG=de delivers German headlines, unknown values fall back to en.
    set_lang("de")
    body, _, _ = render(
        {"notification_type": "MEDIA_AVAILABLE", "subject": "Das Boot",
         "media": {"media_type": "movie", "status": "AVAILABLE"},
         "request": {"requestedBy_username": "frodo"}},
        umap,
    )
    assert "🎬 Jetzt verfügbar" in body and "(Film)" in body, body
    assert "Angefragt von: frodo" in body and "Status: Verfügbar" in body, body
    set_lang("klingon")
    body, _, _ = render({"notification_type": "MEDIA_AVAILABLE", "subject": "X"}, umap)
    assert "Now available" in body, body
    # Both languages cover exactly the same event types.
    assert STRINGS["en"]["events"].keys() == STRINGS["de"]["events"].keys() == EMOJI.keys()
    assert STRINGS["en"].keys() == STRINGS["de"].keys()

    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
    else:
        asyncio.run(main())
