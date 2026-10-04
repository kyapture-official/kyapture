const puppeteer = require('puppeteer-core');
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const OUT = 'C:/Users/LENOVO/Desktop/kyapture/docs/qa-1r5d';
const URL = 'http://localhost:3000/g/qa5dphotog/qa-5d';
const DIALOG = '[aria-labelledby="client-dialog-title"]';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const ok = (name, pass, extra = '') => { results.push({ name, pass, extra }); console.log(`${pass ? 'PASS' : 'FAIL'}  ${name} ${extra}`); };

const dj = (code) => {
  const r = spawnSync('docker', ['exec', '-i', 'kyapture-backend-1', 'python', 'manage.py', 'shell', '-c', code], { encoding: 'utf8' });
  const lines = (r.stdout || '').trim().split(/\r?\n/);
  return lines[lines.length - 1];
};
const GAL = "from apps.galleries.models import Gallery; g=Gallery.objects.get(slug='qa-5d'); ";
const setDownloads = (obj) => dj(GAL + `g.design_settings={'downloads': ${JSON.stringify(obj).replace(/true/g, 'True').replace(/false/g, 'False').replace(/null/g, 'None')}}; g.save(update_fields=['design_settings']); print('ok')`);
const lastLog = () => JSON.parse(dj("from apps.clients.models import DownloadLog, DownloadJob; from apps.galleries.models import Gallery; import json; g=Gallery.objects.get(slug='qa-5d'); l=DownloadLog.objects.order_by('-created_at').first(); print(json.dumps({'n':DownloadLog.objects.count(),'jobs':DownloadJob.objects.filter(gallery=g).count(),'filename':l.filename if l else None,'email':l.email if l else None,'res':l.resolution if l else None,'type':l.download_type if l else None}))"));
const setIds = () => JSON.parse(dj(GAL + "import json; print(json.dumps({s.name:str(s.id) for s in __import__('apps.photos.models',fromlist=['PhotoSet']).PhotoSet.objects.filter(gallery=g)}))"));

function jpegSize(file) {
  const b = fs.readFileSync(file);
  if (b[0] !== 0xff || b[1] !== 0xd8) return null;
  let i = 2;
  while (i < b.length) {
    if (b[i] !== 0xff) { i++; continue; }
    const m = b[i + 1];
    if (m >= 0xc0 && m <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(m)) return { h: b.readUInt16BE(i + 5), w: b.readUInt16BE(i + 7) };
    i += 2 + b.readUInt16BE(i + 2);
  }
  return null;
}

async function waitDownload(dir, before, timeout = 20000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    const files = fs.readdirSync(dir).filter((f) => !before.includes(f));
    if (files.length && !files.some((f) => f.endsWith('.crdownload'))) return files[0];
    await sleep(250);
  }
  return null;
}

const clickText = (page, scope, re) => page.evaluate((scope, src) => {
  const re = new RegExp(src, 'i');
  const el = [...document.querySelectorAll(`${scope} button, ${scope} label, ${scope} [role=radio]`)].find((e) => re.test(e.innerText || ''));
  if (!el) return false;
  el.click();
  return true;
}, scope, re.source);

const dialogText = (page) => page.$eval(DIALOG, (e) => e.innerText);

async function load(page) {
  await page.goto(URL, { waitUntil: 'networkidle2' });
  await page.waitForFunction(() => [...document.querySelectorAll('button')].some((b) => /^ceremony/i.test(b.innerText)), { timeout: 10000 });
  await page.evaluate(() => [...document.querySelectorAll('button')].find((b) => /^ceremony/i.test(b.innerText)).click());
  await sleep(800);
}

