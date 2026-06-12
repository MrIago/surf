#!/usr/bin/env python3
"""surf · find real reference images for a query (for /studio etc).

Replaces the old "give the user a Google Images link and ask them to pick"
workaround: searches an image engine, returns REAL source image URLs, optionally
downloads the top K and builds a contact sheet so the model can SEE and select
the authentic ones — then feed the chosen URLs to an image model as reference.

Engines:
  bing   (default) — works via Browser Run cloud, returns full-res source URLs.
  google — better results but Browser Run hits a CAPTCHA (datacenter IP); use the
           Claude-in-Chrome extension instead for Google. (Not done here.)

Usage:
  images.py "<query>" [--n 30] [--download 6] [--out <dir>]
Prints the image URLs (and, if --download, the contact-sheet path to Read).
"""
from __future__ import annotations
import sys, os, re, json, time, subprocess, tempfile, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))


def bing_urls(query: str, n: int):
    url = "https://www.bing.com/images/search?q=" + urllib.parse.quote(query)
    out = subprocess.run([sys.executable, os.path.join(HERE, "cf.py"), "scrape", url,
                          "--selector", "a.iusc"], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"[surf] image search failed: {out.stderr.strip()[:200]}")
    data = json.loads(out.stdout)
    urls = []
    for grp in data:
        for r in grp.get("results", []):
            for a in r.get("attributes", []):
                if a["name"] == "m":
                    m = re.search(r'"murl":"(.*?)"', a["value"])
                    if m:
                        u = m.group(1).replace("\\/", "/")
                        if u not in urls:
                            urls.append(u)
    return urls[:n]


def download_sheet(urls, k, outdir):
    import shutil
    if not shutil.which("ffmpeg"):
        return None, []
    os.makedirs(outdir, exist_ok=True)
    got = []
    for u in urls:
        if len(got) >= k:
            break
        raw = os.path.join(outdir, f"cand{len(got)}.img")
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                open(raw, "wb").write(r.read())
            jpg = os.path.join(outdir, f"img_{len(got)}.jpg")
            # normalize every thumb to a uniform 320x320 so the tile montage works
            if subprocess.run(["ffmpeg", "-y", "-i", raw, "-vf",
                               "scale=320:320:force_original_aspect_ratio=decrease,pad=320:320:(ow-iw)/2:(oh-ih)/2:white",
                               jpg], capture_output=True).returncode == 0:
                got.append((u, jpg))
        except Exception:
            pass
        finally:
            if os.path.exists(raw):
                os.remove(raw)
    if not got:
        return None, []
    cols = 3
    rows = (len(got) + cols - 1) // cols
    sheet = os.path.join(outdir, "sheet.jpg")
    subprocess.run(["ffmpeg", "-y", "-pattern_type", "glob", "-i", os.path.join(outdir, "img_*.jpg"),
                    "-filter_complex", f"tile={cols}x{rows}:padding=4:color=white",
                    "-frames:v", "1", sheet], capture_output=True)
    return sheet, got


def main() -> int:
    import urllib.parse  # noqa
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    q = sys.argv[1]; a = sys.argv[2:]
    def val(k, d=None):
        return a[a.index(k) + 1] if k in a else d
    n = int(val("--n", "30"))
    urls = bing_urls(q, n)
    print(f"FOUND {len(urls)} images for: {q}")
    for i, u in enumerate(urls):
        print(f"[{i}] {u}")
    if "--download" in a:
        outdir = val("--out") or os.path.join(tempfile.gettempdir(), f"surf_img_{int(time.time())}")
        sheet, got = download_sheet(urls, int(val("--download", "6")), outdir)
        if sheet:
            print(f"\nCONTACT_SHEET: {sheet}  (Read it; cells map to img_0..img_{len(got)-1})")
            for i, (u, _) in enumerate(got):
                print(f"  cell {i} = {u}")
    return 0


if __name__ == "__main__":
    import urllib.parse  # for main
    try:
        import signal; signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ImportError, AttributeError, ValueError):
        pass
    raise SystemExit(main())
