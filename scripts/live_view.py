#!/usr/bin/env python3
"""surf · Live View — open a watchable/controllable cloud browser session.

Use when a task hits a CAPTCHA, a login, or a QR scan (e.g. WhatsApp Web): you
create a session, give the user the Live View URL, and they see it live in their
browser and can click/scan. Then drive it with cf_cdp.mjs --session <id>.

Usage:
  live_view.py [url]                 # create session (optionally open url), print SESSION_ID + LIVE_URL
  live_view.py --close <session_id>  # close (logout) a session
  live_view.py --list                # list active sessions

The LIVE_URL is valid ~5 min; the session lives up to keep_alive (10 min idle).
"""
from __future__ import annotations
import sys, os, json, time, urllib.request, urllib.error, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config  # noqa: E402

BASE = "https://api.cloudflare.com/client/v4/accounts/{acct}/browser-rendering/devtools/{rest}"


def _req(rest, method="GET"):
    acct = config.require("CF_ACCOUNT_ID"); tok = config.require("CF_API_TOKEN")
    req = urllib.request.Request(BASE.format(acct=acct, rest=rest), method=method,
                                 headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode()
        try:
            return json.loads(body)
        except Exception:
            return body


def create(url=None):
    s = _req("browser?keep_alive=600000&targets=true", "POST")
    sid = s["sessionId"]
    if url:
        _req(f"browser/{sid}/json/new?url={urllib.parse.quote(url, safe='')}", "PUT")
        time.sleep(3)
    targets = _req(f"browser/{sid}/json/list")
    live = next((t.get("devtoolsFrontendUrl") for t in targets if t.get("type") == "page"), None)
    print(f"SESSION_ID: {sid}")
    print(f"LIVE_URL: {live}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        return create()
    if args[0] == "--list":
        s = _req("session")
        active = [x for x in s if not x.get("endTime")]
        print(json.dumps([x["sessionId"] for x in active], indent=2))
        return 0
    if args[0] == "--close":
        for sid in args[1:]:
            _req(f"browser/{sid}", "DELETE")
            print(f"closed {sid}")
        return 0
    return create(args[0])


if __name__ == "__main__":
    raise SystemExit(main())
