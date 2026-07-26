# surf · speed — why browser work drags, and the order of attack

Browser tasks feel slow for one reason: **the model round-trip**. Every tool call
is Claude → MCP → browser → page → back, a few seconds each. A task done as 20
screenshot-look-click cycles costs minutes; the same task as one script costs
seconds. Measured on this machine, same job (Wikipedia Top-25 → 5 titles+links):

| Path | Time |
|------|------|
| `local_pw.mjs --eval` (one DOM query) | **2.1s** |
| extension, screenshot-driven loop | minutes (13 min in a published benchmark) |

So the rule is not "use a faster browser" — it's **collapse the round-trips**.

## Order of attack (cheapest first)

1. **Can a script do the whole thing?** Then don't use the extension at all.
   - Public/cookie-login page → `cf.py` (cloud, nothing on the user's machine).
   - Logged-in / IP-bound / needs their real session → `local_pw.mjs`.
   One invocation navigates, acts, extracts, and returns. No per-step round-trip.

2. **Inside a browser, query the DOM — don't look at pixels.**
   `--eval` (local_pw), `page.evaluate` (cf_cdp), or `javascript_tool` (extension)
   turns "read this listing" into one call returning clean JSON. A screenshot of
   the same listing costs a round-trip, image tokens, and a second call to act on
   what you saw. Reach for `querySelectorAll(...).map(...)` first, always.

3. **Batch what must be interactive.** Extension: `browser_batch` groups
   click/type/scroll/navigate into one round-trip. Scripts: `--actions`.
   Coordinates in a batch refer to the screenshot *before* it — if the page
   re-renders mid-batch, end the batch with a screenshot and decide after.

4. **Target elements by ref/selector/text, never guessed coordinates.**
   `find` / `read_page` give refs that survive relayout. Coordinate clicks break
   when a list scrolls (a repeated real failure — see pitfalls.md).

5. **Screenshot last, and only for genuinely visual questions.** "Does this look
   right", "what's the layout", "read this chart". Not for extracting text.

## When the extension is still the right call

It is not the slow option because it's bad — it reaches things nothing else does:

- The user is **watching** and wants to see it happen, or take over mid-task.
- A **phone-linked** session (WhatsApp/Telegram Web) that lives in IndexedDB of
  the running browser.
- **Console/network debugging** of a page the user has open.
- A page whose session is bound to that exact live browser (some course players).

Use it there, but still apply rules 2-4: `javascript_tool` + `browser_batch` +
refs. That combination is most of the difference between "13 minutes" and "fast".

## Cost of each path (rough)

- `local_pw.mjs`: ~2s cold (profile sync ~1.1s when stale, cookie decrypt ~0.1s,
  browser ~2s). Free. Uses the user's IP and CPU.
- `cf.py` / `cf_cdp.mjs`: ~2-5s per call, bills browser-seconds, cloud IP
  (blocked by some sites, blocked by CAPTCHA).
- extension: seconds *per action* plus image tokens per screenshot.

## Gotchas that cost time (add to this list)

- **SPA content isn't there at `domcontentloaded`.** `local_pw.mjs` returns as
  soon as the DOM parses, so an `--eval` against a React feed sees an empty
  shell. Add `--actions '[{"do":"wait","ms":3000}]'`, or query a server-rendered
  node instead. (Hit on the LinkedIn feed: auth was fine, the posts hadn't
  rendered.)
- **Headless trips heavy bot walls even when logged in.** LinkedIn authenticates
  fine but withholds feed content headless. Use `--headed`, or the extension.
- **`cookies.py` costs ~12s** (yt-dlp import) — `lib/chrome_cookies.py` does the
  same in ~0.1s. `local_pw.mjs` already prefers the fast one; don't call the slow
  path directly unless the fast one fails.
- **WhatsApp Web does NOT survive the profile copy** (tested): its IndexedDB
  copies fine but the page still shows the QR, because the session key lives in
  the OS keyring and the device is validated server-side. Use the extension (a
  live browser) or Baileys — as auth-and-cookies.md already said. Cookie- and
  localStorage-based sites (GitHub, LinkedIn) do survive.
- **The right profile matters.** This machine has 17 Chrome profiles; the
  personal one is often some `Profile N`, while `Default`
  may be a work account. `local_pw.mjs` and `chrome_cookies.py` both read the
  profile from `SURF_COOKIES_BROWSER`, so they stay on the same account — but
  check before assuming when a login "mysteriously" isn't there.
- **IndexedDB is copied per-host, not wholesale.** Copying all of it costs 561MB
  and ~8s (WhatsApp history alone is 412MB); the per-host slice is 31MB and
  ~2.6s. `--all-idb` forces the full copy if a task genuinely spans many origins.

## Keep this file honest

When a browser task takes noticeably long, add the cause here. The point of this
reference is that no one re-learns the same lesson twice — same spirit as the
`browser-extension-tricks` memory, which holds the per-trick detail.
