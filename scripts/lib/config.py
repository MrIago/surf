#!/usr/bin/env python3
"""Config for /surf — read settings from env vars OR a persistent .env file.

Priority: environment variable first, then ~/.config/surf/.env, then default.
Lets a non-technical user just say "my Cloudflare token is X" and have it saved,
instead of editing shell profiles. Works on Linux, macOS, Windows (Path.home()).

Recognized settings:
  CF_ACCOUNT_ID        Cloudflare account id (for Browser Run)
  CF_API_TOKEN         Cloudflare API token with "Browser Rendering - Edit"
  GROQ_API_KEY         transcription via Groq (fast, free tier) — preferred
  OPENAI_API_KEY       transcription via OpenAI whisper-1 (fallback)
  SURF_COOKIES_BROWSER browser for cookie export, e.g. "chrome" or "chrome:Profile 1" (default chrome)
  SURF_TRANSCRIBE      auto | groq | openai | local   (default auto)

CLI:
  python3 config.py                      # show current config (secrets masked)
  python3 config.py CF_API_TOKEN=... GROQ_API_KEY=gsk_...   # set one or more
"""
from __future__ import annotations
import os, sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "surf"
CONFIG_FILE = CONFIG_DIR / ".env"
KNOWN = ["CF_ACCOUNT_ID", "CF_API_TOKEN", "GROQ_API_KEY", "OPENAI_API_KEY",
         "SURF_COOKIES_BROWSER", "SURF_TRANSCRIBE"]
SECRET = {"CF_API_TOKEN", "GROQ_API_KEY", "OPENAI_API_KEY"}


def _read_file() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    out = {}
    for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def get(name: str, default=None):
    v = os.environ.get(name)
    if v and v.strip():
        return v.strip()
    v = _read_file().get(name)
    return v.strip() if v and v.strip() else default


def require(name: str) -> str:
    v = get(name)
    if not v:
        raise SystemExit(
            f"[surf] missing {name}. Set it with:\n"
            f"  python3 {__file__} {name}=<value>\n"
            f"(CF creds: https://dash.cloudflare.com/profile/api-tokens — 'Browser Rendering - Edit')")
    return v


def set_values(pairs: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cur = _read_file(); cur.update({k: v for k, v in pairs.items() if v})
    CONFIG_FILE.write_text(
        "# /surf config — secrets, keep private\n"
        + "".join(f"{k}={v}\n" for k, v in cur.items()), encoding="utf-8")
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        pass


def _mask(k, v):
    if k in SECRET and len(v) > 8:
        return v[:4] + "…" + v[-4:]
    return v


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(f"# config: {CONFIG_FILE}{'  (exists)' if CONFIG_FILE.exists() else '  (not created)'}\n")
        any_set = False
        for k in KNOWN:
            v = get(k)
            if v:
                any_set = True
                src = "env" if os.environ.get(k) else "file"
                print(f"  {k} = {_mask(k, v)}  [{src}]")
        if not any_set:
            print("  (nothing configured yet)")
        return 0
    pairs = {}
    for a in args:
        if "=" not in a:
            print(f"skipping {a!r} (expected KEY=VALUE)", file=sys.stderr); continue
        k, _, v = a.partition("=")
        pairs[k.strip()] = v.strip()
    if pairs:
        set_values(pairs)
        print(f"[surf] saved {', '.join(pairs)} to {CONFIG_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
