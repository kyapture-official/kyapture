// 7.5-C browser QA: Billing and the dashboard for an active, a soon-to-expire and an expired owner, then the real daily
// job (dry run first, then a real run, then a second run), then a renewal. Desktop 1280 and 390 px.
//   qa-active   Pro, ends in 20 days            -> "Expires in N days", no banner, no renew link
//   qa-soon     Pro, ends in 2 days             -> amber notice + Renew, banner on the dashboard, reminder bell + mail after the job
//   qa-expired  Pro ended 5 days ago, row still 'active' (the job never ran) -> "Expired" + Upgrade, banner, Free tile,
//               paid features refused at request time; after the job: downgraded once (audit row, bell, mail); after a renewal: Pro again
// Runs against the Docker stack (app :3000, API :8000, real Celery worker, Mailpit :8025). Needs puppeteer-core
// (npm i puppeteer-core in a scratch folder, run a COPY of this file from there). Creates 3 accounts and 1 gallery with
// exact, run-specific emails; prints them and deletes ONLY those at the end. The job's audit rows are append-only and stay.
// Safety: the real job run is made only if its --dry-run lists nobody but this run's accounts (the dev DB holds other accounts).
import puppeteer from 'puppeteer-core'
import { execSync } from 'node:child_process'
import fs from 'node:fs'

const APP = 'http://localhost:3000'
const API = 'http://localhost:8000/api/v1'
const MAIL = 'http://localhost:8025/api/v1'
const OUT = process.env.QA75C_OUT || 'C:/Users/LENOVO/Desktop/kyapture/docs/qa-7-5c'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const stamp = Date.now().toString(36)
const PW = 'Qa75c-Pass-8842!'
const E = {
  active: `qa75c-active-${stamp}@example.invalid`,
  soon: `qa75c-soon-${stamp}@example.invalid`,
  expired: `qa75c-expired-${stamp}@example.invalid`,
}
const SLUG = `qa75c-${stamp}`

