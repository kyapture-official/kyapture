// 7.5-B browser QA: a real payment end to end at desktop and 390 px.
//   payer1: submits (Pro) -> staff view the proof and APPROVE -> Pro unlocks at once -> the period is made to end -> Free again
//   payer2: tries payer1's transaction ID (refused), submits a PDF (Basic) -> staff REJECT with a reason -> plan unchanged
// Runs against the Docker stack (app :3000, API :8000, real Celery worker, Mailpit :8025). Needs puppeteer-core
// (npm i puppeteer-core in a scratch folder, run a COPY of this file from there). Creates 3 accounts, 1 gallery,
// 3 payments, a payment-instructions QR with exact, run-specific emails/ids; it prints them and deletes ONLY those at the
// end (and puts the instructions row back as it found it). Audit rows are append-only and stay in the dev DB.
import puppeteer from 'puppeteer-core'
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import zlib from 'node:zlib'

const APP = 'http://localhost:3000'
const API = 'http://localhost:8000/api/v1'
const MAIL = 'http://localhost:8025/api/v1'
const OUT = process.env.QA75B_OUT || 'C:/Users/LENOVO/Desktop/kyapture/docs/qa-7-5b'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const stamp = Date.now().toString(36)
const PW = 'Qa75b-Pass-8842!'
const E = {
  staff: `qa75b-staff-${stamp}@example.invalid`,
  payer1: `qa75b-payer1-${stamp}@example.invalid`,
  payer2: `qa75b-payer2-${stamp}@example.invalid`,
}
const SLUG = `qa75b-${stamp}`
const REF1 = `QA75B-${stamp.toUpperCase()}-A1`
const REF2 = `QA75B-${stamp.toUpperCase()}-B2`
const REF_STAFF = `QA75B-${stamp.toUpperCase()}-S3`
const REJECT_REASON = 'The amount on the receipt is wrong <b>x</b> & more'
const NOTE = 'Reviews take about a day. a < b & c'

