# surf · recording a narrated demo / tutorial video (mobile 9:16)

For "grava um vídeo testando", "faz um tutorial narrado", "mostra o fluxo pro
cliente". Output: 1080×1920 MP4, voice in sync with the screen. Proven on the Meu
Serralheiro Pro affiliate tutorial (8 scenes, 89 s, 3.6 MB).

Why not the built-in browser: its screenshots come back to you as images, not as
files you can stitch, and it can't run a capture loop. Why not Playwright's
`recordVideo` / CDP screencast: both record in CSS pixels, so a 1080×1920 frame
with a 432×768 viewport becomes a small recording in the corner and grey
everywhere else (that shipped once). Tell the user up front that the recording
runs headless and won't show up in their Browser pane.

## The pipeline

1. **Script the narration per scene first** (one line of speech per screen; plain,
   friendly pt-BR, no jargon). Generate TTS per scene BEFORE recording and save
   each duration — the recording holds every scene until its line ends.
   OpenAI: `POST /v1/audio/speech {model:"gpt-4o-mini-tts", voice:"ash",
   instructions:"Fale em português do Brasil, sotaque natural, tom calmo de quem
   explica um passo a passo"}`. Durations via `ffprobe -show_entries format=duration`.
2. **Record** with playwright-core (`$SD/scripts/node_modules/playwright-core`) and
   the headless shell (`~/.cache/ms-playwright/chromium_headless_shell-*/…/chrome-headless-shell`):
   - context: `viewport {432,768}`, `deviceScaleFactor 2.5`, `isMobile`, `hasTouch`,
     `locale 'pt-BR'`, `colorScheme 'light'`.
   - a loop on the CURRENT stage page: `cdp.send('Page.captureScreenshot',
     {format:'jpeg', quality:88, clip:{x:0,y:0,width:432,height:768,scale:2.5}})` →
     write frame + timestamp. **`scale` must be the DPR** — `scale:1` gives 432×768
     even with DPR 2.5. Expect ~6-14 fps; fine for a tutorial.
   - one browser context per actor (admin, seller, customer…), and a `stage`
     variable that says which one the loop films. Cutting between actors = changing
     `stage`.
   - `scene(name, fn)`: mark start, run the actions, then sleep until
     `audioDuration + 0.5 s` has passed since the start; mark end.
   - type with `pressSequentially(text, {delay: 55})` so it reads as typing.
3. **Assemble**: per scene, frames between its marks → ffmpeg concat list with
   `duration` = gap to the next frame; audio per scene padded/trimmed to the scene
   length (`adelay=200|200,apad,atrim=0:<len>`), concatenated; then
   `ffmpeg -f concat -i v.txt -f concat -i a.txt -vf fps=30,format=yuv420p -c:v libx264
   -crf 22 -c:a aac -shortest -movflags +faststart`. Before encoding, build a
   contact sheet (start+3 s and end−1.5 s of each scene, `hstack`) and LOOK at it.
4. End with a static card (`page.setContent(html)`) summarizing the steps — it
   doubles as the thumbnail. A PDF can't be filmed (the headless viewer is an
   iframe that doesn't render): show it as a card instead.

## Traps already paid for

- **Capture during navigation crashes the target** ("Target crashed",
  `ERR_ABORTED`). Pause the loop around every `goto`/`reload` and around the click
  that navigates (form submit with `window.location.assign`), and wait for the URL
  by polling `page.url()` instead of `waitForURL`.
- **Theme**: `colorScheme:'light'` isn't enough when the app keeps the theme in a
  cookie (SSR) — set that cookie with `ctx.addCookies` before the first load.
  Check `getInitialTheme`/`ThemeProvider` for the name.
- **Leftovers from failed takes show up in the next take** (two pending
  withdrawals on screen). Clean the test data before every re-run, not just at
  the end.
- **SQL from node**: use `execFileSync('bun', ['run','query',env, sql])` and
  collapse whitespace; `execSync` with a JSON-stringified multi-line SQL turns
  `\n` into literal backslashes.
- Locators with icons: `getByRole('button', {name})` may not match a button with an
  icon + text; `locator('button:has-text("…")').first()` does.
- Mobile layouts repeat elements (table hidden + cards shown): `getByText(x)` hits
  strict mode — add `.first()`.
- Test accounts: a naming convention (`probe_*@domain`) + zero-trace query at the
  end. Production DB shared with dev means every take writes real rows.
- Deliver: save to `~/Downloads/<clear-name>.mp4` and send it with the file tool.
