# surf · speed — method first, tool second

Browser tasks feel slow because of **the model round-trip**: every tool call is
Claude → MCP → browser → page → back. A screenshot-driven loop pays that toll a
dozen times *and* burns image tokens on each pass.

## The benchmark that settles the order

Same job, measured end to end: a Mercado Livre search, extracting title, price,
seller and IPS/FHD flags from the result cards.

| Path | Time | Notes |
|------|------|-------|
| Extension, screenshot→look→scroll→look | **2min29s** | what "driving a browser" looks like by default |
| Extension + `javascript_tool` | **30s** | *same tool*, one DOM query instead of pixels |
| `local_pw.mjs --headed --eval` | **7.4s** | no round-trips at all |

Read the middle row carefully: **changing the method bought 5x; changing the tool
bought 4x more.** The method fix is the one that matters, because it costs
nothing and works on every site — including the ones where scripts get blocked.

### Second benchmark: a logged-in course page (cademi)

Reaching a lesson page behind a paid login and pulling the player's iframe src —
the step that gates transcribing a course. Same lesson, all three routes:

| Route | Time |
|---|---|
| `local_pw.mjs --cookies … --eval` | **~6s** |
| `cf.py content --cookies` (cloud Browser Run) | ~15s |
| extension + `javascript_tool` | ~32s |

Two lessons here. First, the ordering flips from the ML case: this page doesn't
fight bots, so the script wins outright and even the *cloud* beats the extension.
Choose per site, not by a fixed ranking. Second, the skill's own docs had claimed
this page was IP-bound and reachable only via the extension — it isn't. When a
doc says "impossible", re-test before designing around it.

## The order of attack

1. **Query the DOM, don't look at pixels.** `javascript_tool` (extension),
   `--eval` (local_pw), `page.evaluate` (cf_cdp) all turn "read this listing"
   into one call returning clean JSON. Screenshots cost a round-trip, image
   tokens, *and* a follow-up call to act on what you saw.
2. **Batch what must be interactive.** `browser_batch` groups
   navigate/click/type/wait into one round-trip; scripts take `--actions`.
   Coordinates inside a batch refer to the screenshot taken *before* it, so if
   the page re-renders mid-batch, end the batch and decide after.
   Note `javascript_tool`, `find` and `read_page` cannot go inside a batch.
3. **Target by ref/selector/text, never guessed coordinates** — they drift when
   a list scrolls (repeated real failure, see pitfalls.md).
4. **Screenshot last**, only for genuinely visual questions.

## Which tool, and why the extension is usually right

The extension is the user's **real Chrome**. That buys things no script can fake:

- **No bot wall.** Real fingerprint, real history. Shopee blocks `local_pw.mjs`
  outright; Mercado Livre serves it an error page unless `--headed`. Both are
  fine in the extension.
- **No auth plumbing.** No cookie export, no profile copy, no decrypt. Sessions
  that live outside cookies (phone-linked apps) work only here.
- **No second browser.** `local_pw.mjs` launches another Chrome next to one that
  may already hold dozens of tabs — running several `--headed` sessions back to
  back has crashed this machine.
- **The user can watch and take over** mid-task.

Its one weakness is the per-action round-trip, and rules 1-2 mostly erase it.

So: **the desktop app's built-in browser by default for interactive work** (same
tools and same speed rules, visible to the user, isolated from their Chrome; the
extension only when they ask, for acting inside their real Chrome); `cf.py` for
public pages (cloud, nothing on their machine); `local_pw.mjs` when round-trips
genuinely dominate — dozens of pages in a batch, or a long unattended run — on a
site that tolerates it.

## Cost of each path (rough)

- extension: ~5-10s per round-trip; near-zero setup; no extra process.
- `cf.py` / `cf_cdp.mjs`: ~2-5s per call, bills browser-seconds, cloud IP
  (blocked by some sites, and never solves CAPTCHAs).
- `local_pw.mjs`: ~2-7s for a whole run, free, uses their IP and CPU — but
  launches a real Chrome, so budget the RAM.

## Gotchas that cost time (add to this list)

- **SPA content isn't there at `domcontentloaded`.** `local_pw.mjs` returns as
  soon as the DOM parses, so an `--eval` against a React feed sees an empty
  shell. Add `--actions '[{"do":"wait","ms":3000}]'`, or query a server-rendered
  node instead. (Hit on the LinkedIn feed: auth was fine, the posts hadn't
  rendered.)
- **Headless trips bot walls even when logged in.** Measured: LinkedIn
  authenticates but withholds the feed; **Mercado Livre** returns "Hubo un error
  accediendo a esta pagina" and needs `--headed`; **Shopee** redirects to
  `/verify/traffic/error` even with cookies injected, and its internal
  `/api/v4/search/search_items` answers `error: 90309999`. All three are fine in
  the extension. When a script hits a wall, switch tools instead of escalating
  workarounds.
- **Don't run several `--headed` sessions back to back.** Each is a real Chrome
  next to the user's own; this crashed the machine. The script now has a
  `--max-seconds` watchdog and always closes in a `finally`, but the underlying
  cost is real — prefer the extension when a task is interactive anyway.
- **Duplicate rows usually mean the selector matched card *and* container.**
  On ML, `li.ui-search-layout__item` plus `div.poly-card` returned every item
  twice; dedupe by title, or pick the innermost selector.
- **`cookies.py` costs ~12s** (yt-dlp import) — `lib/chrome_cookies.py` does the
  same in ~0.1s. `local_pw.mjs` already prefers the fast one; don't call the slow
  path directly unless the fast one fails.
- **WhatsApp Web does NOT survive the profile copy** (tested): its IndexedDB
  copies fine but the page still shows the QR, because the session key lives in
  the OS keyring and the device is validated server-side. Use the extension (a
  live browser) or Baileys — as auth-and-cookies.md already said. Cookie- and
  localStorage-based sites (GitHub, LinkedIn) do survive.
- **The right profile matters.** `Default` is often *not* the account you want —
  a machine can carry a dozen Chrome profiles, and the work account frequently
  sits in `Default` while the personal one is some `Profile N`. `local_pw.mjs`
  and `chrome_cookies.py` both read the profile from `SURF_COOKIES_BROWSER`, so
  they can't drift apart; set it once. When a login "mysteriously" isn't there,
  check the profile before debugging anything else — map them with:
  `python3 -c "import json;print(json.load(open('$HOME/.config/google-chrome/Local State'))['profile']['info_cache'])"`
- **IndexedDB is copied per-host, not wholesale.** Copying all of it costs 561MB
  and ~8s (WhatsApp history alone is 412MB); the per-host slice is 31MB and
  ~2.6s. `--all-idb` forces the full copy if a task genuinely spans many origins.

## Keep this file honest

When a browser task takes noticeably long, add the cause here. The point of this
reference is that no one re-learns the same lesson twice — same spirit as the
`browser-extension-tricks` memory, which holds the per-trick detail.
