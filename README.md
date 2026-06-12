# surf — unlock the web for Claude Code

`/surf` gives Claude a **real browser** instead of a plain fetch. Read pages that
return 403 to anti-bot walls, run JavaScript-heavy sites, **see images**, **watch
and download videos**, extract structured data, take desktop **or mobile**
screenshots, render local HTML, find real reference images, and drive pages
**logged-in as you** — all from the CLI.

It routes across three tools and picks the lightest one that works:

| Task | Tool |
|------|------|
| Read / screenshot / extract, fast, public or cookie-login site | **Cloudflare Browser Run** (REST) |
| Click / type / scroll, dynamic content, find a video stream | **Browser Run** (CDP / Playwright) |
| A site you're already logged into (incl. phone-linked apps) | **Claude-in-Chrome extension** |
| CAPTCHA / login / QR scan | **Live View** — you solve, Claude continues |

> **Claude Code skill (local), not claude.ai web.** It shells out to local tools
> (curl/ffmpeg/yt-dlp/node) and your browser cookies — the web sandbox has none of
> those.

## Install

```
/plugin marketplace add MrIago/surf
/plugin install surf@surf
/reload-plugins
```

Or manually: clone into `~/.claude/skills/surf`.

## One-time setup

`/surf` needs Cloudflare **Browser Run** credentials (free plan works). When asked,
provide your **Account ID** and an **API token** with `Browser Rendering - Edit`
(https://dash.cloudflare.com/profile/api-tokens):

```bash
python3 scripts/lib/config.py CF_ACCOUNT_ID=... CF_API_TOKEN=...
# optional:
python3 scripts/lib/config.py GROQ_API_KEY=gsk_...           # video transcription
python3 scripts/lib/config.py SURF_COOKIES_BROWSER="chrome:Profile 1"  # which profile for logged-in renders
```

Keys are read from the environment first, then `~/.config/surf/.env` — nothing is
hardcoded, so the same skill works on anyone's machine.

## Requirements

- **Node** (the interactive driver installs `playwright-core` once: `npm i` in `scripts/`, or `npm i -g playwright-core`).
- **curl** (always present).
- For video / cookies / reference images: **ffmpeg**, **yt-dlp** (`pip install yt-dlp`). On Linux, reading Chrome cookies also needs `secretstorage`.
- The Claude-in-Chrome route needs the extension + a direct Anthropic plan.

## What it can do

```bash
SD=scripts
python3 $SD/cf.py markdown   "<url>"                 # page as clean text
python3 $SD/cf.py screenshot "<url>" --full          # full-page PNG/JPEG
python3 $SD/cf.py screenshot "<url>" --device mobile # 390x844 @3x phone shot
python3 $SD/cf.py screenshot --html-file page.html   # render a LOCAL html you generated
python3 $SD/cf.py json "<url>" --prompt "extract price, title, rating"
python3 $SD/cf.py markdown "<url>" --cookies airbnb.com.br   # render LOGGED-IN
node    $SD/cf_cdp.mjs --url "<url>" --consent --capture-net 'm3u8|mp4' --actions '[{"do":"click","text":"show all photos"}]'
python3 $SD/images.py "estádio São Januário" --download 6    # real reference image URLs + contact sheet
python3 $SD/video.py "<url>" --transcribe --frames 8         # download + transcript + frames
python3 $SD/live_view.py "<url>"                             # captcha/QR -> a link you act on
```

## Honest limits

- Does **not** solve CAPTCHAs — route those to Live View.
- Google Images CAPTCHAs the cloud IP — use Bing (default in `images.py`) or the extension.
- Phone-linked apps (WhatsApp Web) aren't cookie-auth — use the extension or a protocol lib.
- Browser Run has rate limits; for bulk, fetch sequentially and parallelize the reasoning.

MIT © mriago
