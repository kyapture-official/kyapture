// 7F F3 browser check: the ready link carries its key in the #fragment; an old ?key= link moves there.
import puppeteer from 'puppeteer-core'
import { execSync } from 'node:child_process'

const APP = 'http://localhost:3000'
const API = 'http://localhost:8000/api/v1'
const BASE = `${API}/public/${process.env.QA7F_USERNAME}/${process.env.QA7F_SLUG}/`
const OUT = 'C:/Users/LENOVO/Desktop/kyapture/docs/qa-7f'
const EMAIL = `qa7f-ready-${Date.now()}@example.invalid`
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const checks = []
const check = (name, ok, detail = '') => { checks.push({ name, ok }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name} ${detail}`) }
const post = async (url, body) => {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: APP }, body: JSON.stringify(body) })
  return { status: r.status, data: await r.json().catch(() => ({})) }
}

const access = await post(`${BASE}download-access/`, { email: EMAIL })
check('download-access 200', access.status === 200, access.status)
const job = await post(`${BASE}download/`, { download_token: access.data.download_token, resolution: 'download' })
check('prepare 202', job.status === 202, `${job.status} ${JSON.stringify(job.data).slice(0, 120)}`)
const { job_id: jobId, link_token: key } = job.data
let state = ''
for (let i = 0; i < 60 && state !== 'ready'; i++) {
  await sleep(2000)
  const r = await fetch(`${BASE}download-jobs/${jobId}/?link_token=${encodeURIComponent(key)}`)
  state = (await r.json()).state
}
check('job ready (real worker)', state === 'ready', state)

// The ready email (Mailpit): its link uses #key=, never ?key=.
let mailText = ''
for (let i = 0; i < 20 && !mailText; i++) {
  await sleep(1500)
  const s = await (await fetch(`http://localhost:8025/api/v1/search?query=${encodeURIComponent(`to:${EMAIL}`)}`)).json()
  if (s.messages?.length) mailText = (await (await fetch(`http://localhost:8025/api/v1/message/${s.messages[0].ID}`)).json()).Text
}
const flat = mailText.replace(/=\r?\n/g, '')
check('ready email sent', Boolean(mailText))
check('ready email link has #key= and no ?key=', flat.includes(`/download/file/${jobId}#key=`) && !flat.includes('?key='))

const browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new' })
const path = `/g/${process.env.QA7F_USERNAME}/${process.env.QA7F_SLUG}/download/file/${jobId}`
try {
  for (const [label, width, height] of [['desktop', 1280, 900], ['mobile', 390, 844]]) {
    for (const [kind, url] of [['fragment', `${APP}${path}#key=${encodeURIComponent(key)}`], ['old-query', `${APP}${path}?key=${encodeURIComponent(key)}`]]) {
      const ctx = await browser.createBrowserContext()        // a fresh browser, like opening the email
      const page = await ctx.newPage()
      await page.setViewport({ width, height })
      const apiCalls = []
      page.on('request', (req) => { if (req.url().includes('/download-jobs/')) apiCalls.push(req.url()) })
      await page.goto(url, { waitUntil: 'networkidle2' })
      await page.waitForFunction(() => /ready to download/i.test(document.body.innerText), { timeout: 20000 }).catch(() => {})
      const text = await page.evaluate(() => document.body.innerText)
      const finalUrl = page.url()
      check(`${label} ${kind}: Page 4 shows the file`, /ready to download/i.test(text) && /\.zip/i.test(text))
      check(`${label} ${kind}: address bar has #key= and no ?key=`, finalUrl.includes('#key=') && !finalUrl.includes('?key='), finalUrl.slice(-40))
      check(`${label} ${kind}: status call carried the key`, apiCalls.some((u) => u.includes('link_token=')))
      if (kind === 'fragment') await page.screenshot({ path: `${OUT}/${label}-ready-page-fragment-key.png` })
      await ctx.close()
    }
  }
} finally {
  await browser.close()
}
const logs = execSync('docker logs --since 5m kyapture-frontend-1 2>&1').toString()
const pageLines = logs.split('\n').filter((l) => l.includes(`/download/file/${jobId}`))
check('frontend log has the page requests', pageLines.length >= 2, pageLines.length)
check('frontend log has no key= at all', !logs.includes('key='))
console.log(`SUMMARY ${checks.filter((c) => c.ok).length}/${checks.length}`)
console.log('JOB', jobId)