fs.mkdirSync(OUT, { recursive: true })
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'qa75b-'))
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const checks = []
const check = (name, ok, detail = '') => { checks.push({ name, ok: Boolean(ok) }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name} ${detail}`) }
const pyAll = (code) => execSync('docker exec -i kyapture-backend-1 python manage.py shell', { input: code }).toString().trim()
const py = (code) => pyAll(code).split('\n').pop()

// ---- test files: a real PNG receipt and a real PDF ----------------------------------------------------------------------
const crcTable = new Int32Array(256).map((_, n) => { let c = n; for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c })
const crc32 = (buf) => { let c = -1; for (const byte of buf) c = crcTable[(c ^ byte) & 0xff] ^ (c >>> 8); return (c ^ -1) >>> 0 }
const chunk = (type, data) => {
  const body = Buffer.concat([Buffer.from(type), data])
  const out = Buffer.alloc(4 + body.length + 4)
  out.writeUInt32BE(data.length, 0); body.copy(out, 4); out.writeUInt32BE(crc32(body), 4 + body.length)
  return out
}
function makePng(width, height) {
  const raw = Buffer.alloc((width * 3 + 1) * height)
  for (let y = 0; y < height; y += 1) {
    raw[y * (width * 3 + 1)] = 0
    for (let x = 0; x < width; x += 1) {
      const o = y * (width * 3 + 1) + 1 + x * 3
      raw[o] = 40 + ((x * 200) / width) | 0; raw[o + 1] = 90 + ((y * 120) / height) | 0; raw[o + 2] = 120
    }
  }
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(width, 0); ihdr.writeUInt32BE(height, 4); ihdr[8] = 8; ihdr[9] = 2
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))])
}
const PNG_FILE = path.join(TMP, 'receipt.png')
const PDF_FILE = path.join(TMP, 'receipt.pdf')
const TXT_FILE = path.join(TMP, 'notes.txt')
fs.writeFileSync(PNG_FILE, makePng(480, 320))
fs.writeFileSync(PDF_FILE, '%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n')
fs.writeFileSync(TXT_FILE, 'not a receipt')

// ---- seed (exact emails; ids printed before anything that can fail) -------------------------------------------------
const seeded = JSON.parse(py(`
import io, json
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from PIL import Image
from apps.galleries.models import Gallery
from apps.subscriptions.models import PaymentInstructions
U = get_user_model()
existed = PaymentInstructions.objects.filter(pk=1).exists()
row = PaymentInstructions.load()
before = {name: getattr(row, name) for name in PaymentInstructions.LINE_FIELDS + ('note',)}
before_qr = row.qr_image.name if row.qr_image else ''
staff = U.objects.create_user(email='${E.staff}', username='qa75bs${stamp}', password='${PW}', is_staff=True, display_name='QA Staff')
p1 = U.objects.create_user(email='${E.payer1}', username='qa75bp1${stamp}', password='${PW}', display_name='QA Payer One')
p2 = U.objects.create_user(email='${E.payer2}', username='qa75bp2${stamp}', password='${PW}', display_name='QA Payer Two')
g = Gallery.objects.create(photographer=p1, title='QA 75B Gallery', slug='${SLUG}', is_active=True)
row.account_name, row.esewa_id, row.bank_name = 'Kyapture QA Studio', '9800000000', 'Nabil Bank'
row.bank_account_number, row.bank_branch, row.note = '0123456789', 'Kathmandu', ${JSON.stringify(NOTE)}
buf = io.BytesIO(); Image.new('RGB', (180, 180), (30, 90, 60)).save(buf, 'PNG')
row.qr_image.save('qr.png', ContentFile(buf.getvalue()), save=False)
row.save()
print(json.dumps({'staff': str(staff.pk), 'p1': str(p1.pk), 'p2': str(p2.pk), 'gallery': str(g.pk), 'existed': existed,
                  'before': before, 'before_qr': before_qr, 'qr': row.qr_image.name}))
`))
console.log('SEEDED', JSON.stringify(seeded), E)

const jar = (setCookies) => Object.fromEntries(setCookies.map((c) => c.split(';')[0].split(/=(.*)/s).slice(0, 2)))
const call = (cookies, p, init = {}) => fetch(`${API}${p}`, {
  ...init,
  headers: {
    Origin: APP, Referer: `${APP}/`, 'X-CSRFToken': cookies.csrftoken || '',
    Cookie: Object.entries(cookies).map(([k, v]) => `${k}=${v}`).join('; '), ...(init.headers || {}),
  },
})
const cookiesOf = async (page) => Object.fromEntries((await page.cookies('http://localhost:8000')).map((c) => [c.name, c.value]))
const json = (response) => response.json().catch(() => ({}))

const ORIGINAL = JSON.stringify({ design_settings: { downloads: { high_res: { enabled: true, mode: 'original' } } } })
const BACK = JSON.stringify({ design_settings: { downloads: { high_res: { enabled: true, mode: '3600' } } } })
const patchGallery = (cookies, body) => call(cookies, `/galleries/${SLUG}/`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body })

let browser
const proofFiles = []
const mailIds = []
try {
  browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new' })

  async function signIn(email, viewport = { width: 1280, height: 900 }) {
    const ctx = await browser.createBrowserContext()
    const page = await ctx.newPage()
    await page.setViewport(viewport)
    await page.goto(`${APP}/login`, { waitUntil: 'networkidle2' })
    await page.type('#login-email', email)
    await page.type('#login-password', PW)
    await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle2' }), page.keyboard.press('Enter')])
    return page
  }
  const visible = (page, selector) => page.evaluate((s) => [...document.querySelectorAll(s)].filter((e) => e.offsetParent !== null).length, selector)
  const bodyText = (page) => page.evaluate(() => document.body.innerText)
  const clickText = async (page, selector, pattern) => {
    const ok = await page.evaluate((s, p) => {
      const el = [...document.querySelectorAll(s)].filter((e) => e.offsetParent !== null).find((e) => new RegExp(p, 'i').test(e.innerText.trim()))
      if (el) el.click()
      return Boolean(el)
    }, selector, pattern)
    if (!ok) throw new Error(`no visible ${selector} matching ${pattern}`)
  }
  // The dev DB holds real accounts. A screenshot of a shared list hides every row that is not this run's, so no real
  // address is ever committed (only the screenshot is affected; nothing is changed on the server).
  const mask = (page, selector) => page.evaluate((s, key) => document.querySelectorAll(s).forEach((e) => { if (!e.innerText.includes(key)) e.style.display = 'none' }), selector, 'qa75b-')
  const noHScroll = (page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)
  const paymentPosts = (page) => { const seen = []; page.on('request', (r) => { if (r.method() === 'POST' && r.url().endsWith('/subscriptions/payments/')) seen.push(r.url()) }); return seen }

  // ================= payer1: a real submit =================================================================================
  const payer1 = await signIn(E.payer1)
  const posts1 = paymentPosts(payer1)
  const cookies1 = await cookiesOf(payer1)
  await payer1.goto(`${APP}/dashboard/billing`, { waitUntil: 'networkidle2' })
  check('Free account: Billing says it is on the Free tier', /free tier/i.test(await bodyText(payer1)))
  check('Original download is refused on the Free plan (before)', (await patchGallery(cookies1, ORIGINAL)).status === 403)
  await payer1.click('[data-testid=plan-card-pro]')
  await sleep(500)
  const form = await bodyText(payer1)
  check('the instructions come from the admin row (name, eSewa, bank, number, branch)',
    ['Kyapture QA Studio', '9800000000', 'Nabil Bank', '0123456789', 'Kathmandu'].every((t) => form.includes(t)))
  check('the admin note is drawn as plain text', form.includes(NOTE))
  await sleep(800)
  check('the QR is a normal image from our own storage', await payer1.evaluate(() => {
    const img = document.querySelector('[data-testid=payment-qr]')
    return Boolean(img && img.naturalWidth > 0 && img.src.includes('/media/payment_instructions/qr_'))
  }))
  await payer1.screenshot({ path: `${OUT}/desktop-billing-form.png`, fullPage: true })

  // validation happens before any request
  await clickText(payer1, '[data-testid=payment-form] button[type=submit]', 'submit transaction review')
  await sleep(400)
  const empty = await bodyText(payer1)
  check('an empty form shows the transaction ID and proof errors, and sends nothing',
    /enter the transaction id/i.test(empty) && /choose the screenshot or pdf/i.test(empty) && posts1.length === 0, posts1.length)
  await payer1.type('#payment-reference', 'ab')
  const fileInput = await payer1.$('#manual-receipt-input')
  await fileInput.uploadFile(TXT_FILE)
  await sleep(400)
  await clickText(payer1, '[data-testid=payment-form] button[type=submit]', 'submit transaction review')
  await sleep(400)
  const bad = await bodyText(payer1)
  check('a short ID and a .txt proof are refused inline, no request', /must be 4-64 characters/i.test(bad) && /png, jpeg or webp image, or a pdf/i.test(bad) && posts1.length === 0)
  await payer1.$eval('#payment-reference', (el) => { el.select() })
  await payer1.keyboard.press('Backspace')
  await payer1.type('#payment-reference', REF1)
  await fileInput.uploadFile(PNG_FILE)
  await payer1.type('#payment-notes', 'QA payment, paid by eSewa')
  await sleep(500)
  await payer1.screenshot({ path: `${OUT}/desktop-billing-filled.png`, fullPage: true })
  await clickText(payer1, '[data-testid=payment-form] button[type=submit]', 'submit transaction review')
  await sleep(2500)
  check('success toast after the API answered, one POST', /payment submitted/i.test(await bodyText(payer1)) && posts1.length === 1, posts1.length)
  check('the pending notice and the history row appear', (await visible(payer1, '[data-testid=billing-pending]')) === 1 && (await visible(payer1, '[data-testid=payment-history-row]')) === 1)
  const historyText = await payer1.evaluate(() => document.querySelector('[data-testid=payment-history-row]').innerText)
  check('history shows plan, amount, transaction ID, Pending, Attached', /pro/i.test(historyText) && historyText.includes(REF1) && /pending/i.test(historyText) && /attached|waiting for review/i.test(historyText), historyText.replace(/\s+/g, ' '))
  await payer1.screenshot({ path: `${OUT}/desktop-billing-pending.png`, fullPage: true })
  const own = await json(await call(cookies1, '/subscriptions/payments/'))
  check('the user\'s own list has no proof file or link', Array.isArray(own) && own.length === 1 && !JSON.stringify(own).includes('payment_proof') && !JSON.stringify(own).includes('payment_proofs'), JSON.stringify(own).slice(0, 120))
  check('the plan did not change by submitting', (await json(await call(cookies1, '/subscriptions/my-subscription/'))).status === 'no_subscription')
  proofFiles.push(...JSON.parse(py(`
import json
from apps.subscriptions.models import ManualPayment
print(json.dumps([p.payment_proof.name for p in ManualPayment.objects.filter(user__email='${E.payer1}')]))
`)))

  // ================= payer2: same ID refused, then a PDF ================================================================
  const payer2 = await signIn(E.payer2)
  const posts2 = paymentPosts(payer2)
  const cookies2 = await cookiesOf(payer2)
  await payer2.goto(`${APP}/dashboard/billing`, { waitUntil: 'networkidle2' })
  await payer2.click('[data-testid=plan-card-basic]')
  await sleep(400)
  const input2 = await payer2.$('#manual-receipt-input')
  await payer2.type('#payment-reference', ` ${REF1.toLowerCase()} `)
  await input2.uploadFile(PNG_FILE)
  await clickText(payer2, '[data-testid=payment-form] button[type=submit]', 'submit transaction review')
  await sleep(2500)
  const dup = await bodyText(payer2)
  check('the same transaction ID (other case, padded) is refused with a clear message', /already submitted/i.test(dup) && posts2.length === 1, dup.replace(/\s+/g, ' ').slice(0, 0))
  check('no payment row was created for payer2', py(`from apps.subscriptions.models import ManualPayment; print(ManualPayment.objects.filter(user__email='${E.payer2}').count())`) === '0')
  await payer2.screenshot({ path: `${OUT}/desktop-billing-duplicate.png`, fullPage: true })
  await payer2.$eval('#payment-reference', (el) => { el.select() })
  await payer2.keyboard.press('Backspace')
  await payer2.type('#payment-reference', REF2)
  await input2.uploadFile(PDF_FILE)
  await sleep(300)
  check('a PDF proof is accepted by the form', /receipt\.pdf/.test(await bodyText(payer2)))
  await clickText(payer2, '[data-testid=payment-form] button[type=submit]', 'submit transaction review')
  await sleep(2500)
  check('payer2\'s PDF payment is submitted', (await visible(payer2, '[data-testid=billing-pending]')) === 1 && posts2.length === 2, posts2.length)
  proofFiles.push(...JSON.parse(py(`
import json
from apps.subscriptions.models import ManualPayment
print(json.dumps([p.payment_proof.name for p in ManualPayment.objects.filter(user__email='${E.payer2}')]))
`)))

  // ================= staff: a payment of their own, then review =========================================================
  const staff = await signIn(E.staff)
  const staffCalls = []
  staff.on('request', (r) => { if (r.url().includes('/api/v1/staff/payments/')) staffCalls.push(`${r.method()} ${r.url().replace(/\?s=.*/, '?s=…')}`) })
  const staffCookies = await cookiesOf(staff)
  const selfForm = new FormData()
  const proPlanId = JSON.parse(py(`import json; from apps.subscriptions.models import SubscriptionPlan as P; p = P.objects.get(key='basic'); print(json.dumps([str(p.id), str(p.price)]))`))
  selfForm.append('plan', proPlanId[0]); selfForm.append('amount', proPlanId[1]); selfForm.append('reference', REF_STAFF)
  selfForm.append('payment_proof', new Blob([fs.readFileSync(PNG_FILE)], { type: 'image/png' }), 'own.png')
  const selfSubmit = await call(staffCookies, '/subscriptions/payments/', { method: 'POST', body: selfForm })
  check('a staff member can submit their own payment', selfSubmit.status === 201, selfSubmit.status)
  proofFiles.push(...JSON.parse(py(`
import json
from apps.subscriptions.models import ManualPayment
print(json.dumps([p.payment_proof.name for p in ManualPayment.objects.filter(user__email='${E.staff}')]))
`)))

  await staff.goto(`${APP}/dashboard/staff/payments`, { waitUntil: 'networkidle2' })
  await sleep(800)
  const queue = await bodyText(staff)
  check('the sidebar lists Payments for staff', /payments/i.test(await staff.evaluate(() => document.querySelector('nav, aside')?.innerText || '')))
  check('the queue lists the three pending payments with their transaction IDs', (await visible(staff, '[data-testid=payment-row]')) >= 3 && [REF1, REF2, REF_STAFF].every((r) => queue.includes(r)))
  const ownRow = await staff.evaluate((ref) => [...document.querySelectorAll('[data-testid=payment-row]')].filter((e) => e.offsetParent !== null).find((e) => e.innerText.includes(ref))?.innerText || '', REF_STAFF)
  check('the staff member\'s own payment shows no Approve / Reject', /your own payment/i.test(ownRow) && !/\bapprove\b|\breject\b/i.test(ownRow.replace(/your own payment/i, '')), ownRow.replace(/\s+/g, ' '))
  const ownApprove = await call(staffCookies, `/staff/payments/${JSON.parse(py(`import json; from apps.subscriptions.models import ManualPayment as M; print(json.dumps(str(M.objects.get(reference='${REF_STAFF}').pk)))`))}/approve/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
  check('and the API refuses it (403 cannot_review_own)', ownApprove.status === 403 && (await json(ownApprove)).code === 'cannot_review_own', ownApprove.status)
  await mask(staff, '[data-testid=payment-row]')
  await staff.screenshot({ path: `${OUT}/desktop-staff-queue.png`, fullPage: true })
  await staff.reload({ waitUntil: 'networkidle2' })
  await sleep(600)

  // the proof, inside the staff page
  const rowOf = (ref) => `(() => [...document.querySelectorAll('[data-testid=payment-row]')].filter((e) => e.offsetParent !== null).find((e) => e.innerText.includes('${ref}')))()`
  const clickInRow = async (ref, pattern) => {
    const ok = await staff.evaluate((r, p) => {
      const row = [...document.querySelectorAll('[data-testid=payment-row]')].filter((e) => e.offsetParent !== null).find((e) => e.innerText.includes(r))
      const button = row && [...row.querySelectorAll('button')].find((b) => new RegExp(p, 'i').test(b.innerText.trim()))
      if (button) button.click()
      return Boolean(button)
    }, ref, pattern)
    if (!ok) throw new Error(`no ${pattern} button in the row of ${ref}`)
  }
  await clickInRow(REF1, '^view proof$')
  await staff.waitForSelector('[data-testid=proof-image], [data-testid=proof-pdf-link], [role=alert]', { timeout: 15000 }).catch(() => {})
  await sleep(500)
  const proofImg = await staff.evaluate(() => { const i = document.querySelector('[data-testid=proof-image]'); return i ? { loaded: i.naturalWidth > 0, src: i.src } : null })
  if (!proofImg) console.log('PROOF MODAL TEXT:', (await staff.evaluate(() => document.querySelector('[role=dialog], dialog')?.innerText || document.body.innerText)).replace(/\s+/g, ' ').slice(0, 300), '| calls:', staffCalls.join(' | '))
  check('the proof image loads inside the staff page from a signed link', proofImg && proofImg.loaded && /\/staff\/payments\/[^/]+\/proof\/\?s=/.test(proofImg.src), proofImg ? 'loaded' : 'none')
  check('the link carries no storage path', proofImg && !proofImg.src.includes('payment_proofs') && !proofImg.src.includes('/media/'))
  await mask(staff, '[data-testid=payment-row]')
  await staff.screenshot({ path: `${OUT}/desktop-staff-proof.png` })
  const linkNow = proofImg.src
  const staffFetch = await staff.evaluate(async (u) => { const r = await fetch(u, { credentials: 'include' }); return { status: r.status, type: r.headers.get('content-type'), cache: r.headers.get('cache-control') } }, linkNow)
  const viaNode = await call(staffCookies, linkNow.replace('http://localhost:8000/api/v1', ''))      // node can read every header (CORS hides most from the page)
  check('the file answers 200 image/png with nosniff, no-store, no referrer and a locked-down CSP',
    staffFetch.status === 200 && staffFetch.type === 'image/png' && /no-store/.test(staffFetch.cache) && viaNode.headers.get('x-content-type-options') === 'nosniff'
      && viaNode.headers.get('referrer-policy') === 'no-referrer' && /default-src 'none'/.test(viaNode.headers.get('content-security-policy') || ''), JSON.stringify(staffFetch))
  check('the same link does NOT work for the payer (403)', (await call(cookies1, linkNow.replace('http://localhost:8000/api/v1', ''))).status === 403)
  check('and not without the staff sign-in (401)', (await fetch(linkNow)).status === 401)
  await clickText(staff, '[role=dialog] button, dialog button', '^close$')
  await sleep(300)
  await clickInRow(REF2, '^view proof$')
  await sleep(2000)
  const pdfLink = await staff.evaluate(() => document.querySelector('[data-testid=proof-pdf-link]')?.href || '')
  check('a PDF proof shows an Open PDF link (signed)', /\/proof\/\?s=/.test(pdfLink))
  const pdfFetch = await staff.evaluate(async (u) => { const r = await fetch(u, { credentials: 'include' }); return { status: r.status, type: r.headers.get('content-type') } }, pdfLink)
  check('the PDF is served as application/pdf', pdfFetch.status === 200 && pdfFetch.type === 'application/pdf', JSON.stringify(pdfFetch))
  await clickText(staff, '[role=dialog] button, dialog button', '^close$')
  await sleep(300)

  // ---- APPROVE payer1 (real click) ----------------------------------------------------------------------------------
  await clickInRow(REF1, '^approve$')
  await sleep(500)
  await mask(staff, '[data-testid=payment-row]')
  await staff.screenshot({ path: `${OUT}/desktop-staff-approve-dialog.png` })
  check('the approve dialog says what happens', /unlocks for them at once/i.test(await bodyText(staff)))
  await clickText(staff, 'form button[type=submit]', '^approve payment$')
  await sleep(2500)
  const afterApprove = await bodyText(staff)
  check('success toast only after the API answered, and the row left the pending list',
    /approved .*pro payment/i.test(afterApprove) && !(await staff.evaluate((r) => [...document.querySelectorAll('[data-testid=payment-row]')].some((e) => e.innerText.includes(r)), REF1)) && staffCalls.some((c) => c.includes('/approve/')), staffCalls.join(' | '))
  const p1id = JSON.parse(py(`import json; from apps.subscriptions.models import ManualPayment as M; print(json.dumps(str(M.objects.get(reference='${REF1}').pk)))`))
  const second = await json(await call(staffCookies, `/staff/payments/${p1id}/approve/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }))
  check('a second approve changes nothing and says so', second.changed === false && second.code === 'already_approved' && /nothing was changed/i.test(second.message), JSON.stringify(second).slice(0, 120))
  const reject1 = await call(staffCookies, `/staff/payments/${p1id}/reject/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason: 'too late' }) })
  check('a reject after the approve is a 409 and changes nothing', reject1.status === 409 && (await json(reject1)).code === 'already_approved', reject1.status)

  // ---- payer1: Pro unlocked at once -----------------------------------------------------------------------------------
  const sub = await json(await call(cookies1, '/subscriptions/my-subscription/'))
  check('Pro is active for 30 days: plan, status, entitlements', sub.plan?.key === 'pro' && sub.status === 'active' && sub.entitlements?.original_download === true && sub.days_remaining >= 29, `${sub.plan?.key} ${sub.status} ${sub.days_remaining}`)
  check('Original download is now accepted on the same session (was 403)', (await patchGallery(cookies1, ORIGINAL)).status === 200)
  await payer1.reload({ waitUntil: 'networkidle2' })
  await sleep(500)
  const billing1 = await bodyText(payer1)
  check('Billing shows the active tier Pro and Approved in the history', /pro/i.test(await payer1.evaluate(() => document.querySelector('[data-testid=billing-active-plan]')?.innerText || '')) && /approved/i.test(billing1) && (await visible(payer1, '[data-testid=billing-pending]')) === 0)
  await payer1.screenshot({ path: `${OUT}/desktop-billing-approved.png`, fullPage: true })
  await payer1.setViewport({ width: 390, height: 844 })
  await sleep(500)
  await payer1.screenshot({ path: `${OUT}/mobile-billing-approved.png`, fullPage: true })
  check('390px Billing: no horizontal page scroll', await noHScroll(payer1))
  await payer1.setViewport({ width: 1280, height: 900 })
  const approvalMail = await json(await fetch(`${MAIL}/search?query=${encodeURIComponent(`to:${E.payer1}`)}`))
  mailIds.push(...(approvalMail.messages || []).map((m) => m.ID))
  check('the user got the approval email', (approvalMail.messages || []).some((m) => /approved/i.test(m.Subject)), (approvalMail.messages || []).map((m) => m.Subject).join(' | '))

  // ================= REJECT payer2 (real click, reason) ===================================================================
  await staff.setViewport({ width: 390, height: 844 })
  await staff.reload({ waitUntil: 'networkidle2' })
  await sleep(800)
  check('390px staff queue: no horizontal page scroll', await noHScroll(staff))
  await mask(staff, '[data-testid=payment-row]')
  await staff.screenshot({ path: `${OUT}/mobile-staff-queue.png`, fullPage: true })
  await staff.reload({ waitUntil: 'networkidle2' })
  await sleep(600)
  await clickInRow(REF2, '^reject$')
  await sleep(500)
  staffCalls.length = 0
  await clickText(staff, 'form button[type=submit]', '^reject payment$')
  await sleep(500)
  check('an empty reason is refused before any request', /enter a reason/i.test(await bodyText(staff)) && !staffCalls.some((c) => c.includes('/reject/')))
  await staff.type('#payment-reason', REJECT_REASON)
  await mask(staff, '[data-testid=payment-row]')
  await staff.screenshot({ path: `${OUT}/mobile-staff-reject-dialog.png` })
  await clickText(staff, 'form button[type=submit]', '^reject payment$')
  await sleep(2500)
  check('reject: toast after the API, the row left the list', /rejected/i.test(await bodyText(staff)) && staffCalls.some((c) => c.includes('/reject/')))
  await staff.setViewport({ width: 1280, height: 900 })
  await staff.select('#payments-status', 'rejected')
  await sleep(1500)
  const rejectedRow = await staff.evaluate((r) => { const row = [...document.querySelectorAll('[data-testid=payment-row]')].filter((e) => e.offsetParent !== null).find((e) => e.innerText.includes(r)); return row ? { text: row.innerText, bold: row.querySelectorAll('b').length } : null }, REF2)
  check('the staff history shows the reason as literal text (no <b> element)', rejectedRow && rejectedRow.text.includes('<b>x</b> & more') && rejectedRow.bold === 0, rejectedRow?.text.replace(/\s+/g, ' ').slice(0, 120))
  await mask(staff, '[data-testid=payment-row]')
  await staff.screenshot({ path: `${OUT}/desktop-staff-rejected.png`, fullPage: true })

  // ---- payer2 sees the reason, the plan did not change -----------------------------------------------------------------
  check('payer2\'s plan did not change', (await json(await call(cookies2, '/subscriptions/my-subscription/'))).status === 'no_subscription')
  await payer2.reload({ waitUntil: 'networkidle2' })
  await sleep(500)
  const rej = await payer2.evaluate(() => { const n = document.querySelector('[data-testid=billing-rejected]'); return n ? { text: n.innerText, bold: n.querySelectorAll('b').length } : null })
  check('Billing shows the rejection with the reason as literal text', rej && rej.text.includes('<b>x</b> & more') && rej.bold === 0 && /plan has not changed/i.test(rej.text), rej?.text.replace(/\s+/g, ' ').slice(0, 160))
  await payer2.screenshot({ path: `${OUT}/desktop-billing-rejected.png`, fullPage: true })
  await payer2.setViewport({ width: 390, height: 844 })
  await sleep(500)
  await payer2.screenshot({ path: `${OUT}/mobile-billing-rejected.png`, fullPage: true })
  check('390px rejected Billing: no horizontal page scroll', await noHScroll(payer2))
  await payer2.setViewport({ width: 1280, height: 900 })
  const rejectMail = await json(await fetch(`${MAIL}/search?query=${encodeURIComponent(`to:${E.payer2}`)}`))
  mailIds.push(...(rejectMail.messages || []).map((m) => m.ID))
  const rejectBody = rejectMail.messages?.[0] ? (await json(await fetch(`${MAIL}/message/${rejectMail.messages[0].ID}`))).Text : ''
  check('payer2 got the rejection email with the reason', /could not be approved/i.test(rejectMail.messages?.[0]?.Subject || '') && rejectBody.includes('The amount on the receipt is wrong'), rejectMail.messages?.[0]?.Subject)
  const reuse = await call(cookies2, '/subscriptions/payments/', { method: 'POST', body: (() => { const f = new FormData(); f.append('plan', JSON.parse(py(`import json; from apps.subscriptions.models import SubscriptionPlan as P; print(json.dumps(str(P.objects.get(key='basic').id)))`))); f.append('amount', proPlanId[1]); f.append('reference', REF2); f.append('payment_proof', new Blob([fs.readFileSync(PNG_FILE)], { type: 'image/png' }), 'again.png'); return f })() })
  check('after the rejection the SAME user may submit that ID again (201)', reuse.status === 201, reuse.status)
  proofFiles.push(...JSON.parse(py(`
import json
from apps.subscriptions.models import ManualPayment
print(json.dumps([p.payment_proof.name for p in ManualPayment.objects.filter(user__email='${E.payer2}')]))
`)))
  check('...but payer1 may not take it (400)', (await call(cookies1, '/subscriptions/payments/', { method: 'POST', body: (() => { const f = new FormData(); f.append('plan', JSON.parse(py(`import json; from apps.subscriptions.models import SubscriptionPlan as P; print(json.dumps(str(P.objects.get(key='studio').id)))`))); f.append('amount', JSON.parse(py(`import json; from apps.subscriptions.models import SubscriptionPlan as P; print(json.dumps(str(P.objects.get(key='studio').price)))`))); f.append('reference', REF2); f.append('payment_proof', new Blob([fs.readFileSync(PNG_FILE)], { type: 'image/png' }), 'steal.png'); return f })() })).status === 400)

  // ================= the period ends: Free again with no job having run =================================================
  py(`
from datetime import timedelta
from django.utils import timezone
from apps.subscriptions.models import UserSubscription
UserSubscription.objects.filter(user__email='${E.payer1}').update(expires_at=timezone.now() - timedelta(minutes=1))
print('ok')
`)
  const stillActive = py(`from apps.subscriptions.models import UserSubscription as U; print(U.objects.get(user__email='${E.payer1}').status)`)
  check('the row still says active (no sweep ran)', stillActive === 'active', stillActive)
  check('Original download is refused again at once (back to Free)', (await patchGallery(cookies1, BACK)).status === 200 && (await patchGallery(cookies1, ORIGINAL)).status === 403)
  await payer1.reload({ waitUntil: 'networkidle2' })
  await sleep(600)
  check('Billing shows the lapsed state and no Active Tier', /plan ended on/i.test(await bodyText(payer1)) && (await visible(payer1, '[data-testid=billing-active-plan]')) === 0)
  await payer1.screenshot({ path: `${OUT}/desktop-billing-lapsed.png`, fullPage: true })
  check('nothing was deleted: the gallery and the payment rows are still there', py(`from apps.galleries.models import Gallery as G; from apps.subscriptions.models import ManualPayment as M; print(G.objects.filter(slug='${SLUG}').count(), M.objects.filter(user__email='${E.payer1}').count())`) === '1 1')

  // ================= audit log and what it holds ========================================================================
  await staff.goto(`${APP}/dashboard/staff/audit`, { waitUntil: 'networkidle2' })
  await sleep(800)
  const audit = await bodyText(staff)
  check('the audit log lists submit, approve, reject and proof opened', /submitted a manual payment/i.test(audit) && /approved a manual payment/i.test(audit) && /rejected a manual payment/i.test(audit) && /opened a payment proof/i.test(audit))
  await mask(staff, '[data-testid=audit-row]')
  await staff.screenshot({ path: `${OUT}/desktop-audit.png` })
  const rows = JSON.parse(py(`
import json
from apps.users.models import StaffAuditLog
rows = StaffAuditLog.objects.filter(action__startswith='payment.', actor_email__in=['${E.staff}', '${E.payer1}', '${E.payer2}']).order_by('id')
print(json.dumps([[r.action, r.actor_email, r.target_email, r.reason, bool(r.ip)] for r in rows]))
`))
  console.log('AUDIT', JSON.stringify(rows))
  const actions = rows.map((r) => r[0])
  check('audit rows: 4 submits, 1 approve, 1 reject, 2 proof views', actions.filter((a) => a === 'payment.submit').length === 4 && actions.filter((a) => a === 'payment.approve').length === 1 && actions.filter((a) => a === 'payment.reject').length === 1 && actions.filter((a) => a === 'payment.proof_view').length === 2, JSON.stringify(actions))
  const blob = JSON.stringify(rows)
  check('no audit row holds a reference, a file name or the reject reason', ![REF1, REF2, REF_STAFF, 'payment_proofs', '.png', '.pdf', 'amount on the receipt'].some((s) => blob.includes(s)))
  check('every audit row has the trusted address', rows.every((r) => r[4]))

  // ================= a normal user ======================================================================================
  let normalStaffCalls = 0
  payer2.on('request', (r) => { if (r.url().includes('/api/v1/staff/')) normalStaffCalls += 1 })
  await payer2.goto(`${APP}/dashboard/staff/payments`, { waitUntil: 'networkidle2' })
  await sleep(600)
  check('a normal user at /dashboard/staff/payments sees "Staff only" and made no staff request', /staff only/i.test(await bodyText(payer2)) && normalStaffCalls === 0, normalStaffCalls)
  await payer2.screenshot({ path: `${OUT}/desktop-normal-user-denied.png` })
  for (const [method, p, body] of [['GET', '/staff/payments/'], ['POST', `/staff/payments/${p1id}/approve/`, {}], ['POST', `/staff/payments/${p1id}/reject/`, { reason: 'x' }], ['POST', `/staff/payments/${p1id}/proof-link/`, {}], ['GET', `/staff/payments/${p1id}/proof/?s=x`]]) {
    const response = await call(cookies2, p, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined })
    check(`API ${method} ${p.replace(p1id, '<id>')} answers 403 to a normal user`, response.status === 403, response.status)
  }
} finally {
  // ---- cleanup: exact rows only ------------------------------------------------------------------------------------------
  try { await browser?.close() } catch { /* the browser this script opened */ }
  const emails = Object.values(E)
  console.log('CLEANUP users', JSON.stringify(emails), 'proof files', JSON.stringify(proofFiles), 'mail ids', JSON.stringify(mailIds))
  console.log(pyAll(`
import json
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from apps.subscriptions.models import ManualPayment, PaymentInstructions
U = get_user_model()
emails = ${JSON.stringify(emails)}
users = U.objects.filter(email__in=emails)
print('users to delete:', sorted(users.values_list('email', flat=True)), 'count', users.count())
assert users.count() == len(emails), 'count does not match what this run created'
payments = ManualPayment.objects.filter(user__in=users)
names = sorted({p.payment_proof.name for p in payments if p.payment_proof} | set(${JSON.stringify(proofFiles)}))
print('payments to delete:', payments.count(), 'files', names)
users.delete()
for name in names:
    default_storage.delete(name)
seed = json.loads(${JSON.stringify(JSON.stringify(seeded))})
row = PaymentInstructions.load()
if row.qr_image and row.qr_image.name == seed['qr']:
    row.qr_image.storage.delete(row.qr_image.name)
if seed['existed']:
    for key, value in seed['before'].items():
        setattr(row, key, value)
    row.qr_image = seed['before_qr'] or None
    row.save()
else:
    PaymentInstructions.objects.filter(pk=1).delete()
print('left:', U.objects.filter(email__in=emails).count(), ManualPayment.objects.filter(reference__startswith='QA75B-').count())
`))
  for (const id of mailIds) { try { await fetch(`${MAIL}/messages`, { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ IDs: [id] }) }) } catch { /* mailpit */ } }
  fs.rmSync(TMP, { recursive: true, force: true })
  const failed = checks.filter((c) => !c.ok)
  console.log(`\n${checks.length - failed.length} / ${checks.length} checks passed`)
  if (failed.length) console.log('FAILED:', failed.map((c) => c.name).join(' | '))
  process.exitCode = failed.length ? 1 : 0
}
