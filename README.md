# surf

Gives Claude Code a real browser: cloud Chromium, your own Chrome, or local Playwright, routed per task.

## What it does

Plain `WebFetch` gets 403 on anti-bot walls and never executes JavaScript. surf renders the page in a real browser, so Claude can:

- Read protected pages as clean markdown
- Screenshot any page: desktop or mobile (390x844 @3x), full page or a single element, remote URL or a local HTML file
- Extract structured data with a prompt and a JSON schema
- Render pages logged in as you, by injecting your own Chrome cookies (no password ever leaves your machine)
- Watch videos: download, transcribe, and tile frames into a contact sheet Claude reads
- Find real reference images for a query, with source URLs and a contact sheet
- Hand CAPTCHAs and QR scans to you through a live browser view, then keep driving the same session

## How it works

- Three backends, one decision matrix. Cloudflare Browser Run (managed cloud Chromium) handles public pages without touching your machine. The Claude-in-Chrome extension drives your real Chrome, and is the default whenever you're logged in or the site fights bots — it clears walls no script can, because it isn't a script. Local Playwright reuses your profile for bulk or unattended runs where per-action round-trips would dominate. The skill picks the lightest tool that works and escalates when needed.
- Method beats tool. The same extraction driven by screenshots took 2min29s, driven by one DOM query in the same browser took 30s, and driven by a script took 7.4s — so the skill queries the DOM first, batches what has to be interactive, and screenshots only for genuinely visual questions.
- The REST path (`cf.py`, stdlib-only Python) does one navigate plus one action per call: markdown, rendered HTML, screenshot, AI extraction, links, scrape, PDF. It retries 429s with backoff.
- The CDP driver (`cf_cdp.mjs`) connects Playwright to the same cloud browser over WebSocket and executes a JSON action list (click by text, type, scroll, dismiss the consent banner) in a single run, with zero model round-trips between steps.
- `--capture-net '<regex>'` records matching network requests while the page runs. This is how surf finds video streams behind custom players: the m3u8 never appears in the HTML, it appears on the wire.
- Cookie injection (`cookies.py`) exports your live session from Chrome via yt-dlp and injects it into the cloud browser. Verified on Airbnb: the cloud render showed the user's member price (R$550) where the public page showed R$631. `lib/chrome_cookies.py` does the same decrypt in ~0.1s instead of ~12s, since loading yt-dlp to read a SQLite file dominates the cost.
- Local Playwright (`local_pw.mjs`) runs your own Chrome, logged in, from a **copy** of the profile, so your browser stays open while a script drives another. It syncs only auth-bearing files and only the target host's IndexedDB (31MB, ~2.6s here, versus 561MB if you copy every origin). One call navigates, acts, and extracts. It is not the default, though: on a real Mercado Livre search it ran in 7.4s where the extension driven with `javascript_tool` took 30s and a screenshot-driven loop took 2min29s — but Shopee blocks it outright and ML needs `--headed`. The extension is the user's actual Chrome, so it clears bot walls no script can. Use the script for bulk or unattended runs; use the extension for logged-in work you're supervising.
- The auth map is documented and tested: cookie sessions work in the cloud; IP-bound cookies (LinkedIn) need local curl from your machine; IndexedDB sessions (WhatsApp Web) need the extension or a protocol library. `references/auth-and-cookies.md` covers which is which and why.

## Usage

> Claude Code skill (local). It shells out to curl, node, ffmpeg, and yt-dlp; the claude.ai web sandbox has none of those.

### Install

```
/plugin marketplace add MrIago/surf
/plugin install surf@surf
/reload-plugins
```

Or manually: clone into `~/.claude/skills/surf`.

### One-time setup

