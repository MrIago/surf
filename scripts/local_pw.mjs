// surf · local Playwright driving a COPY of the user's real Chrome profile.
// "The extension, but as a script": native logins (cookies + localStorage +
// IndexedDB, so it survives token-in-storage sites) with zero model round-trips
// between steps — the fastest path for a logged-in multi-step task.
//
// Why a copy: Chrome locks its profile directory, so pointing Playwright at the
// live one would force the user to close their browser. We sync only the ~100MB
// of auth-bearing files into a cache dir instead, and the user keeps browsing.
//
// Two-part auth, because neither half is enough alone:
//   1. the copied profile carries localStorage/IndexedDB (unencrypted on disk) —
//      this is what keeps token-in-storage sites and WhatsApp Web logged in;
//   2. cookies are re-injected via cookies.py, because Chrome encrypts them with
//      a keyring key tied to the original profile, so the copied Cookies file is
//      unreadable to a fresh Playwright launch (verified: values decrypt to empty).
//
// Requires: playwright-core (npm i -g playwright-core, or in this scripts dir).
//
// Usage:
//   node local_pw.mjs --url <url> [opts]
//   node local_pw.mjs --sync                 # refresh the profile copy, then exit
// Options:
//   --profile <name>       Chrome profile dir name (default: SURF_LOCAL_PROFILE or "Default")
//   --sync                 force-refresh the copy before running (do this after a new login)
//   --cookies <domain>     inject decrypted cookies for this domain (needed for cookie-auth sites)
//   --headed               show the window (much better against bot detection; default headless)
//   --eval '<js>'          run JS in the page and print the JSON result — the FASTEST extractor
//   --actions '<json>'     [{do:"click",text|selector},{do:"type",selector,text},
//                          {do:"scroll",y},{do:"wait",ms},{do:"press",key},{do:"screenshot",out}]
//   --capture-net <regex>  print request URLs matching regex (find m3u8/mp4/api endpoints)
//   --consent              dismiss the cookie/consent banner first
//   --screenshot <file>    final screenshot path
//   --timeout <ms>         navigation timeout (default 45000)
//
// stdout: TITLE / EVAL / NETWORK / SCREENSHOT lines the model reads.
import { chromium } from 'playwright-core';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? (argv[i + 1] ?? true) : d; };
const has = (k) => argv.includes(k);

// ---- profile copy -----------------------------------------------------------
// Only the files that carry authentication. IndexedDB is the big one (~100MB) but
// it's what keeps WhatsApp Web / token-in-storage sites logged in, so it stays.
const AUTH_ITEMS = [
  'Cookies', 'Cookies-journal',
  'Login Data', 'Login Data-journal',
  'Local Storage', 'IndexedDB', 'Session Storage',
  'Preferences', 'Secure Preferences', 'Network',
];

function chromeRoot() {
  const home = os.homedir();
  if (process.platform === 'darwin') return path.join(home, 'Library/Application Support/Google/Chrome');
  if (process.platform === 'win32') return path.join(process.env.LOCALAPPDATA || '', 'Google/Chrome/User Data');
  return path.join(home, '.config/google-chrome');
}

function cacheRoot() {
  return path.join(os.homedir(), '.cache', 'surf', 'pw-profile');
}

function syncProfile(profileName, { force = false } = {}) {
  const src = path.join(chromeRoot(), profileName);
  if (!fs.existsSync(src)) {
    console.error(`[surf] Chrome profile not found: ${src}`);
    console.error(`[surf] available: ${fs.readdirSync(chromeRoot()).filter(d => /^(Default|Profile )/.test(d)).join(', ')}`);
    process.exit(1);
  }
  const dstRoot = cacheRoot();
  const dst = path.join(dstRoot, profileName);
  const stamp = path.join(dstRoot, `.synced-${profileName}`);

  // Re-sync when forced, missing, or older than 12h (logins drift/expire).
  const age = fs.existsSync(stamp) ? Date.now() - fs.statSync(stamp).mtimeMs : Infinity;
  if (!force && age < 12 * 3600 * 1000) return dstRoot;

  fs.mkdirSync(dst, { recursive: true });
  // "Local State" lives at the User Data root and holds the key that decrypts Cookies.
  const localState = path.join(chromeRoot(), 'Local State');
  if (fs.existsSync(localState)) fs.copyFileSync(localState, path.join(dstRoot, 'Local State'));
  for (const item of AUTH_ITEMS) {
    const s = path.join(src, item);
    if (!fs.existsSync(s)) continue;
    const d = path.join(dst, item);
    fs.rmSync(d, { recursive: true, force: true });
    fs.cpSync(s, d, { recursive: true });
  }
  fs.writeFileSync(stamp, new Date().toISOString());
  console.log(`PROFILE_SYNCED ${dst}`);
  return dstRoot;
}

// ---- consent ---------------------------------------------------------------
const CONSENT = [/aceitar todos/i, /aceitar tudo/i, /accept all/i, /allow all/i,
  /concordo/i, /i agree/i, /got it/i, /entendi/i];

