#!/usr/bin/env python3
"""surf · read+decrypt Chrome cookies directly (fast path, no yt-dlp).

cookies.py shells out to yt-dlp, which costs ~12s of import time just to read a
SQLite file. This does the same job in ~0.2s by decrypting the cookie values
ourselves, which matters when a script launches a browser per invocation.

Chrome on Linux/macOS encrypts cookie values with AES-128-CBC. The key is
PBKDF2(password, salt=b"saltysalt", iterations, 16) where the password comes from
the OS keyring (Linux: "Chrome Safe Storage" in gnome-keyring/kwallet; macOS:
Keychain). Values are prefixed with a version tag (v10/v11).

Falls back to the plaintext `value` column when a cookie isn't encrypted.

Usage:
  python3 chrome_cookies.py <domain> [--profile Default] [--json]
"""
from __future__ import annotations
import sys, os, json, sqlite3, shutil, tempfile, subprocess, argparse

ITERATIONS = {"v10": 1, "v11": 1}  # Linux uses 1 iteration; macOS uses 1003


def chrome_root() -> str:
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library/Application Support/Google/Chrome")
    if sys.platform == "win32":
        return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google/Chrome/User Data")
    return os.path.join(home, ".config/google-chrome")


def keyring_password() -> bytes:
    """The 'Chrome Safe Storage' secret from the OS keyring."""
    if sys.platform == "darwin":
        out = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
            capture_output=True, text=True)
        if out.returncode == 0:
            return out.stdout.strip().encode()
        return b"peanuts"
    # Linux: try secretstorage (gnome-keyring), then the documented fallback.
    try:
        import secretstorage  # type: ignore
        bus = secretstorage.dbus_init()
        for coll in secretstorage.get_all_collections(bus):
            if coll.is_locked():
                continue
            for item in coll.get_all_items():
                if item.get_label() in ("Chrome Safe Storage", "Chromium Safe Storage"):
                    return item.get_secret()
    except Exception:
        pass
    return b"peanuts"  # Chrome's fallback when no keyring is available


def decrypt(encrypted: bytes, key: bytes) -> str:
    if not encrypted:
        return ""
    tag = encrypted[:3].decode("utf8", "ignore")
    if tag not in ("v10", "v11"):
        return encrypted.decode("utf8", "ignore")
    try:
        from Crypto.Cipher import AES  # pycryptodome
    except ImportError:
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        except ImportError:
            raise SystemExit("[surf] need pycryptodome or cryptography — pip install cryptography")
        decryptor = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
        plain = decryptor.update(encrypted[3:]) + decryptor.finalize()
    else:
        plain = AES.new(key, AES.MODE_CBC, IV=b" " * 16).decrypt(encrypted[3:])
    pad = plain[-1] if plain else 0
    if 0 < pad <= 16:
        plain = plain[:-pad]
    # Chrome 130+ prefixes a 32-byte SHA256 domain hash before the value.
    text = plain.decode("utf8", "ignore")
    if len(plain) > 32 and not text.isprintable():
        text = plain[32:].decode("utf8", "ignore")
    return text


def read(domain: str, profile: str = "Default") -> list[dict]:
    from hashlib import pbkdf2_hmac
    key = pbkdf2_hmac("sha1", keyring_password(), b"saltysalt",
                      1003 if sys.platform == "darwin" else 1, 16)

    db = os.path.join(chrome_root(), profile, "Cookies")
    if not os.path.exists(db):
        raise SystemExit(f"[surf] no Cookies db at {db}")
    # Copy first: Chrome holds a write lock on the live file.
    tmp = os.path.join(tempfile.mkdtemp(prefix="surf_ck_"), "Cookies")
    shutil.copy2(db, tmp)

    con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
    # Match the domain and every subdomain (api.x.com, gist.github.com), the way
    # yt-dlp does — a session often spans more than the bare host.
    rows = con.execute(
        "select host_key,name,value,encrypted_value,path,expires_utc,is_secure,is_httponly,samesite"
        " from cookies where host_key = ? or host_key = ? or host_key like ?",
        (domain, f".{domain}", f"%.{domain}")).fetchall()
    con.close()
    shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)

    SAMESITE = {-1: "Lax", 0: "None", 1: "Lax", 2: "Strict"}
    out = []
    for host, name, val, enc, pth, exp, secure, httponly, samesite in rows:
        value = val or decrypt(enc, key)
        if not value:
            continue
        out.append({
            "name": name, "value": value, "domain": host, "path": pth or "/",
            # Chrome stores microseconds since 1601-01-01; convert to unix seconds.
            "expires": (exp / 1_000_000 - 11644473600) if exp else -1,
            "secure": bool(secure), "httpOnly": bool(httponly),
            "sameSite": SAMESITE.get(samesite, "Lax"),
        })
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--profile", default=os.environ.get("SURF_LOCAL_PROFILE", "Default"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cookies = read(a.domain, a.profile)
    print(json.dumps(cookies, indent=2) if a.json else f"{len(cookies)} cookies for {a.domain}")
