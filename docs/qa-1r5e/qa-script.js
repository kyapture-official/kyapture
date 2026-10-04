// Task 1R.5-E browser QA. Gallery qa-5e: Gallery Password "gallerypass" + Download PIN 4821.
// Run from a folder that has puppeteer-core:  MSYS_NO_PATHCONV=1 node qa-script.js
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const OUT = 'C:/Users/LENOVO/Desktop/kyapture/docs/qa-1r5e';
const TMP = process.env.QA_TMP || path.resolve('dl');
const ORIGIN = process.env.QA_ORIGIN || 'http://localhost:3000';
const GAL = `${ORIGIN}/g/qa5ephotog/qa-5e`;
const PASSWORD = 'gallerypass';
const PIN = '4821';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const ok = (name, pass, extra = '') => { results.push({ name, pass, extra }); console.log(`${pass ? 'PASS' : 'FAIL'}  ${name} ${extra}`); };
const bodyText = (page) => page.evaluate(() => document.body.innerText);
const has = async (page, re) => re.test(await bodyText(page));
const waitText = (page, re, timeout = 30000) =>
  page.waitForFunction((src) => new RegExp(src, 'i').test(document.body.innerText), { timeout }, re.source).catch(async (e) => {
    await page.screenshot({ path: `${OUT}/_timeout-${Date.now()}.png` });
    console.log('TIMEOUT waiting for', re, 'page text:', JSON.stringify((await bodyText(page)).slice(0, 300)));
    throw e;
  });

async function mailFor(email) {
  for (let i = 0; i < 40; i++) {
    const list = await (await fetch('http://localhost:8025/api/v1/messages?limit=50')).json();
    const hit = (list.messages || []).find((m) => (m.To || []).some((t) => t.Address === email));
    if (hit) {
      const full = await (await fetch(`http://localhost:8025/api/v1/message/${hit.ID}`)).json();
      const link = (full.Text || '').match(/https?:\/\/\S+\/download\/file\/[0-9a-f-]+\?key=\S+/);
      return { link: link && link[0].replace(/[)>\]]+$/, ''), subject: full.Subject };
    }
    await sleep(500);
  }
  return null;
}

async function newCtx(browser, label, viewport) {
  const ctx = await browser.createBrowserContext();
  const page = await ctx.newPage();
  await page.setViewport(viewport);
  const dir = path.join(TMP, label);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const cdp = await browser.target().createCDPSession();
  await cdp.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: dir, browserContextId: ctx.id });
  return { ctx, page, dir };
}

async function waitDownload(dir, timeout = 20000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    const files = fs.readdirSync(dir);
    if (files.length && !files.some((f) => f.endsWith('.crdownload'))) return files[0];
    await sleep(250);
  }
  return null;
}

const clickButton = (page, re) => page.evaluate((src) => {
  const el = [...document.querySelectorAll('button, a')].find((e) => new RegExp(src, 'i').test(e.innerText || e.getAttribute('aria-label') || ''));
  if (!el) return false;
  el.click();
  return true;
}, re.source);

let browser;

// 1. Unlock, header Download icon (new tab), PIN + email, prepare. Returns the Page 4 URL.
async function createJobAsVisitor(label, viewport) {
  const { ctx, page } = await newCtx(browser, label, viewport);
  const email = `qa5e-${label}-${Date.now()}@example.com`;
  await page.goto(GAL, { waitUntil: 'networkidle2' });
  const gate = await page.$('input[name="gallery-password"]');
  ok(`${label}: gallery asks for the Gallery Password on entry`, !!gate);
  await page.screenshot({ path: `${OUT}/${label}-1-gallery-password-gate.png` });
  await page.type('input[name="gallery-password"]', PASSWORD);
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => [...document.querySelectorAll('button')].some((b) => /^ceremony/i.test(b.innerText)), { timeout: 20000 });
  await page.evaluate(() => [...document.querySelectorAll('button')].find((b) => /^ceremony/i.test(b.innerText)).click());
  await page.waitForSelector('button[aria-label="Download"]', { timeout: 20000 });
  await sleep(1500); // let the grid finish re-rendering before a trusted click

  const [target] = await Promise.all([
    new Promise((resolve) => browser.once('targetcreated', resolve)),
    page.click('button[aria-label="Download"]'),
  ]);
  const tab = await target.page();
  await tab.setViewport(viewport);
  await waitText(tab, /download photos|confirm|pin|email|choose/i);
  const pwAsked = await tab.$('input[name="gallery-password"]');
  ok(`${label}: header Download icon -> new tab keeps the unlock (no password prompt)`, !pwAsked);
  await tab.screenshot({ path: `${OUT}/${label}-2-newtab-pin-email-gate.png` });

  const emailInput = await tab.$('input[type="email"]');
  const pinInput = await tab.$('input[type="password"]');
  ok(`${label}: Download PIN + email still asked at download`, !!emailInput && !!pinInput);
  await emailInput.type(email);
  await pinInput.type(PIN);
  await clickButton(tab, /^next$/);
  await waitText(tab, /choose photos|start download/i);
  await tab.screenshot({ path: `${OUT}/${label}-3-choose.png` });

  const t0 = Date.now();
  await clickButton(tab, /start download/);
  await waitText(tab, /preparing your photos/);
  const sawPreparing = Date.now() - t0;
  await tab.screenshot({ path: `${OUT}/${label}-4-preparing.png` });
  await waitText(tab, /ready to download/);
  const readyAfter = Date.now() - t0;
  ok(`${label}: Preparing page visible at least ~1.5s`, readyAfter >= 1450, `(preparing seen at ${sawPreparing}ms, ready at ${readyAfter}ms)`);
  await tab.screenshot({ path: `${OUT}/${label}-5-page4-after-job.png` });
  const url = tab.url();
  ok(`${label}: job page URL carries the signed key`, /\/download\/file\/[0-9a-f-]+\?key=/.test(url));
  await ctx.close();
  return { email, url };
}

