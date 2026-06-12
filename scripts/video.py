#!/usr/bin/env python3
"""surf · download + watch + transcribe any video.

Strategy:
  1) If you pass a direct media URL (.m3u8 / .mp4) -> ffmpeg downloads it.
  2) Else (a normal page/social URL) -> yt-dlp (handles YouTube/Insta/TikTok/etc,
     with your browser cookies for private/paid content).
  3) For sites with a custom embedded player (ConverteAI, Panda, etc.), first
     capture the stream URL with:  cf_cdp.mjs --url <page> --capture-net 'm3u8|mp4'
     then pass that m3u8 here.

Then optionally: --transcribe (Groq/OpenAI/local whisper) and --frames N
(extract N frames + a contact-sheet image so the model can visually "watch").

Its stdout lists the produced file paths.

Usage:
  video.py <url-or-mediaurl> [--out F.mp4] [--cookies <domain>] [--referer URL]
           [--transcribe] [--frames 8]
"""
from __future__ import annotations
import sys, os, json, time, tempfile, subprocess, shutil, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import config  # noqa: E402

TMP = tempfile.gettempdir()


def _need(bin_):
    if not shutil.which(bin_):
        raise SystemExit(f"[surf] {bin_} not installed — please install it.")


def download(url, out, cookies, referer):
    is_media = any(url.split("?")[0].endswith(e) for e in (".m3u8", ".mp4", ".mov", ".webm"))
    if is_media:
        _need("ffmpeg")
        cmd = ["ffmpeg", "-y"]
        if referer:
            cmd += ["-headers", f"Referer: {referer}"]
        cmd += ["-i", url, "-c", "copy", out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out):
            raise SystemExit(f"[surf] ffmpeg failed: {r.stderr.strip()[-300:]}")
        return out
    # normal page -> yt-dlp
    _need("yt-dlp")
    cmd = ["yt-dlp", "-f", "mp4/best", "-o", out, "--no-warnings"]
    if cookies:
        cmd += ["--cookies-from-browser", config.get("SURF_COOKIES_BROWSER", "chrome")]
    cmd += [url]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not os.path.exists(out):
        # yt-dlp may add an extension
        base = os.path.splitext(out)[0]
        for f in os.listdir(os.path.dirname(out) or "."):
            if f.startswith(os.path.basename(base)):
                return os.path.join(os.path.dirname(out) or ".", f)
        raise SystemExit(f"[surf] yt-dlp failed: {r.stderr.strip()[-300:]}")
    return out


def transcribe(mp4):
    _need("ffmpeg")
    mp3 = mp4.rsplit(".", 1)[0] + ".mp3"
    subprocess.run(["ffmpeg", "-y", "-i", mp4, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", mp3],
                   capture_output=True)
    backend = config.get("SURF_TRANSCRIBE", "auto")
    if backend == "auto":
        backend = "groq" if config.get("GROQ_API_KEY") else ("openai" if config.get("OPENAI_API_KEY") else "local")
    txt = mp4.rsplit(".", 1)[0] + ".txt"
    if backend in ("groq", "openai"):
        key = config.require("GROQ_API_KEY" if backend == "groq" else "OPENAI_API_KEY")
        api = ("https://api.groq.com/openai/v1/audio/transcriptions" if backend == "groq"
               else "https://api.openai.com/v1/audio/transcriptions")
        model = "whisper-large-v3-turbo" if backend == "groq" else "whisper-1"
        body, ctype = _multipart({"model": model, "response_format": "text"}, ("file", mp3))
        req = urllib.request.Request(api, data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": ctype})
        with urllib.request.urlopen(req, timeout=300) as r:
            open(txt, "w", encoding="utf-8").write(r.read().decode())
    else:
        from faster_whisper import WhisperModel  # type: ignore
        model = WhisperModel("small", device="auto", compute_type="auto")
        segs, _ = model.transcribe(mp3)
        open(txt, "w", encoding="utf-8").write(" ".join(s.text for s in segs))
    return txt, backend


def _multipart(fields, filefield):
    boundary = "----surf" + str(int(time.time()))
    body = b""
    for k, v in fields.items():
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    name, path = filefield
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{os.path.basename(path)}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
    body += open(path, "rb").read() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def frames(mp4, n):
    _need("ffmpeg")
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "default=nk=1:nw=1", mp4], capture_output=True, text=True).stdout or "0")
    d = os.path.join(TMP, f"surf_frames_{int(time.time())}")
    os.makedirs(d, exist_ok=True)
    for i in range(n):
        t = dur * i / max(n - 1, 1) * 0.97
        subprocess.run(["ffmpeg", "-y", "-ss", str(t), "-i", mp4, "-frames:v", "1",
                        os.path.join(d, f"f_{i:02d}.jpg")], capture_output=True)
    cols = 4
    sheet = mp4.rsplit(".", 1)[0] + "_sheet.jpg"
    subprocess.run(["ffmpeg", "-y", "-i", os.path.join(d, "f_%02d.jpg"),
                    "-filter_complex", f"scale=320:-1,tile={cols}x{(n + cols - 1)//cols}", sheet],
                   capture_output=True)
    return sheet


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    url = sys.argv[1]
    a = sys.argv[2:]
    def val(k, d=None):
        return a[a.index(k) + 1] if k in a else d
    out = val("--out") or os.path.join(TMP, f"surf_video_{int(time.time())}.mp4")
    mp4 = download(url, out, "--cookies" in a, val("--referer"))
    print(f"VIDEO: {mp4}")
    if "--transcribe" in a:
        txt, backend = transcribe(mp4)
        print(f"TRANSCRIPT: {txt}  (via {backend})")
    if "--frames" in a:
        sheet = frames(mp4, int(val("--frames", "8")))
        print(f"CONTACT_SHEET: {sheet}")
    return 0


if __name__ == "__main__":
    try:
        import signal; signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ImportError, AttributeError, ValueError):
        pass
    raise SystemExit(main())