async function dismissConsent(page) {
  for (let i = 0; i < 6; i++) {
    for (const rx of CONSENT) {
      for (const scope of [page, ...page.frames()]) {
        try {
          const btn = scope.getByRole('button', { name: rx }).first();
          if (await btn.isVisible({ timeout: 250 })) { await btn.click({ timeout: 1500 }); return true; }
        } catch { /* keep trying */ }
      }
    }
    await page.waitForTimeout(500);
  }
  return false;
}

// ---- main ------------------------------------------------------------------
const profileName = opt('--profile', process.env.SURF_LOCAL_PROFILE || 'Default');
const userDataDir = syncProfile(profileName, { force: has('--sync') });
if (has('--sync') && !opt('--url')) process.exit(0);

const url = opt('--url');
if (!url) { console.error('[surf] --url required (or --sync alone to refresh the copy)'); process.exit(1); }

const ctx = await chromium.launchPersistentContext(path.join(userDataDir, profileName), {
  headless: !has('--headed'),
  channel: 'chrome',           // the user's real Chrome, not bundled Chromium
  viewport: { width: 1440, height: 900 },
  args: ['--no-first-run', '--no-default-browser-check'],
});

// Cookies come from cookies.py (yt-dlp + keyring) already decrypted — the copied
// Cookies file can't be read by a fresh profile, see the header note.
const cookieDomain = opt('--cookies');
if (cookieDomain) {
  try {
    let raw;
    try {
      // Fast path: decrypt straight from Chrome's SQLite (~0.1s).
      raw = execFileSync('python3',
        [path.join(__dirname, 'lib', 'chrome_cookies.py'), cookieDomain, '--json',
         '--profile', profileName], { encoding: 'utf8' });
    } catch {
      // Fallback: yt-dlp path (~12s, but handles browsers/setups we don't).
      raw = execFileSync('python3',
        [path.join(__dirname, 'cookies.py'), cookieDomain, '--json'], { encoding: 'utf8' });
    }
    const jar = JSON.parse(raw.slice(raw.indexOf('[')));
    await ctx.addCookies(jar.map(c => ({
      name: c.name, value: c.value,
      domain: c.domain, path: c.path || '/',
      expires: c.expires && c.expires > 0 ? Math.floor(c.expires) : -1,
      httpOnly: !!c.httpOnly, secure: !!c.secure,
      sameSite: ['Strict', 'Lax', 'None'].includes(c.sameSite) ? c.sameSite : 'Lax',
    })));
    console.log(`COOKIES_INJECTED ${jar.length} for ${cookieDomain}`);
  } catch (e) {
    console.log(`COOKIES_FAIL ${String(e.message).split('\n')[0]}`);
  }
}

const page = ctx.pages()[0] || await ctx.newPage();

const netRx = opt('--capture-net') ? new RegExp(opt('--capture-net')) : null;
const captured = [];
if (netRx) page.on('request', r => { if (netRx.test(r.url())) captured.push(r.url()); });

await page.goto(url, { waitUntil: 'domcontentloaded', timeout: Number(opt('--timeout', 45000)) }).catch(e =>
  console.log(`NAV_WARN ${e.message}`));

if (has('--consent')) await dismissConsent(page);

const actions = JSON.parse(opt('--actions', '[]'));
for (const a of actions) {
  try {
    if (a.do === 'click') {
      if (a.selector) await page.click(a.selector, { timeout: 8000 });
      else if (a.text) await page.getByText(new RegExp(a.text, 'i')).first().click({ timeout: 8000 });
    } else if (a.do === 'type') {
      await page.fill(a.selector, a.text, { timeout: 8000 });
    } else if (a.do === 'scroll') {
      await page.evaluate(y => window.scrollBy(0, y), a.y ?? 1000);
    } else if (a.do === 'press') {
      await page.keyboard.press(a.key);
    } else if (a.do === 'wait') {
      await page.waitForTimeout(a.ms ?? 1000);
    } else if (a.do === 'screenshot') {
      await page.screenshot({ path: a.out, fullPage: !!a.full });
      console.log(`SCREENSHOT ${a.out}`);
    }
    await page.waitForTimeout(250);
  } catch (e) {
    console.log(`ACTION_FAIL ${JSON.stringify(a)} :: ${e.message}`);
  }
}

console.log(`TITLE ${await page.title()}`);
console.log(`URL ${page.url()}`);

// The fast path: pull structured data straight out of the DOM, no screenshot needed.
if (opt('--eval')) {
  try {
    const out = await page.evaluate(new Function(`return (${opt('--eval')})`)());
    console.log('EVAL ' + JSON.stringify(out, null, 2));
  } catch (e) {
    console.log(`EVAL_FAIL ${e.message}`);
  }
}

if (opt('--screenshot')) {
  await page.screenshot({ path: opt('--screenshot'), fullPage: has('--full') });
  console.log(`SCREENSHOT ${opt('--screenshot')}`);
}

if (netRx) console.log('NETWORK ' + JSON.stringify([...new Set(captured)], null, 2));

await ctx.close();