// 2. Open an emailed link in a brand-new browser context (no cookies, no storage).
async function openEmailLink(label, viewport, link) {
  const { ctx, page, dir } = await newCtx(browser, label, viewport);
  await page.goto(link, { waitUntil: 'networkidle2' });
  await waitText(page, /ready to download|expired|password|preparing/i, 20000);
  const text = await bodyText(page);
  ok(`${label}: signed link opens Page 4 with no gallery password`, /ready to download/i.test(text) && !(await page.$('input[name="gallery-password"]')), JSON.stringify(text.slice(0, 120)));
  ok(`${label}: header shows gallery title + studio`, /QA 5E WEDDING/i.test(text));
  ok(`${label}: no gallery photos / sets exposed on the page`, (await page.$$('img')).length === 0 && !/ceremony|party/i.test(text.replace(/photo-download/gi, '')));
  await page.screenshot({ path: `${OUT}/${label}-page4-from-email-fresh-browser.png` });

  await page.evaluate(() => document.querySelector('ul button').click());
  const file = await waitDownload(dir);
  const size = file ? fs.statSync(path.join(dir, file)).size : 0;
  const magic = file ? fs.readFileSync(path.join(dir, file)).subarray(0, 2).toString() : '';
  ok(`${label}: ZIP part downloads from the signed link alone`, !!file && size > 1000 && magic === 'PK', `${file} ${size} bytes`);
  await ctx.close();
}

async function forgedLink(label, viewport, link) {
  const { ctx, page } = await newCtx(browser, label, viewport);
  const forged = link.slice(0, -4) + 'abcd';
  await page.goto(forged, { waitUntil: 'networkidle2' });
  await waitText(page, /expired|ready to download|password/i, 20000);
  const text = await bodyText(page);
  ok(`${label}: forged key shows the friendly expired page`, /download expired/i.test(text) && !/ready to download/i.test(text));
  await page.screenshot({ path: `${OUT}/${label}-forged-key-expired.png` });
  await ctx.close();
}

// 3. Fresh tab on /download with no unlock: gallery password gate, then on to the download page.
async function freshDownloadEntry(label, viewport, urlPath) {
  const { ctx, page } = await newCtx(browser, label, viewport);
  await page.goto(`${GAL}${urlPath}`, { waitUntil: 'networkidle2' });
  const gate = await page.waitForSelector('input[name="gallery-password"]', { timeout: 15000 }).catch(() => null);
  ok(`${label}: no session -> gallery password gate (not a dead end)`, !!gate);
  await page.screenshot({ path: `${OUT}/${label}-gate-no-session.png` });
  await page.type('input[name="gallery-password"]', 'wrong-password');
  await page.keyboard.press('Enter');
  await waitText(page, /incorrect|invalid/i, 10000).catch(() => {});
  ok(`${label}: wrong password is refused`, await has(page, /incorrect|invalid/i));
  await page.$eval('input[name="gallery-password"]', (e) => { e.focus(); e.select(); });
  await page.type('input[name="gallery-password"]', PASSWORD);
  await page.keyboard.press('Enter');
  await waitText(page, /download|pin|email|choose/i, 15000);
  await sleep(500);
  const text = await bodyText(page);
  ok(`${label}: after the password, the page continues to the download page`, !(await page.$('input[name="gallery-password"]')) && /pin|email|choose photos|go to download page/i.test(text), JSON.stringify(text.slice(0, 100)));
  await page.screenshot({ path: `${OUT}/${label}-after-unlock-continues.png` });
  await ctx.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new', args: ['--no-sandbox'] });
  const desktop = { width: 1280, height: 800 };
  const phone = { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 };

  const made = await createJobAsVisitor('desktop', desktop);
  const mailed = await mailFor(made.email);
  ok('desktop: ready email arrived in Mailpit with a job link', !!(mailed && mailed.link), mailed && mailed.subject);
  const link = (mailed && mailed.link) || made.url;
  ok('desktop: emailed link is the same Page 4 URL the visitor saw', link.split('?')[0] === made.url.split('?')[0]);

  await openEmailLink('desktop-fresh', desktop, link);
  await openEmailLink('mobile-fresh', phone, link);
  await forgedLink('desktop-forged', desktop, link);
  await forgedLink('mobile-forged', phone, link);

  console.log('waiting 65s for the unlock/PIN throttle...');
  await sleep(65000);
  await freshDownloadEntry('desktop-newtab-no-session', desktop, '/download');
  await freshDownloadEntry('mobile-newtab-no-session', phone, '/download');
  console.log('waiting 65s for the throttle...');
  await sleep(65000);
  await freshDownloadEntry('desktop-keyless-job-page', desktop, `/download/file/${link.match(/file\/([0-9a-f-]+)/)[1]}`);

  console.log('waiting 65s for the throttle...');
  await sleep(65000);
  const mobileMade = await createJobAsVisitor('mobile', phone);
  const mobileMail = await mailFor(mobileMade.email);
  ok('mobile: ready email arrived', !!(mobileMail && mobileMail.link));

  fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 2));
  const failed = results.filter((r) => !r.pass);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  await browser.close();
  process.exit(failed.length ? 1 : 0);
})().catch(async (e) => { console.error(e); try { await browser.close(); } catch {} process.exit(2); });