async function openTile(page, index, mobile) {
  await page.evaluate(() => document.querySelector('#gallery-grid')?.scrollIntoView());
  await page.waitForSelector('#gallery-grid img', { timeout: 15000 });
  const buttons = await page.$$('#gallery-grid button[aria-label="Download this photo"]');
  const btn = buttons[index];
  if (!mobile) {
    const tile = await btn.evaluateHandle((b) => b.closest('[class*="group"]') || b.parentElement);
    await tile.asElement().hover();
  }
  await btn.evaluate((b) => b.scrollIntoView({ block: 'center' }));
  await sleep(300);
  if (!mobile) {
    const tile = await btn.evaluateHandle((b) => b.closest('[class*="group"]') || b.parentElement);
    await tile.asElement().hover();
  }
  await btn.click();
  await page.waitForSelector(DIALOG, { timeout: 8000 });
  await sleep(500);
}

async function run(label, viewport, mobile, opts = {}) {
  const dir = path.resolve(`C:/Users/LENOVO/AppData/Local/Temp/claude/C--Users-LENOVO-Desktop-kyapture/da1812fa-c4dc-4b4a-bde3-072d715d336d/scratchpad/dl-${label}`);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const ctx = await browser.createBrowserContext();
  const page = await ctx.newPage();
  await page.setViewport(viewport);
  const cdp = await browser.target().createCDPSession();
  await cdp.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: dir, browserContextId: ctx.id });
  const email = `qa5d-${label}-${Date.now()}@example.com`;
  const shot = (n) => page.screenshot({ path: `${OUT}/${label}-${n}.png` });
  const pagesBefore = (await browser.pages()).length;

  await load(page);
  await openTile(page, 0, mobile);

  // ── gate (page 1 inside the modal)
  let text = (await dialogText(page)).toLowerCase();
  ok(`${label}: gate shown first with email + PIN`, text.includes('download photo') && text.includes('email') && text.includes('pin') && !!(await page.$(`${DIALOG} input[type=email]`)) && !!(await page.$(`${DIALOG} input[type=password]`)));
  ok(`${label}: gate has NEXT button`, /next/.test(text));
  await shot('1-gate');
  await page.type(`${DIALOG} input[type=email]`, email);
  await page.type(`${DIALOG} input[type=password]`, '0000');
  await clickText(page, DIALOG, /^next$/);
  await page.waitForFunction((s) => /incorrect pin/i.test(document.querySelector(s)?.innerText || ''), { timeout: 8000 }, DIALOG);
  ok(`${label}: wrong PIN rejected inline`, true);
  await shot('2-wrong-pin');
  await page.type(`${DIALOG} input[type=password]`, '4821');
  await clickText(page, DIALOG, /^next$/);
  await page.waitForFunction((s) => /photo size/i.test(document.querySelector(s)?.innerText || ''), { timeout: 8000 }, DIALOG);

  // ── DOWNLOAD PHOTO modal
  text = (await dialogText(page)).toLowerCase();
  ok(`${label}: modal has PHOTO SIZE / DOWNLOAD TO / Remember / button`, ['photo size', 'high resolution', 'web size', 'download to', 'save to my device', 'remember my selection', 'download photo'].every((t) => text.includes(t)));
  ok(`${label}: only Save to My Device offered`, !/google photos|dropbox/.test(text));
  const defaultChecked = await page.$$eval(`${DIALOG} [role=radio]`, (rs) => rs.filter((r) => r.getAttribute('aria-checked') === 'true').map((r) => r.innerText.trim()));
  ok(`${label}: High Resolution is the default`, defaultChecked.length === 1 && /high resolution/i.test(defaultChecked[0]), JSON.stringify(defaultChecked));
  ok(`${label}: Web Size states its real px`, /up to 2048 px/i.test(text));
  await shot('3-choose');

  // pick Web Size + remember, download
  await clickText(page, DIALOG, /web size/);
  await page.evaluate((s) => document.querySelector(`${s} input[type=checkbox]`).click(), DIALOG);
  await shot('4-choose-web-remember');
  let before = fs.readdirSync(dir);
  const urlBefore = page.url();
  await clickText(page, DIALOG, /^download photo$/);
  const f1 = await waitDownload(dir, before);
  ok(`${label}: direct download started (web)`, !!f1, f1);
  if (f1) {
    const size = jpegSize(path.join(dir, f1));
    ok(`${label}: web file is a JPEG at exactly 2048 px (long edge)`, size && Math.max(size.w, size.h) === 2048, JSON.stringify(size));
    ok(`${label}: filename is the real photo name`, /^(Ceremony|Party)_00\d\.jpg$/.test(f1), f1);
  }
  await page.waitForFunction((s) => !document.querySelector(s), { timeout: 5000 }, DIALOG);
  ok(`${label}: dialog closed, still on the gallery (no JSON page, no new tab)`, page.url() === urlBefore && (await browser.pages()).length === pagesBefore);
  await sleep(500);
  await shot('5-after-download');
  let log = lastLog();
  ok(`${label}: no ZIP job created`, log.jobs === 0 || opts.jobsBaseline !== undefined && log.jobs === opts.jobsBaseline, `jobs=${log.jobs}`);
  ok(`${label}: activity row = real filename + email + web`, log.filename === f1 && log.email === email && log.res === 'web' && log.type === 'photo', JSON.stringify(log));
  const stored = await page.evaluate(() => Object.entries(localStorage).filter(([k]) => k.startsWith('kyapture:photo-download:')));
  ok(`${label}: remember stored in localStorage per gallery`, stored.length === 1 && stored[0][0].endsWith(':qa5dphotog:qa-5d') && /web/.test(stored[0][1]), JSON.stringify(stored));

  // ── second photo through the lightbox: no gate, remembered selection preselected
  await page.evaluate(() => document.querySelector('#gallery-grid')?.scrollIntoView());
  const imgs = await page.$$('#gallery-grid img');
  await imgs[1].evaluate((i) => i.scrollIntoView({ block: 'center' }));
  await sleep(300);
  await imgs[1].click();
  await sleep(1200);
  await page.waitForSelector('button[aria-label="Download this photo"]:not(#gallery-grid *)', { timeout: 8000 }).catch(() => {});
  const lbBtn = await page.evaluateHandle(() => [...document.querySelectorAll('button[aria-label="Download this photo"]')].find((b) => !b.closest('#gallery-grid')));
  ok(`${label}: lightbox has a download button`, !!lbBtn.asElement());
  await lbBtn.asElement().click();
  await page.waitForSelector(DIALOG, { timeout: 8000 });
  await sleep(500);
  text = (await dialogText(page)).toLowerCase();
  ok(`${label}: no gate again this session (token remembered)`, !text.includes('your email') && !!text.match(/photo size/));
  const sel = await page.$$eval(`${DIALOG} [role=radio]`, (rs) => rs.filter((r) => r.getAttribute('aria-checked') === 'true').map((r) => r.innerText.trim()));
  const remembered = await page.$eval(`${DIALOG} input[type=checkbox]`, (c) => c.checked);
  ok(`${label}: remembered Web Size preselected + checkbox ticked`, /web size/i.test(sel[0] || '') && remembered, JSON.stringify(sel));
  await shot('6-lightbox-remembered');
  // High Resolution, untick remember
  await clickText(page, DIALOG, /high resolution/);
  await page.evaluate((s) => document.querySelector(`${s} input[type=checkbox]`).click(), DIALOG);
  before = fs.readdirSync(dir);
  await clickText(page, DIALOG, /^download photo$/);
  const f2 = await waitDownload(dir, before);
  ok(`${label}: direct download started (high resolution)`, !!f2, f2);
  if (f2) {
    const size = jpegSize(path.join(dir, f2));
    ok(`${label}: high-res file is the full-size master (3000px, not upscaled)`, size && Math.max(size.w, size.h) === 3000, JSON.stringify(size));
    ok(`${label}: filename is the real photo name`, /^(Ceremony|Party)_00\d\.jpg$/.test(f2) && f2 !== f1, f2);
  }
  await sleep(600);
  log = lastLog();
  ok(`${label}: activity row = real filename + high-res`, log.filename === f2 && log.res === 'download' && log.email === email, JSON.stringify(log));
  const cleared = await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith('kyapture:photo-download:')).length);
  ok(`${label}: unticking Remember forgets the selection`, cleared === 0);

  if (opts.rules) await rules(page, email, dir, mobile, label);
  await ctx.close();
}

