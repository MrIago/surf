# surf · the tools, in depth

All proven against real sites (Airbnb logged-in, a paid course, WhatsApp Web).

## 0. Built-in browser of the Claude desktop app (`mcp__Claude_Browser__*`)

Only in the desktop app's Code tab (since July 2026); absent in a terminal
session. A tabbed Chromium in the app's Browser pane: the user watches live and can
take over. **Clean profile**, separate from their Chrome — no saved logins, nothing
lands in their Chrome history. Default for interactive work.

- Open: `preview_start {url}` (new tab) or `{name}` (dev server from
  `.claude/launch.json`); `navigate`, `tabs_create/select/close`.
- Read: `get_page_text`, `read_page` (a11y tree with `ref_N`), `find`,
  `javascript_tool` (REPL semantics, last expression returned).
- Act: `computer` (click by `ref`, type, key, scroll, zoom, screenshot with
  `scale`), `form_input`, `browser_batch` for a sequence in one round-trip.
- Device: `resize_window` preset `mobile` (375×812, touch, Android UA — reload
  after switching), `tablet`, `desktop` (resets); `colorScheme light|dark`.
- Debug: `read_console_messages`, `read_network_requests` (with response bodies).
- Logins: the user signs in in the pane (OAuth popups work) and turns on **Keep
  cookies** in the ⋮ menu so it survives restarts. You can't import their Chrome
  cookies into it (httpOnly). Never type the user's real password yourself; a
  project's test account is fine on their own app.
- Permissions: the first action on an external site shows a card (Allow once /
  Always allow / Deny), per domain including subdomains. Localhost and project files
  need none. Safety classifiers review clicks/typing on external pages.
- Limits: no frame export (videos → Playwright, `recording.md`), not for bulk.

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
round-trip between steps. **Not the default** — see the decision summary below.
Measured 7.4s on a Mercado Livre search where the extension driven properly
(`javascript_tool`) took 30s, and driven by screenshots took 2min29s. Worth it
for bulk or unattended work; not worth the bot walls and the extra Chrome for a
one-off page.

**How it dodges the profile lock.** Chrome locks its profile dir, so pointing
Playwright at the live one would force the user to close their browser. Instead
`local_pw.mjs` copies only the auth-bearing files (Cookies, Login Data, Local
Storage, Preferences, Network, plus the *target host's* IndexedDB) into
`~/.cache/surf/pw-profile`, re-syncing when the copy is stale or was built for a
different host. The user never closes anything. Per-host IndexedDB matters:
copying every origin costs 561MB/~8s on this machine (WhatsApp history alone is
412MB) versus 31MB/~2.6s for one host. `--all-idb` opts into the full copy.

**What it does and doesn't authenticate.** Cookie- and localStorage-based
sessions survive the copy (verified on GitHub and LinkedIn). Phone-linked apps do
**not**: WhatsApp Web copies its IndexedDB fine but still shows the QR, because
the session key is in the OS keyring and the device is validated server-side.
Route those to the extension or Baileys.

**Why cookies are injected separately.** Chrome encrypts cookie values with a
keyring key tied to the original profile, so the copied `Cookies` file decrypts
to empty in a fresh launch (verified). `--cookies <domain>` therefore re-injects
them decrypted via `lib/chrome_cookies.py` (~0.1s; it reads the SQLite and does
the AES-CBC itself, vs ~12s for the yt-dlp path in `cookies.py`, kept as fallback).
localStorage/IndexedDB need no such trick — they're plaintext in the copy, which
is what keeps token-in-storage and phone-linked sites logged in.

- `--eval '<fn>'` — the fast extractor: one DOM query returns JSON, no screenshot.
- `--actions` / `--capture-net` / `--consent` / `--screenshot` — same shape as `cf_cdp.mjs`.
- `--profile <name>` — defaults to the profile in `SURF_COOKIES_BROWSER` (so this
  and `cookies.py` stay on one account); override when a session lives elsewhere.
- `--headed` — visible window; also much less bot-like than headless.
- `--sync` — force a refresh after the user logs into something new.

Downsides: uses their machine/IP, and headless still trips aggressive bot walls
(use `--headed`, or fall back to the extension). See auth-and-cookies.md for
phone-linked-app specifics and the Baileys alternative.

## Decision summary

- Interactive, visible, the user watching (their app, docs, any site) → **built-in
  browser** (desktop app). Login needed → the user signs in in the pane once.
- Data from a site they're logged into in Chrome, headless → **local_pw.mjs
  --cookies**.
- Act as the user in their real Chrome → **extension**, only when they ask for it.
- Public page, read or extract → **REST (cf.py)**; needs clicks or network
  capture → **CDP (cf_cdp.mjs)**. Both keep it off the user's machine.
- Dozens of pages, or a long unattended run, on a site that tolerates headless →
  **local_pw.mjs**.
- Phone-linked live session, or console/network debugging → **extension**.
- CAPTCHA / QR / login wall → **Live View**, user acts, then continue.

Measured (Mercado Livre search, same extraction): extension screenshot-loop
2min29s → extension + `javascript_tool` 30s → `local_pw.mjs` 7.4s. Fix the method
before reaching for another tool; see `speed.md`.
