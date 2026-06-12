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

## 4. Local Playwright (real profile)

Run Playwright on the user's machine with `launchPersistentContext(userDataDir)`
pointing at their real Chrome profile — reuses its IndexedDB/localStorage, so it's
logged into everything (including WhatsApp Web). Scriptable + native logins + fast.
Downsides: local (their IP/CPU), and the profile must be **closed** (Chrome locks
it). Essentially "the extension, but as a script." See auth-and-cookies.md for the
phone-linked-app specifics and the Baileys alternative.

## Decision summary

- Public/cookie-login, read or extract → **REST (cf.py)**.
- Need to interact / find a stream → **CDP (cf_cdp.mjs)**.
- Logged-in-by-phone, or want it visible/native, or debug → **extension**.
- Want native logins in a script → **local Playwright**.
- CAPTCHA / QR / login wall → **Live View**, user acts, then continue.
