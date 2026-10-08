// 7F F7 (first bullet): logging out with an EXPIRED access cookie really ends the session.
import puppeteer from 'puppeteer-core'

const APP = 'http://localhost:3000'
const API = 'http://localhost:8000/api/v1'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const checks = []
const check = (name, ok, detail = '') => { checks.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'} ${name} ${detail}`) }

const browser = await puppeteer.launch({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new' })
try {
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  await page.setViewport({ width: 1280, height: 900 })
  await page.goto(`${APP}/login`, { waitUntil: 'networkidle2' })
  const status = await page.evaluate(async (api) => (await fetch(`${api}/auth/login/`, {
    method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: process.env.QA7F_EMAIL, password: process.env.QA7F_PASSWORD }),
  })).status, API)
  check('login', status === 200, status)
  await page.goto(`${APP}/dashboard`, { waitUntil: 'networkidle2' })
  const cdp = await page.createCDPSession()
  const refreshBefore = (await cdp.send('Network.getAllCookies')).cookies.find((c) => c.name === 'refresh_token')?.value
  await cdp.send('Network.deleteCookies', { name: 'access_token', domain: 'localhost' })   // the access cookie "expired"
  const calls = []
  page.on('response', (r) => { if (/auth\/(logout|token\/refresh)\//.test(r.url())) calls.push(`${new URL(r.url()).pathname} ${r.status()}`) })
  await page.click('button[aria-label="Logout session"]')
  await sleep(3000)
  console.log('calls', calls.join(' | '))
  check('logout answered 200 after a refresh', calls.some((c) => c.includes('/auth/logout/ 200')) && calls.some((c) => c.includes('refresh/ 200')))
  check('the browser left the dashboard', !page.url().includes('/dashboard'), page.url())
  const me = await page.evaluate(async (api) => (await fetch(`${api}/auth/me/`, { credentials: 'include' })).status, API)
  check('the session is gone in this browser (/auth/me 401)', me === 401, me)
  // The refresh token the browser held before logging out no longer works anywhere.
  const replay = await fetch(`${API}/auth/token/refresh/`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Origin: APP, Cookie: `refresh_token=${refreshBefore}` }, body: '{}',
  })
  check('the old refresh token is refused (401)', replay.status === 401, replay.status)
} finally {
  await browser.close()
}
console.log(`SUMMARY ${checks.filter(Boolean).length}/${checks.length}`)
