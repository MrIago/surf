#!/usr/bin/env python3
"""surf · Cloudflare Browser Run — Quick Actions (REST). The fast, stateless path.

A real cloud Chromium renders the page (executes JS, clean IP) and returns the
result. Passes anti-bot fingerprint walls that a plain fetch gets 403 on.
NOTE: does NOT bypass CAPTCHA/Turnstile — for that use Live View (see live_view.py).

Its stdout IS the result. For screenshot/pdf it writes the file and prints the path.

Usage:
  cf.py markdown   <url>                      # page as clean markdown (read it)
  cf.py content    <url>                      # rendered HTML (post-JS)
  cf.py screenshot <url> [--full] [--out F]   # PNG/JPEG -> prints saved path
  cf.py json       <url> --prompt "..." [--schema '{...}']   # AI structured extract
  cf.py links      <url>                      # all links
  cf.py scrape     <url> --selector "h1" [--selector "a"]    # elements
  cf.py pdf        <url> [--out F]            # PDF -> prints saved path

Options (any action):
  --cookies <domain>   inject your logged-in cookies for <domain> (e.g. airbnb.com.br)
                       so the page renders authenticated. Uses your local Chrome.
  --wait <mode>        gotoOptions.waitUntil: domcontentloaded|load|networkidle0|networkidle2
                       (default networkidle2 — best for JS-heavy/SPA pages)
  --ua <string>        custom User-Agent (e.g. modern Chrome to dodge "update browser" walls)
"""
from __future__ import annotations
import sys, os, json, base64, time, argparse, urllib.request, urllib.error, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config  # noqa: E402

API = "https://api.cloudflare.com/client/v4/accounts/{acct}/browser-rendering/{action}"


def _cookies_for(domain: str):
    """Export the user's Chrome cookies for a domain via cookies.py -> Browser Run format."""
    import subprocess
    here = os.path.dirname(os.path.abspath(__file__))
    out = subprocess.run([sys.executable, os.path.join(here, "cookies.py"), domain, "--json"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        print(f"[surf] cookie export failed: {out.stderr.strip()}", file=sys.stderr)
        return []
    try:
        return json.loads(out.stdout)
    except Exception:
        return []


def call(action: str, body: dict, binary: bool):
    acct = config.require("CF_ACCOUNT_ID")
    tok = config.require("CF_API_TOKEN")
    url = API.format(acct=acct, action=action)
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                raw = r.read()
                if binary:
                    return raw, r.headers
                return json.loads(raw.decode()), r.headers
        except urllib.error.HTTPError as e:
            err = e.read().decode(errors="replace")
            if e.code == 429 and attempt < 2:
                time.sleep(3 * (attempt + 1)); continue
            raise SystemExit(f"[surf] HTTP {e.code}: {err[:300]}")
        except urllib.error.URLError as e:
            if attempt < 2:
                time.sleep(2); continue
            raise SystemExit(f"[surf] network error: {e}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["markdown", "content", "screenshot", "json", "links", "scrape", "pdf"])
    p.add_argument("url", nargs="?")
    p.add_argument("--prompt"); p.add_argument("--schema")
    p.add_argument("--selector", action="append", default=[])
    p.add_argument("--cookies"); p.add_argument("--wait", default="networkidle2")
    p.add_argument("--ua"); p.add_argument("--full", action="store_true")
    p.add_argument("--out")
    # screenshot framing
    p.add_argument("--device", choices=["desktop", "mobile"], default="desktop",
                   help="screenshot device preset (mobile = 390x844 @3x + mobile UA)")
    p.add_argument("--viewport", help="WxH, e.g. 1440x900 (overrides --device size)")
    p.add_argument("--scale", type=float, help="deviceScaleFactor, e.g. 3 for retina")
    p.add_argument("--element", help="CSS selector to clip the screenshot to one element")
    p.add_argument("--html-file", help="render a LOCAL html file instead of a url (preview generated pages)")
    a = p.parse_args()

    if not a.url and not a.html_file:
        raise SystemExit("[surf] need a <url> or --html-file")

    body: dict = {"gotoOptions": {"waitUntil": a.wait, "timeout": 50000}}
    if a.html_file:
        body["html"] = open(a.html_file, encoding="utf-8").read()
    else:
        body["url"] = a.url
    if a.ua:
        body["userAgent"] = a.ua
    if a.cookies:
        ck = _cookies_for(a.cookies)
        if ck:
            body["cookies"] = ck
            print(f"[surf] injected {len(ck)} cookies for {a.cookies}", file=sys.stderr)

    binary = a.action in ("screenshot", "pdf")
    if a.action == "json":
        if not a.prompt and not a.schema:
            raise SystemExit("[surf] json needs --prompt and/or --schema")
        if a.prompt:
            body["prompt"] = a.prompt
        if a.schema:
            body["response_format"] = {"type": "json_schema", "schema": json.loads(a.schema)}
    elif a.action == "scrape":
        if not a.selector:
            raise SystemExit("[surf] scrape needs --selector")
        body["elements"] = [{"selector": s} for s in a.selector]
    elif a.action == "screenshot":
        body["screenshotOptions"] = {"type": "jpeg", "quality": 82, "fullPage": a.full}
        # device / viewport
        if a.device == "mobile":
            w, h, scale = 390, 844, 3
            body["userAgent"] = a.ua or ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                                         "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
        else:
            w, h, scale = 1280, 900, 1
        if a.viewport:
            try:
                w, h = (int(x) for x in a.viewport.lower().split("x"))
            except Exception:
                raise SystemExit("[surf] --viewport must be WxH, e.g. 1440x900")
        vp = {"width": w, "height": h, "deviceScaleFactor": a.scale or scale}
        if a.device == "mobile":
            vp["isMobile"] = True; vp["hasTouch"] = True
        body["viewport"] = vp
        if a.element:
            body["selector"] = a.element  # capture just this element

    res, headers = call(a.action, body, binary)

    if binary:
        ext = "jpg" if a.action == "screenshot" else "pdf"
        out = a.out or os.path.join(tempfile.gettempdir(), f"surf_{a.action}_{int(time.time())}.{ext}")
        with open(out, "wb") as f:
            f.write(res)
        print(out)  # the model reads this path
        return 0

    if not res.get("success"):
        raise SystemExit(f"[surf] failed: {json.dumps(res.get('errors'))}")
    result = res.get("result")
    if isinstance(result, (dict, list)):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result)
    return 0


if __name__ == "__main__":
    try:
        import signal; signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ImportError, AttributeError, ValueError):
        pass
    raise SystemExit(main())
