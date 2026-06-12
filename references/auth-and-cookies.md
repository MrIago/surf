# surf · authentication — what works where

## Two kinds of session, two outcomes

1. **Cookie-based** (most sites: shops, courses, dashboards, Airbnb, Gmail web).
   The session lives in cookies → exportable → injectable into Browser Run.
   `cf.py --cookies <domain>` and `cf_cdp.mjs --cookies-domain <domain>` do this:
   they call `cookies.py`, which uses `yt-dlp --cookies-from-browser` to read the
   user's *already-logged-in* browser (no password, no login). Proven: rendered a
   user's personalized Airbnb price (R$550 vs R$631 public).

2. **IndexedDB / device-linked** (WhatsApp Web, Telegram Web, some E2E apps).
   The session is NOT in cookies — it's crypto keys in IndexedDB tied to the
   phone via multi-device pairing. **Cookies will never authenticate these.**
   Injecting them just shows a QR. This is by design, not a missing cookie.

## Choosing the cookie profile

`yt-dlp` reads the **Default** Chrome profile unless told otherwise. If the user
is logged in on another profile, set it:
```bash
python3 "$SD/scripts/lib/config.py" SURF_COOKIES_BROWSER="chrome:Profile 1"
```
A near-empty cookie export for a domain the user *is* logged into is the tell that
either the wrong profile is set, or (for WhatsApp-type apps) auth isn't in cookies.

## Phone-linked apps (WhatsApp/Telegram Web)

Three ways in, best first:

1. **Protocol library (e.g. Baileys for WhatsApp)** — not a browser at all; speaks
   the WhatsApp protocol over WebSocket. Prints a QR, user scans **once**, then it
   **persists the session to disk** and reconnects forever. Fast, scriptable,
   downloads media bytes natively (`downloadMediaMessage`). Best for ongoing use.
2. **Claude-in-Chrome extension** — the user's real Chrome is already linked. Works
   immediately, but slow and visible.
3. **Browser Run + QR via Live View** — open `web.whatsapp.com` with a modern UA
   (`cf_cdp.mjs --ua modern`), give the user the Live View link, they scan → the
   cloud session is now a linked device and you can read chats. Proven to work, but
   the cloud session is ephemeral (rescan next time).

`cf.py`/`cf_cdp.mjs` cookie injection alone → QR screen (won't log in).

## Anti-abuse (important)

Linking/connecting to one account many times in minutes (extension + cloud +
Baileys, repeated reconnects) trips WhatsApp's protection → `401`/conflict, and a
genuinely paired session fails to reconnect. Keep to **one connection at a time**,
back off on `401`, and don't loop. A 515 ("restart required") from Baileys means
the scan **succeeded** — reconnect once (the project's own loop handles this).

## After any device link — tell the user

When a scan links a device (WhatsApp etc.), say so, and tell them to remove it in
**WhatsApp → Linked devices** when done. Close cloud sessions with
`live_view.py --close <id>`.
