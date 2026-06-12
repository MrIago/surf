# surf · watch, download, transcribe any video

Goal: let the model effectively "watch" a video — by reading its transcript and a
contact sheet of frames — and keep a downloaded copy.

## Decide how to get the bytes

1. **Known site / social** (YouTube, Instagram, TikTok, Vimeo, Twitter…):
   `video.py "<page-url>"` uses `yt-dlp`. Add `--cookies` for private/paid/age-gated.
2. **Direct media URL** (`.m3u8` / `.mp4`): `video.py "<media-url>"` uses `ffmpeg`.
   Add `--referer "<player-or-page-url>"` if the CDN requires it (many do).
3. **Custom embedded player** (ConverteAI, Panda, JW, etc. — common in courses):
   the stream isn't in the page HTML. Find it by spying the network, then download:
   ```bash
   node "$SD/scripts/cf_cdp.mjs" --url "<lesson-page>" --cookies-domain <site> \
        --capture-net 'm3u8|mp4|stream' --consent
   # grab the .../main.m3u8 (or video_0.m3u8) from the printed network list, then:
   python3 "$SD/scripts/video.py" "<m3u8-url>" --referer "<embed-or-page-url>" --transcribe
   ```
   Proven on a paid Cademi course (ConverteAI player → main.m3u8 → mp4 → transcript).

## Watch + understand

```bash
python3 "$SD/scripts/video.py" "<url>" --transcribe --frames 8
```
- `--transcribe` → `.txt` via Groq `whisper-large-v3-turbo` (needs `GROQ_API_KEY`),
  else OpenAI `whisper-1`, else local `faster_whisper` (GPU/CPU). Read it to know
  what's said.
- `--frames N` → extracts N frames evenly + a tiled `*_sheet.jpg`. **Read the
  contact sheet** to see the visual content across the timeline.

## Also grab the rest of a lesson page

Course pages usually also expose PDFs/materials and notes in the page text — pull
them in the same pass:
```bash
node "$SD/scripts/cf_cdp.mjs" --url "<lesson>" --cookies-domain <site> --consent \
     --capture-net 'm3u8|\.pdf'   # text (notes) + pdf links + stream all at once
```
Download signed PDF links promptly (they often carry short-lived `ts`/token query
params) with `curl -L`.

## Tips

- Block heavy resources isn't exposed here; keep clips reasonable. Long videos:
  transcription cost scales with length (Groq is fast and cheap).
- If `yt-dlp` 403s on a normal site, retry with `--cookies` (logged-in) or fall
  back to the cf_cdp network-capture route.
