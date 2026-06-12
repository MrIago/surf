#!/usr/bin/env python3
"""surf · export your local browser cookies for a domain (to render pages logged-in).

Reuses your already-logged-in browser session (like /consume does) — it does NOT
log in or store passwords. Uses yt-dlp's --cookies-from-browser to read the
browser's cookie store (on Linux, decrypts via the keyring).

Pick the browser/profile via SURF_COOKIES_BROWSER (default "chrome"); for a
specific profile use "chrome:Profile 1". Config: lib/config.py.

NOTE: cookies authenticate normal sites (shops, courses, Airbnb). They do NOT
authenticate phone-linked apps (WhatsApp/Telegram Web) — those keep their session
in IndexedDB, not cookies. For those, use the extension or local Playwright.

Usage:
  cookies.py <domain>            # -> Netscape cookie file path on stdout
  cookies.py <domain> --json     # -> Browser Run cookie array (JSON) on stdout
"""
from __future__ import annotations
import sys, os, json, tempfile, subprocess, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config  # noqa: E402

MAXEXP = 253402300799


def export(domain: str) -> str:
    if not shutil.which("yt-dlp"):
        raise SystemExit("[surf] yt-dlp not installed — `pip install yt-dlp` (it reads browser cookies).")
    browser = config.get("SURF_COOKIES_BROWSER", "chrome")
    out = os.path.join(tempfile.gettempdir(), f"surf_ck_{domain.replace('/', '_')}.txt")
    seed = domain if domain.startswith("http") else f"https://{domain}/"
    r = subprocess.run(
        ["yt-dlp", "--cookies-from-browser", browser, "--cookies", out,
         "--skip-download", "--no-warnings", seed],
        capture_output=True, text=True)
    if not os.path.exists(out):
        raise SystemExit(f"[surf] cookie export failed (browser={browser}). "
                         f"Is that browser logged in? err: {r.stderr.strip()[:200]}")
    return out


def to_browser_run(path: str, domain: str) -> list:
    key = domain.split("//")[-1].split("/")[0]
    cookies = []
    for ln in open(path, encoding="utf-8", errors="replace"):
        if not ln.strip():
            continue
        httponly = False
        if ln.startswith("#HttpOnly_"):
            httponly, ln = True, ln[10:]
        elif ln.startswith("#"):
            continue
        parts = ln.rstrip("\n").split("\t")
        if len(parts) < 7:
            continue
        dom, _flag, p, secure, expiry, name, value = parts[:7]
        if key.split(".")[-2] not in dom:  # loose domain match (airbnb in .airbnb.com.br)
            if key not in dom:
                continue
        try:
            e = int(float(expiry))
        except ValueError:
            e = -1
        if e <= 0 or e > MAXEXP:
            e = -1
        cookies.append({"name": name, "value": value, "domain": dom, "path": p or "/",
                        "secure": secure == "TRUE", "httpOnly": httponly,
                        "expires": e, "sameSite": "Lax"})
    return cookies


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    domain = sys.argv[1]
    as_json = "--json" in sys.argv[2:]
    path = export(domain)
    if as_json:
        ck = to_browser_run(path, domain)
        print(json.dumps(ck, ensure_ascii=False))
        print(f"[surf] {len(ck)} cookies for {domain}", file=sys.stderr)
    else:
        print(path)
    return 0


if __name__ == "__main__":
    try:
        import signal; signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ImportError, AttributeError, ValueError):
        pass
    raise SystemExit(main())