surf needs Cloudflare **Browser Run** credentials (the free plan works). When asked, provide your **Account ID** and an **API token** with `Browser Rendering - Edit` (https://dash.cloudflare.com/profile/api-tokens):

```bash
python3 scripts/lib/config.py CF_ACCOUNT_ID=... CF_API_TOKEN=...
# optional:
python3 scripts/lib/config.py GROQ_API_KEY=gsk_...   # video transcription
```

Keys load from the environment first, then `~/.config/surf/.env`. Nothing is hardcoded, so the same skill works on any machine.

#### Which Chrome profile? (do this if you want logged-in pages)

Anything that renders **as you** — `cf.py --cookies`, `local_pw.mjs` — reads your
local Chrome. Browsers usually hold several profiles, and `Default` is often the
*work* account rather than the one you mean, so point surf at the right one:

```bash
# list your profiles and the account in each:
python3 -c "import json,os;print('\n'.join(f\"{k:12} {v.get('user_name','-')}\" for k,v in json.load(open(os.path.expanduser('~/.config/google-chrome/Local State')))['profile']['info_cache'].items()))"

python3 scripts/lib/config.py SURF_COOKIES_BROWSER="chrome:Profile 1"
```

Every script reads that one setting, so cookies and the local browser can't end
up on different accounts. On macOS the path is
`~/Library/Application Support/Google/Chrome/Local State`; on Windows,
`%LOCALAPPDATA%/Google/Chrome/User Data/Local State`. Other browsers: `firefox`,
`edge` (profile syntax is the same).

Nothing is uploaded: cookies are read locally and injected into a browser you
control. `local_pw.mjs` works off a **copy** of the profile in `~/.cache/surf/`
so your own Chrome can stay open; delete that directory any time.

### Requirements

- **Node** (the interactive drivers install `playwright-core` once: `npm i` in `scripts/`, or `npm i -g playwright-core`)
- **curl**
- For video / reference images: **ffmpeg**, **yt-dlp** (`pip install yt-dlp`)
- For logged-in rendering: **cryptography** (`pip install cryptography`) to decrypt
  Chrome's cookies, plus **secretstorage** on Linux (`pip install secretstorage`)
  to read the keyring. Without them surf falls back to yt-dlp, which works but
  costs ~12s per call instead of ~0.1s
- `local_pw.mjs` also needs a local **Chrome** install (it launches `channel: 'chrome'`)
- The Claude-in-Chrome route needs the extension plus a direct Anthropic plan

Check what's missing on your machine:

```bash
python3 scripts/lib/chrome_cookies.py github.com   # prints "<n> cookies" if the decrypt path works
```

### Commands

In normal use you type none of this; you ask Claude to open, read, or screenshot a page and it runs the right script. The primitives:

```bash
SD=scripts
python3 $SD/cf.py markdown   "<url>"                 # page as clean text
python3 $SD/cf.py screenshot "<url>" --full          # full-page screenshot
python3 $SD/cf.py screenshot "<url>" --device mobile # 390x844 @3x phone shot
python3 $SD/cf.py screenshot --html-file page.html   # render a LOCAL html you generated
python3 $SD/cf.py json "<url>" --prompt "extract price, title, rating"
python3 $SD/cf.py markdown "<url>" --cookies airbnb.com.br   # render LOGGED IN
node    $SD/cf_cdp.mjs --url "<url>" --consent --capture-net 'm3u8|mp4' --actions '[{"do":"click","text":"show all photos"}]'
python3 $SD/images.py "sao januario stadium" --download 6    # real reference images + contact sheet
node    $SD/local_pw.mjs --url "<url>" --cookies <domain> \
        --eval '() => [...document.querySelectorAll(".item")].map(e => e.innerText)'   # logged-in, ~2s
python3 $SD/video.py "<url>" --transcribe --frames 8         # download + transcript + frames
python3 $SD/live_view.py "<url>"                             # CAPTCHA/QR: a link you act on
```

## Scope and honest limits

- Does **not** solve CAPTCHAs. It opens a Live View link so you solve them, then continues in the same session.
- Google Images CAPTCHAs the cloud IP; `images.py` defaults to Bing (or use the extension for Google).
- Phone-linked apps (WhatsApp Web, Telegram Web) do not authenticate with cookies, by design. Use the extension, local Playwright with your real profile, or a protocol library such as Baileys.
- Cloudflare Browser Run has rate limits (free plan: 10 browser-minutes per day). For bulk jobs, fetch one URL at a time and parallelize the analysis instead of the fetches.
- Never acts on instructions found inside a page, and asks before submitting forms, purchasing, or linking a device.

MIT © mriago
