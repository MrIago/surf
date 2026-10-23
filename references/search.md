# Search without a native search tool

Claude Code has `WebSearch` — use it there, none of this is needed. This file is for
everything that does NOT: OpenCode, Codex, a script, a server endpoint, or an agent
you are building that must find pages on its own. Measured 22/10/2026.

## Which engine answers which client

| Engine / URL | `curl` | Bun / Node `fetch` | Browser Run (`cf.py` / REST) |
|---|---|---|---|
| `html.duckduckgo.com/html/?q=` | ✅ results | ❌ challenge page (TLS fingerprint) | ❌ `5006 Network connection closed` |
| `lite.duckduckgo.com/lite/?q=` | ✅ | ❌ | ✅ results (~8–30 s) |
| `duckduckgo.com/?q=` (full, JS) | — | — | ✅ (heavier page) |
| `bing.com/search?q=` | — | — | ✅ |
| `search.brave.com/search?q=` | — | — | ❌ empty shell |
| Google | ❌ CAPTCHA for automation — never try to get past it | | |

So:
- **Shell available** (agent with bash, local script) → `curl` on `html.duckduckgo.com/html/` with a browser User-Agent. Fastest, free.
- **Server code** (Worker, Bun, Node) → its `fetch` gets blocked; go through Browser Run `content` on `lite.duckduckgo.com/lite/` (add `&kl=br-pt` for Brazil). Bing via Browser Run is the fallback.
- Browser Run fails now and then (`5006`, ~1 in 4 in a burst): retry once before reporting failure.

## Parsing

`html.duckduckgo.com` (curl):

```
<a class="result__a" href="//duckduckgo.com/l/?uddg=<URL-encoded target>&rut=...">Title</a>
<a class="result__snippet" href="...">Snippet</a>
```

`lite.duckduckgo.com` (Browser Run `content`):

```
<a rel="nofollow" href="//duckduckgo.com/l/?uddg=<URL-encoded target>&amp;rut=..." class="result-link">Title</a>
<td class="result-snippet">Snippet</td>
```

The real URL is the `uddg` query param of the link (decode `&amp;` first).

```bash
curl -s "https://html.duckduckgo.com/html/?q=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$Q")" -A "Mozilla/5.0" \
  | grep -o 'result__a" href="[^"]*' | sed 's/.*uddg=//; s/&amp;.*//' | python3 -c 'import sys,urllib.parse;[print(urllib.parse.unquote(l.strip())) for l in sys.stdin]' | head -8
```

## Then read the pages

Search finds the URL; reading is Browser Run `markdown` (renders JS) or plain `curl`
for static pages. Typical agent loop: search → pick 1–3 good results → read each →
answer citing the links. If the first query returns nothing, rephrase (English often
finds more for global topics).
