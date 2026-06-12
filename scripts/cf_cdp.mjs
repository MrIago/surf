// surf · Cloudflare Browser Run — interactive driver over CDP (Playwright).
// A REAL driveable cloud browser: navigate, click, type, scroll, dismiss consent,
// spy the network (to find video/m3u8/pdf), inject your login cookies, screenshot.
// Use this when the task needs interaction or dynamic content the REST path can't reach.
//
// Requires: playwright-core (npm i -g playwright-core, or install in this scripts dir).
// Reads CF_ACCOUNT_ID / CF_API_TOKEN from ~/.config/surf/.env (via config.py) or env.
//
// Usage:
//   node cf_cdp.mjs --url <url> [opts]
// Options:
//   --cookies-domain <d>   inject your local Chrome cookies for domain d (logged-in render)
//   --ua modern            spoof a modern Chrome UA (dodges "update your browser" walls)
//   --consent              dismiss the cookie/consent banner first (recommended, always)
//   --actions '<json>'     array of steps: {do:"click",text|selector|coord}, {do:"type",text},
//                          {do:"scroll",y}, {do:"wait",ms}, {do:"press",key}, {do:"screenshot",out}
//   --capture-net <regex>  print network request URLs matching regex (find video/stream/pdf)
//   --screenshot <file>    final screenshot path (jpeg)
//   --keep-alive           leave the session alive (prints SESSION_ID for Live View)
//   --session <id>         reconnect to an existing session id instead of a new one
//
// stdout: JSON-ish lines the model reads (page title, captured net, screenshot path, session id).
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? (argv[i + 1] ?? true) : d; };
const has = (k) => argv.includes(k);

function cfg(name) {
  if (process.env[name]) return process.env[name];
  try { return execFileSync('python3', [path.join(__dirname, 'lib', 'config.py')], { encoding: 'utf8' })
    .split('\n').find(l => l.trim().startsWith(name))?.split('=')[1]?.trim()?.split('  ')[0]; }
  catch { return undefined; }
}
// config.py masks secrets, so read token straight from require helper instead:
function cfgRaw(name) {
  try { return execFileSync('python3', ['-c',
    `import sys;sys.path.insert(0,${JSON.stringify(path.join(__dirname,'lib'))});import config;print(config.get(${JSON.stringify(name)}) or '')`],
    { encoding: 'utf8' }).trim(); } catch { return ''; }
}

const ACCT = cfgRaw('CF_ACCOUNT_ID');
const TOK = cfgRaw('CF_API_TOKEN');
if (!ACCT || !TOK) { console.error('[surf] missing CF_ACCOUNT_ID/CF_API_TOKEN — set via lib/config.py'); process.exit(1); }

const url = opt('--url');
const sessionArg = opt('--session');
const ws = sessionArg
  ? `wss://api.cloudflare.com/client/v4/accounts/${ACCT}/browser-rendering/devtools/browser/${sessionArg}`
  : `wss://api.cloudflare.com/client/v4/accounts/${ACCT}/browser-rendering/devtools/browser?keep_alive=600000`;

const CONSENT = [/aceitar todos/i, /aceitar tudo/i, /accept all/i, /allow all/i, /concordo/i,
  /i agree/i, /got it/i, /entendi/i, /ok, entendi/i];

async function dismissConsent(page) {
  // Banners often appear shortly after load — retry for ~6s across roles/dialogs/langs.
  for (let attempt = 0; attempt < 4; attempt++) {
    for (const re of CONSENT) {
      for (const loc of [
        page.getByRole('button', { name: re }),
        page.locator('[role="dialog"]').getByText(re),
        page.getByText(re),
      ]) {
        try { await loc.first().click({ timeout: 1200 }); await page.waitForTimeout(500); return re.source; } catch {}
      }
    }
    await page.waitForTimeout(1200);
  }
  return null;
}

