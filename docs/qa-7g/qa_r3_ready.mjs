// 7G R3 browser check: the ready page polls the job status with the key in the
// X-Download-Link-Key header; the backend log gets no `link_token=` line and no key.
// Env: QA7G_USERNAME, QA7G_SLUG (a published gallery with downloads on, no PIN / password).
import puppeteer from 'puppeteer-core'
import { execSync } from 'node:child_process'

const APP = 'http://localhost:3000'
const API = 'http://localhost:8000/api/v1'
const USER = process.env.QA7G_USERNAME
const SLUG = process.env.QA7G_SLUG
const BASE = `${API}/public/${USER}/${SLUG}/`
const OUT = 'C:/Users/LENOVO/Desktop/kyapture/docs/qa-7g'
const EMAIL = `qa7g-ready-${Date.now()}@example.invalid`
const since = new Date(Date.now() - 2000).toISOString()
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
check('prepare 202', job.status === 202, job.status)
const { job_id: jobId, link_token: key } = job.data
const path = `/g/${USER}/${SLUG}/download/file/${jobId}`

const browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new' })
try {
  for (const [label, width, height] of [['desktop', 1280, 900], ['mobile', 390, 844]]) {
    const ctx = await browser.createBrowserContext()        // a fresh browser, like opening the email
    const page = await ctx.newPage()
    await page.setViewport({ width, height })
    const polls = []
    page.on('request', (req) => {
      if (req.url().includes('/download-jobs/') && req.method() === 'GET') {
        polls.push({ url: req.url(), header: req.headers()['x-download-link-key'] })
      }
    })
    const failed = []
    page.on('requestfailed', (req) => failed.push(req.url()))
    await page.goto(`${APP}${path}#key=${encodeURIComponent(key)}`, { waitUntil: 'domcontentloaded' })
    // Opened right after the prepare POST: the page polls (2 s, 5 s, then 10 s) until the worker is done.
    await page.waitForFunction(() => /ready to download/i.test(document.body.innerText), { timeout: 90000 }).catch(() => {})
    const text = await page.evaluate(() => document.body.innerText)
    check(`${label}: page lists the file`, /ready to download/i.test(text) && /\.zip/i.test(text))
    check(`${label}: status polls made`, polls.length >= 1, polls.length)
    check(`${label}: no poll URL has link_token or the key`, polls.every((p) => !p.url.includes('link_token') && !p.url.includes(key)))
    check(`${label}: every poll sent the key in X-Download-Link-Key`, polls.length > 0 && polls.every((p) => p.header === key))
    check(`${label}: no failed request (CORS preflight ok)`, failed.length === 0, failed.join(' '))
    await page.screenshot({ path: `${OUT}/${label}-ready-page-header-key.png` })
    await ctx.close()
  }
} finally {
  await browser.close()
}

const logs = execSync(`docker logs --since ${since} kyapture-backend-1 2>&1`).toString()
const jobLines = logs.split('\n').filter((l) => l.includes(`/download-jobs/${jobId}/`))
check('backend log has the status requests', jobLines.length >= 2, jobLines.length)
check('backend log has 0 link_token= lines', !logs.includes('link_token='), (logs.match(/link_token=/g) || []).length)
check('backend log never holds the key', !logs.includes(key) && !logs.includes(encodeURIComponent(key)))
console.log(`SUMMARY ${checks.filter((c) => c.ok).length}/${checks.length}`)
console.log('JOB', jobId, 'POLL LINES', jobLines.length)
