// 7.5-A browser QA: the staff flow (users list, search, suspend, reactivate, audit log) at desktop and 390 px,
// what a suspension does to the owner and to a visitor, and what a normal user sees.
// Runs against the Docker stack (app :3000, API :8000). Needs puppeteer-core (npm i puppeteer-core) and a
// small JPEG at QA75A_JPEG. Creates 3 accounts and 1 gallery with exact, run-specific emails and deletes ONLY
// those rows at the end (it prints them first). Audit rows are append-only and stay in the dev DB.
import puppeteer from 'puppeteer-core'
import { execSync } from 'node:child_process'
import fs from 'node:fs'

const APP = 'http://localhost:3000'
const API = 'http://localhost:8000/api/v1'
const OUT = 'C:/Users/LENOVO/Desktop/kyapture/docs/qa-7-5a'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const JPEG = process.env.QA75A_JPEG
const stamp = Date.now().toString(36)
const PW = 'Qa75a-Pass-8842!'
const E = {
  staff: `qa75a-staff-${stamp}@example.invalid`,
  owner: `qa75a-owner-${stamp}@example.invalid`,
  normal: `qa75a-normal-${stamp}@example.invalid`,
}
const SLUG = `qa75a-${stamp}`
const OWNER_NAME = `qa75aowner${stamp}`
const REASON = '<b>bold</b> chargeback & spam'

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const checks = []
const check = (name, ok, detail = '') => { checks.push({ name, ok: Boolean(ok) }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name} ${detail}`) }
const pyAll = (code) => execSync('docker exec -i kyapture-backend-1 python manage.py shell', { input: code }).toString().trim()
const py = (code) => pyAll(code).split('\n').pop()

// ---- seed (exact emails; ids printed before anything that can fail) -------------------------------------------------
const seeded = JSON.parse(py(`
import json
from django.contrib.auth import get_user_model
from apps.galleries.models import Gallery
U = get_user_model()
staff = U.objects.create_user(email='${E.staff}', username='qa75as${stamp}', password='${PW}', is_staff=True, display_name='QA Staff')
owner = U.objects.create_user(email='${E.owner}', username='${OWNER_NAME}', password='${PW}', display_name='QA Owner')
normal = U.objects.create_user(email='${E.normal}', username='qa75an${stamp}', password='${PW}', display_name='QA Normal')
g = Gallery.objects.create(photographer=owner, title='QA 75A Gallery', slug='${SLUG}', is_published=True, is_active=True, allow_download=True)
print(json.dumps({'staff': str(staff.pk), 'owner': str(owner.pk), 'normal': str(normal.pk), 'gallery': str(g.pk)}))
`))
console.log('SEEDED', JSON.stringify(seeded), E)

const jar = (setCookies) => Object.fromEntries(setCookies.map((c) => c.split(';')[0].split(/=(.*)/s).slice(0, 2)))
async function apiLogin(email) {
  const response = await fetch(`${API}/auth/login/`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Origin: APP, Referer: `${APP}/` },
    body: JSON.stringify({ email, password: PW }),
  })
  return { status: response.status, body: await response.json().catch(() => ({})), cookies: jar(response.headers.getSetCookie()) }
}
const call = (cookies, path, init = {}) => fetch(`${API}${path}`, {
  ...init,
  headers: {
    Origin: APP, Referer: `${APP}/`, 'X-CSRFToken': cookies.csrftoken || '',
    Cookie: Object.entries(cookies).map(([k, v]) => `${k}=${v}`).join('; '), ...(init.headers || {}),
  },
})

let browser
let ownerCookiesBefore
try {
  // ---- owner: a real photo through the real upload + worker, so the public gallery has media -------------------------
  const owner = await apiLogin(E.owner)
  check('owner signs in', owner.status === 200, owner.status)
  ownerCookiesBefore = owner.cookies
  const form = new FormData()
  form.append('image', new Blob([fs.readFileSync(JPEG)], { type: 'image/jpeg' }), 'qa75a.jpg')
  const upload = await call(ownerCookiesBefore, `/photos/${SLUG}/upload/`, { method: 'POST', body: form })
  check('owner uploads a photo (accepted for processing)', [200, 201, 202].includes(upload.status), upload.status)
  let publicBody = null
  for (let i = 0; i < 40; i += 1) {
    const response = await fetch(`${API}/public/${OWNER_NAME}/${SLUG}/`)
    publicBody = await response.json()
    if (publicBody.photos?.length && JSON.stringify(publicBody.photos[0]).includes('/media/')) break
    await sleep(1500)
  }
  const mediaUrls = [...new Set(JSON.stringify(publicBody.photos || []).match(/https?:\/\/[^"]+\/media\/[^"]+|\/media\/[^"]+/g) || [])]
    .map((u) => (u.startsWith('http') ? u : `http://localhost:8000${u}`))
  check('public gallery serves its media before the suspension', mediaUrls.length > 0, `${mediaUrls.length} urls`)
  const mediaBefore = await Promise.all(mediaUrls.map((u) => fetch(u).then((r) => r.status)))
  check('every public media URL answers 200 before', mediaBefore.length > 0 && mediaBefore.every((s) => s === 200), mediaBefore.join(','))

  // ---- staff in a real browser ---------------------------------------------------------------------------------------
  browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new' })
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  await page.setViewport({ width: 1280, height: 900 })
  let staffRequests = []
  page.on('request', (r) => { if (r.url().includes('/api/v1/staff/')) staffRequests.push(`${r.method()} ${r.url()}`) })

  await page.goto(`${APP}/login`, { waitUntil: 'networkidle2' })
  await page.type('#login-email', E.staff)
  await page.type('#login-password', PW)
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle2' }), page.keyboard.press('Enter')])

  const visible = (selector) => page.evaluate((s) => [...document.querySelectorAll(s)].filter((e) => e.offsetParent !== null).length, selector)
  const bodyText = () => page.evaluate(() => document.body.innerText)
  const clickText = async (selector, pattern) => {
    const ok = await page.evaluate((s, p) => {
      const el = [...document.querySelectorAll(s)].filter((e) => e.offsetParent !== null).find((e) => new RegExp(p, 'i').test(e.innerText))
      if (el) el.click()
      return Boolean(el)
    }, selector, pattern)
    if (!ok) throw new Error(`no visible ${selector} matching ${pattern}`)
  }
  const search = async (email) => {
    await page.focus('#staff-search')
    await page.$eval('#staff-search', (el) => el.select())      // headless triple-click does not select
    await page.keyboard.press('Backspace')
    if (email) await page.type('#staff-search', email)
    await page.keyboard.press('Enter')
    await sleep(1200)
  }

  await page.goto(`${APP}/dashboard/staff/users`, { waitUntil: 'networkidle2' })
  const nav = await bodyText()
  check('sidebar lists Users and Audit log for staff', /users/i.test(nav) && /audit log/i.test(nav))
  check('users list shows rows', (await visible('[data-testid=user-row]')) >= 3)
  await page.screenshot({ path: `${OUT}/desktop-users-list.png` })

  // search: one complete address only
  staffRequests = []
  await search('qa75a-owner')
  check('a fragment shows an inline error', /one complete email/i.test(await bodyText()))
  check('a fragment sends no request', staffRequests.length === 0, staffRequests.join(' | '))
  await search(E.owner)
  check('the exact address finds exactly one account', (await visible('[data-testid=user-row]')) === 1, (await bodyText()).replace(/\s+/g, ' ').slice(250, 900))
  const row = await page.evaluate(() => document.querySelector('[data-testid=user-row]').innerText)
  check('row shows email, plan, collections and Active', row.includes(E.owner) && /free/i.test(row) && /active/i.test(row), row.replace(/\s+/g, ' ').slice(0, 140))
  check('storage reads against the plan limit', /\d+(\.\d+)? (B|KB|MB) of [\d.]+ GB/.test(row), row.replace(/\s+/g, ' '))

  // own row: no suspend button
  await search(E.staff)
  const own = await page.evaluate(() => document.querySelector('[data-testid=user-row]').innerText)
  check('the staff row offers no Suspend button', /staff account/i.test(own) && !/suspend/i.test(own.replace(/status|active/gi, '')), own.replace(/\s+/g, ' ').slice(0, 100))

  // suspend: reason required, escaped on display
  await search(E.owner)
  await clickText('[data-testid=user-row] button', '^suspend$')
  await sleep(500)
  await page.screenshot({ path: `${OUT}/desktop-suspend-dialog.png` })
  staffRequests = []
  await clickText('[role=dialog] button[type=submit], dialog button[type=submit], form button[type=submit]', 'suspend account')
  await sleep(500)
  check('an empty reason is refused before any request', /enter a reason/i.test(await bodyText()) && staffRequests.length === 0)
  await page.type('#staff-reason', REASON)
  await clickText('form button[type=submit]', 'suspend account')
  await sleep(2000)
  check('success toast only after the API answered', /suspended/i.test(await bodyText()) && staffRequests.some((r) => r.includes('/suspend/')), staffRequests.join(' | '))
  const after = await page.evaluate(() => ({
    text: document.querySelector('[data-testid=user-row]').innerText,
    bold: document.querySelectorAll('[data-testid=suspension-reason] b').length,
  }))
  check('row now reads Suspended with the reason as literal text', /suspended/i.test(after.text) && after.text.includes('<b>bold</b>'), after.text.replace(/\s+/g, ' ').slice(0, 160))
  check('the reason is escaped (no <b> element)', after.bold === 0)
  await page.screenshot({ path: `${OUT}/desktop-users-suspended.png` })
  await page.setViewport({ width: 390, height: 844 })
  await sleep(500)
  await page.screenshot({ path: `${OUT}/mobile-users-suspended.png` })
  check('390px: no horizontal page scroll', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1))
  await page.setViewport({ width: 1280, height: 900 })

  // ---- what the suspension did ---------------------------------------------------------------------------------------
  const me = await call(ownerCookiesBefore, '/auth/me/')
  check('the owner\'s existing session is dead at once', me.status === 401, me.status)
  const blocked = await apiLogin(E.owner)
  check('the suspended owner cannot sign in', blocked.status === 400 && JSON.stringify(blocked.body).includes('suspended'), `${blocked.status} ${JSON.stringify(blocked.body).slice(0, 80)}`)
  const publicSuspended = await fetch(`${API}/public/${OWNER_NAME}/${SLUG}/`)
  check('the public gallery is a plain 404', publicSuspended.status === 404, publicSuspended.status)
  const visitor = await (await browser.createBrowserContext()).newPage()
  await visitor.setViewport({ width: 390, height: 844 })
  await visitor.goto(`${APP}/g/${OWNER_NAME}/${SLUG}`, { waitUntil: 'networkidle2' })
  await sleep(1000)
  const visitorText = await visitor.evaluate(() => document.body.innerText)
  check('a visitor at 390px sees no gallery', !visitorText.includes('QA 75A Gallery'), visitorText.replace(/\s+/g, ' ').slice(0, 100))
  await visitor.screenshot({ path: `${OUT}/mobile-visitor-suspended.png` })
  let gone = false
  let mediaAfter = []
  for (let i = 0; i < 30 && !gone; i += 1) {
    mediaAfter = await Promise.all(mediaUrls.map((u) => fetch(u).then((r) => r.status)))
    gone = mediaAfter.every((s) => s === 404)
    if (!gone) await sleep(2000)
  }
  check('the old public media URLs stop resolving (rotation ran)', gone, mediaAfter.join(','))

  // ---- reactivate through the UI -------------------------------------------------------------------------------------
  await clickText('[data-testid=user-row] button', '^reactivate$')
  await sleep(400)
  await page.type('#staff-reason', 'Appeal accepted')
  await clickText('form button[type=submit]', 'reactivate account')
  await sleep(2000)
  check('reactivation toast and row read Active', /reactivated/i.test(await bodyText()) && /active/i.test(await page.evaluate(() => document.querySelector('[data-testid=user-row]').innerText)))
  const publicBack = await fetch(`${API}/public/${OWNER_NAME}/${SLUG}/`)
  check('the public gallery is back (200)', publicBack.status === 200, publicBack.status)
  const backBody = await publicBack.json()
  const newUrls = [...new Set(JSON.stringify(backBody.photos || []).match(/https?:\/\/[^"]+\/media\/[^"]+|\/media\/[^"]+/g) || [])]
    .map((u) => (u.startsWith('http') ? u : `http://localhost:8000${u}`))
  const newStatuses = await Promise.all(newUrls.map((u) => fetch(u).then((r) => r.status)))
  check('the media URLs in the new payload load', newStatuses.length > 0 && newStatuses.every((s) => s === 200), newStatuses.join(','))
  await visitor.goto(`${APP}/g/${OWNER_NAME}/${SLUG}`, { waitUntil: 'networkidle2' })
  await sleep(1500)
  check('the visitor page shows the gallery again', (await visitor.evaluate(() => document.body.innerText)).includes('QA 75A Gallery'))
  await visitor.screenshot({ path: `${OUT}/mobile-visitor-reactivated.png` })
  check('the old session stays dead after reactivation', (await call(ownerCookiesBefore, '/auth/me/')).status === 401)
  await sleep(20000)
  const fresh = await apiLogin(E.owner)
  check('the owner signs in again', fresh.status === 200, fresh.status)

  // ---- audit log -----------------------------------------------------------------------------------------------------
  await page.goto(`${APP}/dashboard/staff/audit`, { waitUntil: 'networkidle2' })
  await sleep(800)
  const audit = await bodyText()
  check('audit log lists the suspension and reactivation', /suspended an account/i.test(audit) && /reactivated an account/i.test(audit) && audit.includes(E.staff) && audit.includes(E.owner))
  check('audit log shows the typed reason as text', audit.includes('<b>bold</b> chargeback & spam'))
  check('the audit page has no edit or delete control', (await page.evaluate(() => [...document.querySelectorAll('main button, main [role=button]')].map((b) => b.innerText.toLowerCase()).filter((t) => /edit|delete|remove|save/.test(t)).length)) === 0)
  await page.screenshot({ path: `${OUT}/desktop-audit.png` })
  await page.select('#audit-action', 'account.suspend')
  await sleep(1200)
  const filtered = await page.evaluate(() => [...document.querySelectorAll('[data-testid=audit-row]')].map((r) => r.innerText))
  check('the action filter narrows the log', filtered.length > 0 && filtered.every((t) => /suspended an account/i.test(t)), String(filtered.length))
  await page.setViewport({ width: 390, height: 844 })
  await sleep(500)
  await page.screenshot({ path: `${OUT}/mobile-audit.png` })
  check('390px audit: no horizontal page scroll', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1))

  // ---- a normal user -------------------------------------------------------------------------------------------------
  await sleep(40000)                                  // the login throttle is 5 a minute per address
  const ctx2 = await browser.createBrowserContext()
  const normal = await ctx2.newPage()
  await normal.setViewport({ width: 1280, height: 900 })
  let normalStaffCalls = 0
  normal.on('request', (r) => { if (r.url().includes('/api/v1/staff/')) normalStaffCalls += 1 })
  await normal.goto(`${APP}/login`, { waitUntil: 'networkidle2' })
  await normal.type('#login-email', E.normal)
  await normal.type('#login-password', PW)
  await Promise.all([normal.waitForNavigation({ waitUntil: 'networkidle2' }), normal.keyboard.press('Enter')])
  for (const path of ['/dashboard/staff/users', '/dashboard/staff/audit']) {
    await normal.goto(`${APP}${path}`, { waitUntil: 'networkidle2' })
    await sleep(600)
    check(`a normal user at ${path} sees "Staff only"`, /staff only/i.test(await normal.evaluate(() => document.body.innerText)))
  }
  check('and the page made no staff request', normalStaffCalls === 0, normalStaffCalls)
  const cookies = Object.fromEntries((await normal.cookies('http://localhost:8000')).map((c) => [c.name, c.value]))
  for (const [method, path, body] of [['GET', '/staff/users/'], ['GET', '/staff/audit/'], ['POST', `/staff/users/${seeded.owner}/suspend/`, { reason: 'x' }]]) {
    const response = await call(cookies, path, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined })
    check(`API ${method} ${path} answers 403 to a normal user`, response.status === 403, response.status)
  }
  await normal.screenshot({ path: `${OUT}/desktop-normal-user-denied.png` })
  check('the owner is still active (nothing changed by the refused call)', py(`from django.contrib.auth import get_user_model; print(get_user_model().objects.get(pk='${seeded.owner}').is_active)`) === 'True')

  // ---- the audit rows really written ----------------------------------------------------------------------------------
  const rows = py(`
import json
from apps.users.models import StaffAuditLog
rows = StaffAuditLog.objects.filter(target_id='${seeded.owner}').order_by('id')
print(json.dumps([[r.action, r.reason, bool(r.ip), r.actor_email] for r in rows]))
`)
  console.log('AUDIT ROWS', rows)
  const parsed = JSON.parse(rows)
  check('exactly one suspend and one reactivate row for the owner, with an address', parsed.filter((r) => r[0] === 'account.suspend').length === 1 && parsed.filter((r) => r[0] === 'account.reactivate').length === 1 && parsed.every((r) => r[2]))
} finally {
  if (browser) await browser.close()
  // ---- cleanup: exact rows only -----------------------------------------------------------------------------------
  const report = pyAll(`
import json, shutil
from django.contrib.auth import get_user_model
U = get_user_model()
emails = ['${E.staff}', '${E.owner}', '${E.normal}']
qs = U.objects.filter(email__in=emails)
rows = list(qs.values_list('email', flat=True))
print('ROWS_TO_DELETE', rows)
if len(rows) == 3:
    ids = [str(pk) for pk in qs.values_list('pk', flat=True)]
    qs.delete()
    for pk in ids:
        shutil.rmtree('/app/media/photographers/' + pk, ignore_errors=True)
    print(json.dumps({'deleted': len(rows)}))
else:
    print(json.dumps({'deleted': 0, 'unexpected': len(rows)}))
`)
  console.log('CLEANUP', report)
}
console.log(`SUMMARY ${checks.filter((c) => c.ok).length}/${checks.length}`)
