// docs/qa-7c/qa-script.mjs - 7-C browser QA: forgot -> Mailpit link -> reset, desktop 1366 and mobile 390.
//
// Runs against the real Docker stack (app :3000, API :8000, Mailpit :8025, Celery worker).
// Needs: puppeteer-core, Chrome, and two QA accounts created beforehand (manage.py shell).
// Env: QA_EMAIL_DESKTOP, QA_EMAIL_MOBILE, QA_OLD_PASSWORD, QA_NEW_PASSWORD, QA_SHOTS (dir), CHROME (path).
// No password or token is written in this file; screenshots stay outside the repo.
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import puppeteer from 'puppeteer-core'

const APP = 'http://localhost:3000'
const API = 'http://localhost:8000/api/v1'
const MAILPIT = 'http://localhost:8025/api/v1'
const { QA_EMAIL_DESKTOP, QA_EMAIL_MOBILE, QA_OLD_PASSWORD, QA_NEW_PASSWORD } = process.env
const SHOTS = process.env.QA_SHOTS || '.'
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const LINK_RE = /(http:\/\/localhost:3000)\/reset-password#token=([A-Za-z0-9_-]+)/

const results = []
function check(name, ok, detail = '') {
  results.push({ name, ok: Boolean(ok), detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`)
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

// ── Mailpit ─────────────────────────────────────────────────────────────────
async function mails(address, subject) {
  const res = await fetch(`${MAILPIT}/search?query=${encodeURIComponent(`to:${address}`)}&limit=50`)
  const data = await res.json()
  return data.messages.filter((m) => !subject || m.Subject === subject)
}
async function message(id) {
  return (await fetch(`${MAILPIT}/message/${id}`)).json()
}
async function waitForMail(address, subject, count, timeoutMs = 20000) {
  const end = Date.now() + timeoutMs
  while (Date.now() < end) {
    const found = await mails(address, subject)
    if (found.length >= count) return found
    await sleep(500)
  }
  return mails(address, subject)
}
async function newestResetLink(address, count) {
  const found = await waitForMail(address, 'Reset your Kyapture password', count)
  if (found.length < count) return null
  const msg = await message(found[0].ID)                // newest first
  const m = msg.Text.match(LINK_RE)
  return m ? { url: m[0], host: m[1], token: m[2], html: msg.HTML } : null
}

// ── API (a second "device") ────────────────────────────────────────────────
function cookieHeader(res) {
  return res.headers.getSetCookie().map((c) => c.split(';')[0]).filter((c) => !c.endsWith('=')).join('; ')
}
async function apiLogin(email, password) {
  const res = await fetch(`${API}/auth/login/`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Origin: APP, Referer: `${APP}/login` },
    body: JSON.stringify({ email, password }),
  })
  return { status: res.status, cookies: res.status === 200 ? cookieHeader(res) : '' }
}
async function apiMe(cookies) {
  return (await fetch(`${API}/auth/me/`, { headers: { Cookie: cookies, Origin: APP } })).status
}
async function apiRefresh(cookies) {
  const csrf = (cookies.match(/csrftoken=([^;]+)/) || [])[1] || ''
  return (await fetch(`${API}/auth/token/refresh/`, {
    method: 'POST', headers: { Cookie: cookies, Origin: APP, Referer: APP, 'X-CSRFToken': csrf },
  })).status
}

// ── Page helpers ────────────────────────────────────────────────────────────
function watchRequests(page, log) {
  page.on('request', (req) => log.push({ url: req.url(), method: req.method(), body: req.postData() || '' }))
}
async function fill(page, selector, text) {
  await page.$eval(selector, (el) => { el.focus(); el.select() })
  await page.keyboard.press('Backspace')
  await page.type(selector, text)
}
async function state(page, attr) {
  return page.$eval('.auth-card__body', (el, a) => el.getAttribute(a), attr).catch(() => null)
}
async function waitState(page, attr, value, timeout = 10000) {
  await page.waitForSelector(`.auth-card__body[${attr}="${value}"]`, { timeout }).catch(() => {})
  return state(page, attr)
}
async function noOverflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
}
async function metaTags(page) {
  return page.evaluate(() => ({
    robots: document.querySelector('meta[name="robots"]')?.content || '',
    referrer: document.querySelector('meta[name="referrer"]')?.content || '',
  }))
}
async function shot(page, name) {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true })
}

function expireLinksOf(email) {
  // Exact account only (QA cleanup rule): its pending link(s) are moved into the past.
  const code = `from django.utils import timezone; from datetime import timedelta; from apps.users.models import PasswordResetToken as T; n = T.objects.filter(user__email=${JSON.stringify(email)}).update(expires_at=timezone.now() - timedelta(seconds=1)); print('expired', n)`
  return execFileSync('docker', ['exec', 'kyapture-backend-1', 'python', 'manage.py', 'shell', '-c', code]).toString().trim()
}

async function forgot(page, email) {
  await page.goto(`${APP}/forgot-password`, { waitUntil: 'networkidle0' })
  await fill(page, '#recovery-email', email)
  await page.click('button[type="submit"]')
  await waitState(page, 'data-forgot-state', 'sent')
  return page.$eval('.auth-card__sub[role="status"]', (el) => el.textContent.trim()).catch(() => '')
}

async function run() {
  fs.mkdirSync(SHOTS, { recursive: true })
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true })
  const requests = []

  // ══ DESKTOP 1366 ══════════════════════════════════════════════════════════
  const desk = await browser.createBrowserContext()
  const page = await desk.newPage()
  await page.setViewport({ width: 1366, height: 900 })
  watchRequests(page, requests)

  const device = await apiLogin(QA_EMAIL_DESKTOP, QA_OLD_PASSWORD)
  check('D0 other device signed in', device.status === 200 && (await apiMe(device.cookies)) === 200)

  await page.goto(`${APP}/forgot-password`, { waitUntil: 'networkidle0' })
  const metaForgot = await metaTags(page)
  check('D1 forgot page is noindex + no-referrer', metaForgot.robots.includes('noindex') && metaForgot.referrer === 'no-referrer', JSON.stringify(metaForgot))
  await shot(page, 'desktop-1-forgot')

  const unknownMsg = await forgot(page, `nobody-${Date.now()}@example.invalid`)
  const knownMsg = await forgot(page, QA_EMAIL_DESKTOP)
  check('D2 known and unknown address show the same message', unknownMsg && unknownMsg === knownMsg, knownMsg)
  await shot(page, 'desktop-2-sent')

  const l1 = await newestResetLink(QA_EMAIL_DESKTOP, 1)
  check('D3 email arrived in Mailpit with a fragment link on FRONTEND_URL', l1 && l1.host === APP, l1 ? l1.url.replace(l1.token, '<token>') : 'none')

  await sleep(31000)                                     // UI cooldown of "Send another link"
  await page.click('.auth-secondary-btn')
  await page.waitForSelector('.form-hint[role="status"]', { timeout: 10000 }).catch(() => {})
  const l2 = await newestResetLink(QA_EMAIL_DESKTOP, 2)
  check('D4 "Send another link" sent a second, different link', l2 && l1 && l2.token !== l1.token)

  await page.goto(l1.url, { waitUntil: 'networkidle0' })
  check('D5 the older link is dead after a newer request', (await waitState(page, 'data-reset-state', 'invalid')) === 'invalid')
  await shot(page, 'desktop-3-invalid-older-link')

  const before = requests.length
  await page.goto(l2.url, { waitUntil: 'networkidle0' })
  check('D6 the newest link opens the form', (await waitState(page, 'data-reset-state', 'form')) === 'form')
  const href = await page.evaluate(() => window.location.href)
  check('D6 token removed from the address bar', !href.includes('#') && !href.includes(l2.token), href)
  const metaReset = await metaTags(page)
  check('D6 reset page is noindex + no-referrer', metaReset.robots.includes('noindex') && metaReset.referrer === 'no-referrer')
  await shot(page, 'desktop-4-form')

  await fill(page, '#new-password', 'password123')
  await fill(page, '#new-password-confirm', 'password123')
  await page.click('button[type="submit"]')
  await page.waitForSelector('#new-password-error', { timeout: 10000 }).catch(() => {})
  const weak = await page.$eval('#new-password-error', (el) => el.textContent).catch(() => '')
  check('D7 a common password is refused with the server message', /too common/i.test(weak), weak)
  await shot(page, 'desktop-5-weak-password')

  await fill(page, '#new-password', QA_EMAIL_DESKTOP)
  await fill(page, '#new-password-confirm', QA_EMAIL_DESKTOP)
  await page.click('button[type="submit"]')
  await sleep(1500)
  const asEmail = await page.$eval('#new-password-error', (el) => el.textContent).catch(() => '')
  check('D8 the email as password is refused', /email/i.test(asEmail), asEmail)

  await fill(page, '#new-password', QA_NEW_PASSWORD)
  await fill(page, '#new-password-confirm', `${QA_NEW_PASSWORD}x`)
  await page.click('button[type="submit"]')
  const mismatch = await page.$eval('#new-password-confirm-error', (el) => el.textContent).catch(() => '')
  check('D9 mismatch is caught', /do not match/i.test(mismatch), mismatch)

  await fill(page, '#new-password-confirm', QA_NEW_PASSWORD)
  await page.click('button[type="submit"]')
  check('D10 new password accepted', (await waitState(page, 'data-reset-state', 'done')) === 'done')
  await shot(page, 'desktop-6-done')

  const resetRequests = requests.slice(before)
  const tokenInUrl = requests.some((r) => r.url.includes(l2.token) && !r.url.startsWith('http://localhost:3000/reset-password'))
  const tokenInBodies = resetRequests.filter((r) => r.body.includes(l2.token)).map((r) => new URL(r.url).pathname)
  check('D11 token never in a request URL; only in POST bodies of check/confirm', !tokenInUrl &&
    tokenInBodies.every((p) => /\/auth\/password\/reset\/(check|confirm)\/$/.test(p)), tokenInBodies.join(','))

  check('D12 other device: access cookie dead', (await apiMe(device.cookies)) === 401)
  check('D12 other device: refresh dead', (await apiRefresh(device.cookies)) === 401)

  await page.goto(l2.url, { waitUntil: 'networkidle0' })
  check('D13 a used link is dead', (await waitState(page, 'data-reset-state', 'invalid')) === 'invalid')

  const changed = await waitForMail(QA_EMAIL_DESKTOP, 'Your Kyapture password was changed', 1)
  const changedMsg = changed.length ? await message(changed[0].ID) : { Text: '', HTML: '' }
  check('D14 "password changed" email to the account', changed.length === 1 && /using a password reset link/.test(changedMsg.Text))
  check('D14 it carries no password and no token', !changedMsg.Text.includes(QA_NEW_PASSWORD) && !changedMsg.HTML.includes(l2.token))

  check('D15 old password refused', (await apiLogin(QA_EMAIL_DESKTOP, QA_OLD_PASSWORD)).status === 400)
  const fresh = await apiLogin(QA_EMAIL_DESKTOP, QA_NEW_PASSWORD)
  check('D15 new password signs in', fresh.status === 200)

  await forgot(page, QA_EMAIL_DESKTOP)
  const l3 = await newestResetLink(QA_EMAIL_DESKTOP, 3)
  console.log('      ', expireLinksOf(QA_EMAIL_DESKTOP))
  await page.goto(l3.url, { waitUntil: 'networkidle0' })
  check('D16 an expired link shows the invalid state', (await waitState(page, 'data-reset-state', 'invalid')) === 'invalid')

  const throttledMsg = await forgot(page, QA_EMAIL_DESKTOP)
  await sleep(8000)
  const resetMails = await mails(QA_EMAIL_DESKTOP, 'Reset your Kyapture password')
  check('D17 4th request in an hour: same message, no 4th email', throttledMsg === knownMsg && resetMails.length === 3,
    `${resetMails.length} reset emails`)
  await desk.close()

  // ══ MOBILE 390 ════════════════════════════════════════════════════════════
  const mob = await browser.createBrowserContext()
  const m = await mob.newPage()
  await m.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 })
  watchRequests(m, requests)

  await m.goto(`${APP}/forgot-password`, { waitUntil: 'networkidle0' })
  check('M1 forgot page fits 390', await noOverflow(m))
  await shot(m, 'mobile-1-forgot')
  const mMsg = await forgot(m, QA_EMAIL_MOBILE)
  check('M2 sent state fits 390', mMsg === knownMsg && (await noOverflow(m)))
  await shot(m, 'mobile-2-sent')

  const ml = await newestResetLink(QA_EMAIL_MOBILE, 1)
  await m.goto(ml.url, { waitUntil: 'networkidle0' })
  check('M3 link opens the form at 390, token gone from the URL',
    (await waitState(m, 'data-reset-state', 'form')) === 'form' && !(await m.evaluate(() => location.href)).includes('#'))
  check('M3 form fits 390', await noOverflow(m))
  await shot(m, 'mobile-3-form')

  await fill(m, '#new-password', '12345678')
  await fill(m, '#new-password-confirm', '12345678')
  await m.click('button[type="submit"]')
  await m.waitForSelector('#new-password-error', { timeout: 10000 }).catch(() => {})
  check('M4 a numeric password is refused at 390', /numeric|common/i.test(await m.$eval('#new-password-error', (el) => el.textContent).catch(() => '')))
  await shot(m, 'mobile-4-weak')

  await fill(m, '#new-password', QA_NEW_PASSWORD)
  await fill(m, '#new-password-confirm', QA_NEW_PASSWORD)
  await m.click('button[type="submit"]')
  check('M5 reset done at 390', (await waitState(m, 'data-reset-state', 'done')) === 'done' && (await noOverflow(m)))
  await shot(m, 'mobile-5-done')

  await m.goto(ml.url, { waitUntil: 'networkidle0' })
  check('M6 reused link is invalid at 390', (await waitState(m, 'data-reset-state', 'invalid')) === 'invalid' && (await noOverflow(m)))
  await shot(m, 'mobile-6-invalid')
  await mob.close()

  // ══ Whole run ═════════════════════════════════════════════════════════════
  const hosts = [...new Set(requests.map((r) => new URL(r.url).host))]
  check('X1 no third-party request on the forgot/reset pages', hosts.every((h) => ['localhost:3000', 'localhost:8000'].includes(h)), hosts.join(', '))

  await browser.close()
  const failed = results.filter((r) => !r.ok)
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
  process.exit(failed.length ? 1 : 0)
}

run().catch((err) => { console.error(err); process.exit(2) })
