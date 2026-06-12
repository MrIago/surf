# surf · pitfalls & habits (learned the hard way)

## Always dismiss the consent banner first
Almost every site shows a floating cookie/consent popup that crowds the viewport
and hides content. Click "Accept all" before screenshotting/extracting:
`cf_cdp.mjs --consent` (or `{"do":"dismiss-consent"}` as the first action). The
matcher tries role+text across several languages; if it misses, the button may be
inside a `[role=dialog]` — target it with a `--actions` click by text, or press
Escape. (Repeated real miss: a plain `getByRole('button',{name:/accept/i})` failed
on Airbnb because the button was nested in a dialog.)

## Coordinate clicks are fragile
Clicking by `[x,y]` breaks when a list scrolls or relayouts (we hit "Archived"
instead of a chat twice). Prefer: in-page **search** then click the result by
selector/title, the extension's `find`, or `--actions` click by `text`/`selector`.
Use coordinates only as a last resort, right after a fresh screenshot.

## CAPTCHA / Turnstile / bot walls
Browser Run does NOT solve CAPTCHAs (it's always identified as a bot). The "update
your browser" wall is different — that's just an old UA; fix with `--ua modern`.
For a real CAPTCHA/login/QR: open Live View (`live_view.py`), hand the link to the
user to solve, then continue on that `--session`.

## Rate limits / anti-abuse
- Browser Run: `429` = too many req (free: 1/10s; paid: 10/s) → back off, retry
  (`cf.py` already retries 429 with backoff).
- Account logins (esp. WhatsApp): many connects in minutes → `401`/conflict. One
  connection at a time; don't loop reconnects.

## Don't leave the user staring at nothing
Long fixed waits (we used 25s before driving Live View) read as "it froze." Keep
actions tight, or tell the user what you're waiting for. In Live View demos, give
lead time but say so.

## Sessions & cleanup
- A Playwright `browser.close()` on a Browser Run session **kills** it. To keep it
  alive for the user, disconnect via `process.exit(0)` instead (cf_cdp `--keep-alive`).
- List/close sessions: `live_view.py --list` / `--close <id>`. Close cloud sessions
  when done — and remind the user to remove any device a QR scan linked.

## Fidelity
To truly see an image, download the real file and Read it — sharper than zooming a
screenshot. Browser Run `/screenshot`, the extension's download, and `video.py`
frames all give real pixels.

## Cost awareness
Browser Run bills browser-seconds; the extension uses the user's machine; local
Playwright is free but ties up their Chrome. Default to the lightest tool (REST)
and escalate only when the task needs it.