async function smoothScroll(page, toY) {
  const cur = await page.evaluate(() => window.scrollY).catch(() => 0);
  const steps = 18;
  for (let i = 1; i <= steps; i++) { await page.evaluate(v => window.scrollTo(0, v), cur + (toY - cur) * i / steps); await page.waitForTimeout(90); }
}

const out = {};
const browser = await chromium.connectOverCDP(ws, { headers: { Authorization: `Bearer ${TOK}` } });
const ctx = browser.contexts()[0] || await browser.newContext();

if (opt('--cookies-domain')) {
  try {
    const j = execFileSync('python3', [path.join(__dirname, 'cookies.py'), opt('--cookies-domain'), '--json'], { encoding: 'utf8' });
    const cookies = JSON.parse(j.split('\n').find(l => l.trim().startsWith('[')) || '[]');
    if (cookies.length) { await ctx.addCookies(cookies); out.cookies_injected = cookies.length; }
  } catch (e) { console.error('[surf] cookie inject failed:', e.message); }
}

const page = ctx.pages().find(p => url && p.url().includes(new URL(url).host)) || ctx.pages()[0] || await ctx.newPage();
await page.setViewportSize({ width: 1280, height: 900 }).catch(() => {});

if (opt('--ua') === 'modern') {
  const cdp = await ctx.newCDPSession(page);
  await cdp.send('Network.setUserAgentOverride', { userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36' });
}

const net = [];
const capRe = opt('--capture-net') ? new RegExp(opt('--capture-net'), 'i') : null;
if (capRe) {
  page.on('request', r => { if (capRe.test(r.url())) net.push(r.method() + ' ' + r.url()); });
  page.on('response', r => { if (capRe.test(r.url())) net.push('RESP ' + r.status() + ' ' + r.url()); });
}

if (url) await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 }).catch(e => { out.goto_warn = e.message.split('\n')[0]; });
if (has('--consent')) out.consent = await dismissConsent(page);
await page.waitForTimeout(1500);

for (const step of JSON.parse(opt('--actions', '[]'))) {
  try {
    if (step.do === 'click') {
      if (step.coord) await page.mouse.click(step.coord[0], step.coord[1]);
      else if (step.selector) await page.locator(step.selector).first().click({ timeout: 8000 });
      else if (step.text) await page.getByText(new RegExp(step.text, 'i')).first().click({ timeout: 8000 });
    } else if (step.do === 'type') { await page.keyboard.type(step.text, { delay: 40 }); }
    else if (step.do === 'press') { await page.keyboard.press(step.key); }
    else if (step.do === 'scroll') { await smoothScroll(page, step.y ?? 1000); }
    else if (step.do === 'wait') { await page.waitForTimeout(step.ms ?? 1500); }
    else if (step.do === 'dismiss-consent') { await dismissConsent(page); }
    else if (step.do === 'screenshot') { await page.screenshot({ path: step.out, type: 'jpeg', quality: 82 }); }
    await page.waitForTimeout(600);
  } catch (e) { console.error('[surf] step failed', JSON.stringify(step), e.message.split('\n')[0]); }
}

out.title = await page.title().catch(() => '');
out.url = page.url();
try { out.text = (await page.innerText('body')).replace(/\n{3,}/g, '\n\n').slice(0, 1500); } catch {}
if (capRe) out.network = [...new Set(net)].slice(0, 40);
if (opt('--screenshot')) { await page.screenshot({ path: opt('--screenshot'), type: 'jpeg', quality: 82 }); out.screenshot = opt('--screenshot'); }
if (has('--keep-alive')) {
  // The real reconnectable session id comes from REST: run `live_view.py --list`
  // (or create the session with live_view.py up front for a watchable session).
  out.session_id = sessionArg || 'use live_view.py --list to get the session id';
}

console.log(JSON.stringify(out, null, 2));
if (has('--keep-alive')) process.exit(0); // disconnect but leave session alive (keep_alive)
await browser.close();