async function rules(page, email, dir, mobile, label) {
  const ids = setIds();
  const shot = (n) => page.screenshot({ path: `${OUT}/${label}-${n}.png` });
  await page.keyboard.press('Escape').catch(() => {});

  // a) set switched off AFTER the page loaded
  await load(page);
  setDownloads({ sets_enabled: [ids.Party] });
  await openTile(page, 0, false);
  await sleep(300);
  let before = fs.readdirSync(dir);
  const n0 = lastLog().n;
  await clickText(page, DIALOG, /^download photo$/);
  await sleep(2500);
  let text = (await dialogText(page)).toLowerCase();
  ok(`${label}: disabled set refused inline in the modal`, /not available for download/.test(text), text.slice(-120).replace(/\n/g, ' '));
  ok(`${label}: nothing downloaded or logged, tab not navigated`, fs.readdirSync(dir).length === before.length && lastLog().n === n0 && new globalThis.URL(page.url()).pathname === '/g/qa5dphotog/qa-5d', JSON.stringify({files: fs.readdirSync(dir).length, before: before.length, n: lastLog().n, n0, url: page.url()}));
  await shot('7-rule-set-disabled');
  await page.keyboard.press('Escape');

  // b) a size switched off AFTER load: High Resolution off, remembered default is still High Res
  setDownloads({ high_res: { enabled: false }, web: { enabled: true, px: 1024 } });
  await load(page);
  await openTile(page, 0, false);
  text = (await dialogText(page)).toLowerCase();
  ok(`${label}: disabled size not offered`, !text.includes('high resolution') && text.includes('web size') && /up to 1024 px/.test(text));
  await shot('8-rule-only-web');
  await page.keyboard.press('Escape');

  // c) limit reached after load, then reload
  setDownloads({ limit_total: 1 });
  await load(page);
  setDownloads({ limit_total: 100 });
  await openTile(page, 0, false);
  setDownloads({ limit_total: 1 });
  await clickText(page, DIALOG, /^download photo$/);
  await sleep(2500);
  text = (await dialogText(page)).toLowerCase();
  ok(`${label}: limit reached mid-session refused inline`, /download limit reached\. contact/.test(text), text.slice(-100).replace(/\n/g, ' '));
  await shot('9-rule-limit-inline');
  await page.keyboard.press('Escape');
  await load(page);
  await openTile(page, 0, false);
  const disabled = await page.$eval(`${DIALOG} button[type=submit]`, (b) => b.disabled);
  text = (await dialogText(page)).toLowerCase();
  ok(`${label}: limit reached shown up front, button disabled`, disabled && /download limit reached/.test(text));
  await shot('10-rule-limit-upfront');
  setDownloads({});
}

let browser;
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', args: ['--no-sandbox'] });
  setDownloads({});
  await run('desktop', { width: 1280, height: 800 }, false, { rules: true });
  console.log('waiting 65s for the PIN throttle...');
  await sleep(65000);
  setDownloads({});
  await run('mobile', { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 }, true);
  await browser.close();
  fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 2));
  const failed = results.filter((r) => !r.pass);
  console.log(`\n${results.length - failed.length}/${results.length} passed`);
  process.exit(failed.length ? 1 : 0);
})().catch(async (e) => { console.error('QA CRASH', e); try { await browser.close(); } catch {} process.exit(2); });