fs.mkdirSync(OUT, { recursive: true })
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const checks = []
const check = (name, ok, detail = '') => { checks.push({ name, ok: Boolean(ok) }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name} ${detail}`) }
const pyAll = (code) => execSync('docker exec -i kyapture-backend-1 python manage.py shell', { input: code }).toString().trim()
const py = (code) => pyAll(code).split('\n').pop()
const manage = (...args) => execSync(`docker exec kyapture-backend-1 python manage.py ${args.join(' ')}`).toString()

const seeded = JSON.parse(py(`
import json
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.galleries.models import Gallery
from apps.subscriptions.models import SubscriptionPlan, UserSubscription
U = get_user_model()
pro = SubscriptionPlan.objects.get(key='pro')
now = timezone.now()
def make(email, tag, name, end):
    u = U.objects.create_user(email=email, username='qa75c' + tag + '${stamp}', password='${PW}', display_name=name)
    UserSubscription.objects.create(user=u, plan=pro, status='active', payment_method='manual',
                                    starts_at=end - timedelta(days=30), expires_at=end)
    u.is_active_plan = True
    u.save(update_fields=['is_active_plan'])
    return u
a = make('${E.active}', 'a', 'QA Active', now + timedelta(days=20, hours=1))
s = make('${E.soon}', 's', 'QA Soon', now + timedelta(days=2, hours=1))
x = make('${E.expired}', 'x', 'QA Expired', now - timedelta(days=5))
g = Gallery.objects.create(photographer=x, title='QA 75C Gallery', slug='${SLUG}', is_active=True,
                           design_settings={'downloads': {'high_res': {'enabled': True, 'mode': 'original'}}})
print(json.dumps({'a': str(a.pk), 's': str(s.pk), 'x': str(x.pk), 'g': str(g.pk)}))
`))
console.log('SEEDED', JSON.stringify(seeded), E)

const call = (cookies, p, init = {}) => fetch(`${API}${p}`, {
  ...init,
  headers: {
    Origin: APP, Referer: `${APP}/`, 'X-CSRFToken': cookies.csrftoken || '',
    Cookie: Object.entries(cookies).map(([k, v]) => `${k}=${v}`).join('; '), ...(init.headers || {}),
  },
})
const cookiesOf = async (page) => Object.fromEntries((await page.cookies('http://localhost:8000')).map((c) => [c.name, c.value]))
const json = (response) => response.json().catch(() => ({}))
const patchGallery = (cookies, body) => call(cookies, `/galleries/${SLUG}/`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const mailsTo = async (email) => (await (await fetch(`${MAIL}/search?query=to:${encodeURIComponent(email)}`)).json()).messages || []
const mailIds = new Set()

let browser
try {
  browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new' })
  async function signIn(email) {
    const ctx = await browser.createBrowserContext()
    const page = await ctx.newPage()
    await page.setViewport({ width: 1280, height: 900 })
    await page.goto(`${APP}/login`, { waitUntil: 'networkidle2' })
    await page.type('#login-email', email)
    await page.type('#login-password', PW)
    await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle2' }), page.keyboard.press('Enter')])
    return page
  }
  const bodyText = (page) => page.evaluate(() => document.body.innerText)
  const visible = (page, selector) => page.evaluate((s) => [...document.querySelectorAll(s)].filter((e) => e.offsetParent !== null).length, selector)
  const noHScroll = (page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)
  const open = async (page, route) => { await page.goto(`${APP}${route}`, { waitUntil: 'networkidle2' }); await sleep(600) }
  const textOf = (page, selector) => page.evaluate((s) => document.querySelector(s)?.innerText || '', selector)
  const phone = (page) => page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true })
  const desktop = (page) => page.setViewport({ width: 1280, height: 900 })
  const shot = (page, name) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true })

  const active = await signIn(E.active)
  const soon = await signIn(E.soon)
  const expired = await signIn(E.expired)
  const cA = await cookiesOf(active), cS = await cookiesOf(soon), cX = await cookiesOf(expired)

  // ===== API: the lifecycle block ================================================================================
  const subA = await json(await call(cA, '/subscriptions/my-subscription/'))
  const subS = await json(await call(cS, '/subscriptions/my-subscription/'))
  const subX0 = await json(await call(cX, '/subscriptions/my-subscription/'))
  check('API: active owner reads state active with 20-21 days left', subA.lifecycle?.state === 'active' && [20, 21].includes(subA.lifecycle.days_left), JSON.stringify(subA.lifecycle))
  check('API: soon owner reads state expiring with 2-3 days left', subS.lifecycle?.state === 'expiring' && [2, 3].includes(subS.lifecycle.days_left), JSON.stringify(subS.lifecycle))
  check('API: expired owner reads state expired', subX0.lifecycle?.state === 'expired', JSON.stringify(subX0.lifecycle))

  // ===== the expired owner: Free at request time, no job has run ======================================================
  const gate = await patchGallery(cX, { watermark_enabled: true })
  check('expired owner (job never run): watermark is refused 403 at request time', gate.status === 403, `${gate.status} ${JSON.stringify(await json(gate))}`)

  // ===== Billing + dashboard, desktop ==================================================================================
  await open(active, '/dashboard/billing')
  let t = await textOf(active, '[data-testid=billing-expiry]')
  check('Billing (active): "Expires in 20/21 days"', /expires in (20|21) days/i.test(t), t)
  check('Billing (active): no Renew/Upgrade link', (await visible(active, '[data-testid=billing-expiry-link]')) === 0)
  await shot(active, 'desktop-billing-active')
  await open(active, '/dashboard')
  check('Dashboard (active): no expiry banner', (await visible(active, '[data-testid=plan-expiry-banner]')) === 0)
  check('Dashboard (active): Current Plan tile reads Pro', /current plan\s*pro/i.test((await bodyText(active)).replace(/\n+/g, ' ')))
  await shot(active, 'desktop-home-active')

  await open(soon, '/dashboard/billing')
  t = await textOf(soon, '[data-testid=billing-expiry]')
  check('Billing (soon): "Expires in 2/3 days" with a Renew link', /expires in (2|3) days/i.test(t) && /renew/i.test(t), t)
  check('Billing (soon): the notice is the amber "expiring" state', (await soon.$eval('[data-testid=billing-expiry]', (e) => e.dataset.state)) === 'expiring')
  await shot(soon, 'desktop-billing-soon')
  await soon.click('[data-testid=billing-expiry-link]')
  await sleep(900)
  const inView = await soon.evaluate(() => { const r = document.getElementById('choose-tier').getBoundingClientRect(); return r.top >= -2 && r.top < window.innerHeight })
  check('Billing (soon): the Renew link scrolls to the plan choice', inView)
  await open(soon, '/dashboard')
  t = await textOf(soon, '[data-testid=plan-expiry-banner]')
  check('Dashboard (soon): banner says the plan expires in 2/3 days, with a Renew link to Billing',
    /plan expires in (2|3) days/i.test(t) && /renew/i.test(t), t.replace(/\s+/g, ' '))
  check('Dashboard (soon): the banner link goes to /dashboard/billing', (await soon.$eval('[data-testid=plan-expiry-link]', (e) => new URL(e.href).pathname)) === '/dashboard/billing')
  await shot(soon, 'desktop-home-soon')

  await open(expired, '/dashboard/billing')
  t = await textOf(expired, '[data-testid=billing-expiry]')
  check('Billing (expired): "Expired" with an Upgrade link', /expired/i.test(t) && /upgrade/i.test(t), t)
  check('Billing (expired): says the plan ended and the user is on Free; no Active Tier', /ended on/i.test(await bodyText(expired)) && (await visible(expired, '[data-testid=billing-active-plan]')) === 0)
  await shot(expired, 'desktop-billing-expired')
  await open(expired, '/dashboard')
  t = await textOf(expired, '[data-testid=plan-expiry-banner]')
  check('Dashboard (expired): banner says the plan has ended and the account is Free', /has ended/i.test(t) && /free plan/i.test(t) && /upgrade/i.test(t), t.replace(/\s+/g, ' '))
  check('Dashboard (expired): Current Plan tile reads Free', /current plan\s*free/i.test((await bodyText(expired)).replace(/\n+/g, ' ')))
  await shot(expired, 'desktop-home-expired')

  // ===== 390 px (the same pages) ========================================================================================
  for (const [name, page] of [['active', active], ['soon', soon], ['expired', expired]]) {
    await phone(page)
    await open(page, '/dashboard/billing')
    check(`390px Billing (${name}): no horizontal scroll`, await noHScroll(page))
    await shot(page, `mobile-billing-${name}`)
    await open(page, '/dashboard')
    check(`390px dashboard (${name}): no horizontal scroll`, await noHScroll(page))
    if (name !== 'active') check(`390px dashboard (${name}): the banner is visible and inside the screen`, await page.evaluate(() => {
      const el = document.querySelector('[data-testid=plan-expiry-banner]'); if (!el) return false
      const r = el.getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth + 1 && r.height > 0
    }))
    await shot(page, `mobile-home-${name}`)
    await desktop(page)
  }

  // ===== the real job ================================================================================================
  const dbBefore = JSON.parse(py(`
import json
from apps.subscriptions.models import UserSubscription
from apps.users.models import StaffAuditLog
row = UserSubscription.objects.get(user__email='${E.expired}')
print(json.dumps({'status': row.status, 'downgraded_for': str(row.downgraded_for), 'audit': StaffAuditLog.objects.filter(action='subscription.downgrade', target_email='${E.expired}').count()}))
`))
  check('before the job: no downgrade marker and no audit row yet (the my-subscription GET may already have flipped the status to expired: that is the lock-protected self-heal, not the job)',
    ['active', 'expired'].includes(dbBefore.status) && dbBefore.downgraded_for === 'None' && dbBefore.audit === 0, JSON.stringify(dbBefore))
  const dry = manage('run_subscription_lifecycle', '--dry-run')
  console.log(dry)
  const listed = [...dry.matchAll(/^\s+(\S+@\S+)\s/gm)].map((m) => m[1])
  const foreign = listed.filter((address) => !address.startsWith('qa75c-') || !address.includes(stamp))
  check('dry run lists this run\'s accounts (soon: reminder, expired: downgrade) and says nothing is changed',
    /DRY RUN/.test(dry) && listed.includes(E.soon) && listed.includes(E.expired) && !listed.includes(E.active), listed.join(','))
  const dbDry = JSON.parse(py(`
import json
from apps.subscriptions.models import UserSubscription
from apps.users.models import Notification, StaffAuditLog
print(json.dumps({'markers': list(UserSubscription.objects.filter(user__email__in=['${E.soon}', '${E.expired}']).values_list('reminder_notified_for', 'downgraded_for')),
                  'bells': Notification.objects.filter(user__email__in=['${E.soon}', '${E.expired}'], kind__in=['plan_expiring', 'plan_expired']).count(),
                  'audit': StaffAuditLog.objects.filter(action='subscription.downgrade', target_email='${E.expired}').count()}, default=str))
`))
  check('the dry run wrote nothing (no marker, no bell, no audit row)', dbDry.bells === 0 && dbDry.audit === 0 && dbDry.markers.every((m) => m[0] === null && m[1] === null), JSON.stringify(dbDry))
  check('no mail was sent by the dry run', (await mailsTo(E.soon)).length === 0 && (await mailsTo(E.expired)).length === 0)

  if (foreign.length) {
    check('the real run is safe (only this run\'s accounts are listed)', false, `foreign accounts listed: ${foreign.join(',')}`)
  } else {
    const real = manage('run_subscription_lifecycle')
    console.log(real)
    const afterFirst = JSON.parse(py(`
import json
from apps.subscriptions.models import UserSubscription
from apps.users.models import Notification, StaffAuditLog
x = UserSubscription.objects.get(user__email='${E.expired}')
s = UserSubscription.objects.get(user__email='${E.soon}')
print(json.dumps({'x_status': x.status, 'x_down': x.downgraded_for is not None and x.downgraded_for == x.expires_at,
                  'x_plan_flag': x.user.is_active_plan, 's_status': s.status, 's_remind': s.reminder_notified_for == s.expires_at,
                  'audit': StaffAuditLog.objects.filter(action='subscription.downgrade', target_email='${E.expired}').count(),
                  'audit_row': list(StaffAuditLog.objects.filter(action='subscription.downgrade', target_email='${E.expired}').values_list('actor_id', 'reason')),
                  'bell_x': Notification.objects.filter(user__email='${E.expired}', kind='plan_expired').count(),
                  'bell_s': Notification.objects.filter(user__email='${E.soon}', kind='plan_expiring').count(),
                  'bell_a': Notification.objects.filter(user__email='${E.active}', kind__in=['plan_expiring', 'plan_expired']).count()}, default=str))
`))
    check('the real run: expired owner moved to Free once (status expired, marker, legacy flag off, one audit row with no actor)',
      afterFirst.x_status === 'expired' && afterFirst.x_down && afterFirst.x_plan_flag === false && afterFirst.audit === 1 && afterFirst.audit_row[0][0] === null, JSON.stringify(afterFirst))
    check('the real run: the soon owner got the reminder marker but is still active; the active owner got nothing',
      afterFirst.s_status === 'active' && afterFirst.s_remind && afterFirst.bell_s === 1 && afterFirst.bell_a === 0, JSON.stringify(afterFirst))
    check('one downgrade bell for the expired owner', afterFirst.bell_x === 1)
    const mX = await mailsTo(E.expired), mS = await mailsTo(E.soon)
    for (const m of [...mX, ...mS]) mailIds.add(m.ID)
    check('one downgrade mail (expired) and one reminder mail (soon); none for the active owner',
      mX.length === 1 && mS.length === 1 && (await mailsTo(E.active)).length === 0, `${mX.length}/${mS.length}`)
    const bodyX = mX[0] ? (await (await fetch(`${MAIL}/message/${mX[0].ID}`)).json()).Text : ''
    const bodyS = mS[0] ? (await (await fetch(`${MAIL}/message/${mS[0].ID}`)).json()).Text : ''
    check('the mails name the plan, say files are kept / how to renew, and link to Billing (no token, no private path)',
      /ended/i.test(mX[0]?.Subject || '') && /nothing was deleted/i.test(bodyX) && bodyX.includes('/dashboard/billing')
      && /expires/i.test(mS[0]?.Subject || '') && bodyS.includes('/dashboard/billing')
      && !/token|photographers\/|private/i.test(bodyX + bodyS))

    manage('run_subscription_lifecycle')
    const second = JSON.parse(py(`
import json
from apps.users.models import Notification, StaffAuditLog
print(json.dumps({'audit': StaffAuditLog.objects.filter(action='subscription.downgrade', target_email='${E.expired}').count(),
                  'bells': Notification.objects.filter(user__email__in=['${E.soon}', '${E.expired}'], kind__in=['plan_expiring', 'plan_expired']).count()}))
`))
    check('a second run changes nothing: still 1 audit row, 2 bells, and no new mail', second.audit === 1 && second.bells === 2
      && (await mailsTo(E.expired)).length === 1 && (await mailsTo(E.soon)).length === 1, JSON.stringify(second))

    // the bell, over the API (the same list the UI bell shows)
    const bell = await json(await call(cX, '/notifications/'))
    const row = (bell.results || []).find((n) => n.kind === 'plan_expired')
    check('the expired owner\'s bell lists "plan ended" and links to Billing', row && /ended/i.test(row.message) && row.link === '/dashboard/billing', JSON.stringify(row))

    // after the job: still Free, Billing still says Expired, stored settings kept, nothing deleted
    await open(expired, '/dashboard/billing')
    check('Billing (expired, after the job): still "Expired" with Upgrade', /expired/i.test(await textOf(expired, '[data-testid=billing-expiry]')))
    const gate2 = await patchGallery(cX, { watermark_enabled: true })
    check('after the job: watermark still refused 403', gate2.status === 403)
    const kept = JSON.parse(py(`
import json
from apps.galleries.models import Gallery
g = Gallery.objects.get(slug='${SLUG}')
print(json.dumps({'mode': g.design_settings['downloads']['high_res']['mode'], 'active': g.is_active}))
`))
    check('the stored original-download choice and the gallery are untouched by the downgrade', kept.mode === 'original' && kept.active === true, JSON.stringify(kept))
    // ===== renewal: an upgrade restores it all ==============================================================================
    manage('grant_subscription', E.expired, '--plan', 'Pro', '--days', '30')
    await open(expired, '/dashboard/billing')
    t = await textOf(expired, '[data-testid=billing-expiry]')
    check('after a renewal: Billing says "Expires in N days" again, no banner on the dashboard', /expires in (29|30|31) days/i.test(t), t)
    await open(expired, '/dashboard')
    check('after a renewal: no expiry banner and the tile reads Pro again', (await visible(expired, '[data-testid=plan-expiry-banner]')) === 0 && /current plan\s*pro/i.test((await bodyText(expired)).replace(/\n+/g, ' ')))
    const gate3 = await patchGallery(cX, { watermark_enabled: true })
    check('after a renewal: the watermark is accepted (200) with no other change', gate3.status === 200, String(gate3.status))
    const marks = JSON.parse(py(`
import json
from apps.subscriptions.models import UserSubscription
x = UserSubscription.objects.get(user__email='${E.expired}')
print(json.dumps([x.reminder_notified_for, x.reminder_emailed_for, x.downgraded_for, x.downgrade_emailed_for], default=str))
`))
    check('a renewal cleared all four lifecycle markers', marks.every((m) => m === null), JSON.stringify(marks))
    await shot(expired, 'desktop-home-renewed')
  }
} finally {
  await browser?.close()
  // ---- cleanup: exact emails only, counted before deleting -------------------------------------------------------
  const rows = JSON.parse(py(`
import json
from django.contrib.auth import get_user_model
U = get_user_model()
emails = ['${E.active}', '${E.soon}', '${E.expired}']
qs = U.objects.filter(email__in=emails)
print(json.dumps(sorted(qs.values_list('email', flat=True))))
`))
  console.log('CLEANUP: found', rows)
  if (rows.length === 3) {
    console.log(py(`
from django.contrib.auth import get_user_model
U = get_user_model()
emails = ['${E.active}', '${E.soon}', '${E.expired}']
print(U.objects.filter(email__in=emails).delete())
`))
  } else {
    console.log('CLEANUP SKIPPED: the count does not match what this run created (3)')
  }
  for (const id of mailIds) { await fetch(`${MAIL}/messages`, { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ IDs: [id] }) }).catch(() => {}) }
  const failed = checks.filter((c) => !c.ok)
  console.log(`\n${checks.length - failed.length} / ${checks.length} checks passed`)
  if (failed.length) { console.log('FAILED:', failed.map((c) => c.name)); process.exitCode = 1 }
}
