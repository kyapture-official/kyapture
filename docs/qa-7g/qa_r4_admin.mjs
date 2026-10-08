// 7G R4 browser check: the Django admin shows design_settings read-only, and a PIN use
// recorded between opening and saving the gallery form survives the save.
// Env: QA7G_STAFF_EMAIL, QA7G_PASSWORD, QA7G_GALLERY_ID (pin_use_count starts at 1).
import puppeteer from 'puppeteer-core'
import { execSync } from 'node:child_process'

const ADMIN = 'http://localhost:8000/admin'
const OUT = 'C:/Users/LENOVO/Desktop/kyapture/docs/qa-7g'
const ID = process.env.QA7G_GALLERY_ID
const checks = []
const check = (name, ok, detail = '') => { checks.push({ name, ok }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name} ${detail}`) }
const shell = (code) => execSync(`docker exec kyapture-backend-1 python manage.py shell -c "${code}"`).toString().trim().split('\n').pop()
const count = () => shell(`from apps.galleries.models import Gallery; print(Gallery.objects.get(pk='${ID}').design_settings['privacy']['pin_use_count'])`)

const browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new' })
try {
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  await page.setViewport({ width: 1280, height: 900 })
  await page.goto(`${ADMIN}/login/`, { waitUntil: 'networkidle2' })
  await page.type('#id_username', process.env.QA7G_STAFF_EMAIL)
  await page.type('#id_password', process.env.QA7G_PASSWORD)
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle2' }), page.click('input[type=submit]')])
  for (const [label, width, height] of [['desktop', 1280, 900], ['mobile', 390, 844]]) {
    await page.setViewport({ width, height })
    await page.goto(`${ADMIN}/galleries/gallery/${ID}/change/`, { waitUntil: 'networkidle2' })
    const form = await page.evaluate(() => ({
      editable: Boolean(document.querySelector('[name=design_settings]')),
      shown: document.querySelector('.field-design_settings .readonly')?.innerText || '',
    }))
    check(`${label}: design_settings has no input`, !form.editable)
    check(`${label}: design_settings shown read-only`, form.shown.includes('pin_use_count'), form.shown.slice(0, 80))
    await page.screenshot({ path: `${OUT}/${label}-admin-design-settings-readonly.png`, fullPage: false })
  }
  // The form is open (mobile). A visitor uses the PIN now; then staff renames and saves.
  const before = count()
  shell(`from apps.galleries.models import Gallery; from apps.clients.download_access import record_pin_use; print(record_pin_use(Gallery.objects.get(pk='${ID}')))`)
  const afterUse = count()
  check('PIN use recorded while the form was open', Number(afterUse) === Number(before) + 1, `${before} -> ${afterUse}`)
  await page.$eval('#id_title', (el) => { el.value = 'QA 7G admin renamed' })
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle2' }), page.click('input[name=_save]')])
  const saved = await page.evaluate(() => document.querySelector('.messagelist')?.innerText || '')
  check('admin save succeeded', /changed successfully/i.test(saved), saved.slice(0, 80))
  check('PIN use survived the admin save', count() === afterUse, `${afterUse} -> ${count()}`)
  check('title saved', shell(`from apps.galleries.models import Gallery; print(Gallery.objects.get(pk='${ID}').title)`) === 'QA 7G admin renamed')
} finally {
  await browser.close()
}
console.log(`SUMMARY ${checks.filter((c) => c.ok).length}/${checks.length}`)
