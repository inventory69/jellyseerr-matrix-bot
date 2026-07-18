"""Regenerate the README screenshots (assets/screenshot-{en,de}.png).

Renders the bot's real formatted_body inside an Element-Web-dark mock bubble,
so the screenshots never drift from what the bot actually sends. Staged
content: "A Trip to the Moon" (1902, public domain), poster is poster.svg.

  python assets/mock/gen.py en && python assets/mock/gen.py de
  firefox --headless --no-remote --window-size=880,1150 \
      --screenshot shot.png file://$PWD/assets/mock/shot-en.html
  magick shot.png -trim +repage -bordercolor '#181b21' -border 32 \
      assets/screenshot-en.png
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent))
import bot  # noqa: E402

lang = sys.argv[1] if len(sys.argv) > 1 else "en"
bot.set_lang(lang)
overview = {
    "en": "Six astronomers ride a capsule fired from a giant cannon "
          "straight into the eye of the Moon.",
    "de": "Sechs Astronomen reisen in einer Kapsel, abgefeuert aus einer "
          "riesigen Kanone, mitten ins Auge des Mondes.",
}[lang]
payload = {
    "notification_type": "MEDIA_AVAILABLE",
    "subject": "A Trip to the Moon (1902)",
    "message": overview,
    "media": {"media_type": "movie", "tmdbId": 775, "status": "AVAILABLE"},
    "request": {"requestedBy_username": "frodo"},
}
_, formatted, _ = bot.render(
    payload, {"frodo": "@frodo:example.org"},
    jellyseerr_url="https://jellyseerr.example.org",
)

page = f"""<meta charset="utf-8">
<style>
  html, body {{ margin: 0; }}
  body {{
    zoom: 2;                           /* 2x for a crisp PNG */
    background: #181b21;               /* Element Web dark timeline */
    font-family: "Noto Sans", sans-serif;
    font-size: 14.3px; line-height: 1.55; color: #e8ecf2;
    width: 440px;
  }}
  .msg {{ padding: 18px 20px 16px 20px; }}
  .poster img {{ width: 196px; border-radius: 8px; display: block; margin-bottom: 8px; }}
  .caption a {{ color: #4e9df8; text-decoration: none; }}
  /* matrix.to user links render as mention pills, like Element does.
     frodo is "you" in this shot -> own-mention red pill */
  .caption a[href^="https://matrix.to"] {{
    background: #d3222a; color: #fff; border-radius: 9999px;
    padding: 1px 8px 2px 8px; font-size: 0.92em;
  }}
</style>
<div class="msg">
  <div class="poster"><img src="poster.svg"></div>
  <div class="caption">{formatted}</div>
</div>
"""
out = HERE / f"shot-{lang}.html"
out.write_text(page)
print("wrote", out)
