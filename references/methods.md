# surf · the four tools, in depth

All proven against real sites (Airbnb logged-in, a paid course, WhatsApp Web).

## 1. Cloudflare Browser Run — REST Quick Actions (`cf.py`)

A managed cloud Chromium renders the page and returns the result in one HTTP
call. Stateless: navigate + one action. Fastest path; doesn't touch the user's
machine; scales/parallelizes.

- Actions: `markdown`, `content` (rendered HTML), `screenshot` (`--full`),
  `json` (AI extraction with `--prompt`/`--schema`), `links`, `scrape`
  (`--selector`), `pdf`.
- `--wait networkidle2` is the default (best for SPAs). `--ua "<modern UA>"` to
  defeat "update your browser" walls.
- `--cookies <domain>` injects the user's local Chrome cookies → page renders
  **logged-in** (personalized prices, paywalled content). See auth-and-cookies.md.
- Pricing: free plan = 10 min browser/day; paid = 10h/mo then $0.09/h. Each
  response carries `X-Browser-Ms-Used`.

Use for: read, screenshot, structured extraction, PDFs — the 80% case.

## 2. Cloudflare Browser Run — CDP interactive (`cf_cdp.mjs`)

The SAME cloud browser, but driven via Playwright over a WebSocket (CDP). A real
driveable session that persists up to 10 min: click, type, scroll, open modals,
read dynamic DOM, **spy the network** to find video/stream/pdf URLs, inject
cookies. Connect string:
`wss://api.cloudflare.com/client/v4/accounts/<acct>/browser-rendering/devtools/browser?keep_alive=600000`
(Authorization: Bearer <token>).

- `--actions` is a JSON list of steps (`click` by `text`/`selector`/`coord`,
  `type`, `scroll`, `press`, `wait`, `dismiss-consent`, `screenshot`).
- `--capture-net '<regex>'` records matching request URLs — the way to discover a
  hidden video stream (e.g. `m3u8|mp4`) behind a custom player.
- `--keep-alive` leaves the session up and prints a session id (pair with
  `live_view.py` for a watch link, or reconnect with `--session <id>`).
- Speed win vs the extension: one script does N steps with no model round-trip
  between them.

Use for: interaction, dynamic content, finding streams, multi-step flows.

## 3. Claude-in-Chrome extension (`mcp__claude-in-chrome__*`)

Drives the **user's real Chrome**, with all their native logins (including
phone-linked apps), visible in real time, plus console/network debugging. The
only tool that reaches sites authenticated by something other than cookies.

Setup: user runs `/chrome` (or `claude --chrome`); first time needs a Chrome +
Claude Code restart. Requires a direct Anthropic plan.

How to use well:
1. Load tools in ONE ToolSearch:
   `select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__read_page,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__list_connected_browsers`
   (add `find`, `browser_batch`, `read_network_requests`, `get_page_text` as needed).
2. **Required:** call `list_connected_browsers`, then `AskUserQuestion` listing
   every browser as an option (label = display name, include deviceId) plus the
   "open a confirmation screen in every Chrome" option. Then `select_browser`.
3. `tabs_context_mcp` (createIfEmpty), make a fresh tab, `navigate`.
4. Group predictable steps with `browser_batch` (one round-trip, much faster).
5. Prefer `find` (natural-language) or in-page search over coordinate clicks —
   coordinates drift when the list scrolls/relayouts (a real, repeated failure).
6. To "see" content crisply, download the actual file (e.g. an image) and Read it
   rather than zooming a screenshot.

Downside: slow (each action is a round-trip + screenshot), one browser at a time,
occupies the user's machine.

## 4. Local Playwright, real session (`local_pw.mjs`)

"The extension, but as a script": the user's own logins, their IP, and no model
round-trip between steps. Measured 2.1s for a job an extension loop took minutes on.

**How it dodges the profile lock.** Chrome locks its profile dir, so pointing
Playwright at the live one would force the user to close their browser. Instead
`local_pw.mjs` copies only the auth-bearing files (~109MB of a 2.2GB profile:
Cookies, Login Data, Local Storage, IndexedDB, Preferences, Network) into
`~/.cache/surf/pw-profile`, and re-syncs when the copy is >12h old (~1.1s). The
user never closes anything.

**Why cookies are injected separately.** Chrome encrypts cookie values with a
keyring key tied to the original profile, so the copied `Cookies` file decrypts
to empty in a fresh launch (verified). `--cookies <domain>` therefore re-injects
them decrypted via `lib/chrome_cookies.py` (~0.1s; it reads the SQLite and does
the AES-CBC itself, vs ~12s for the yt-dlp path in `cookies.py`, kept as fallback).
localStorage/IndexedDB need no such trick — they're plaintext in the copy, which
is what keeps token-in-storage and phone-linked sites logged in.

- `--eval '<fn>'` — the fast extractor: one DOM query returns JSON, no screenshot.
- `--actions` / `--capture-net` / `--consent` / `--screenshot` — same shape as `cf_cdp.mjs`.
- `--profile "Profile 1"` — the user may have many; pick the one with the session.
- `--headed` — visible window; also much less bot-like than headless.
- `--sync` — force a refresh after the user logs into something new.

Downsides: uses their machine/IP, and headless still trips aggressive bot walls
(use `--headed`, or fall back to the extension). See auth-and-cookies.md for
phone-linked-app specifics and the Baileys alternative.

## Decision summary

- Public/cookie-login, read or extract → **REST (cf.py)**.
- Need to interact / find a stream, from a cloud IP → **CDP (cf_cdp.mjs)**.
- Logged-in as the user, multi-step, or IP-bound site → **local_pw.mjs**.
- Must be visible/native, phone-linked live session, or console/network debug → **extension**.
- CAPTCHA / QR / login wall → **Live View**, user acts, then continue.
