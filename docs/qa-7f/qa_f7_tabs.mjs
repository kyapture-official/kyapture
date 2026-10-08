// 7F F7 browser check: two tabs whose access cookie expired refresh at the same moment.
// Usage: node qa_f7_tabs.mjs <label> [rounds]
import puppeteer from 'puppeteer-core'

const label = process.argv[2] || 'run'
const rounds = Number(process.argv[3] || 5)
const APP = 'http://localhost:3000'
const API = 'http://localhost:8000/api/v1'
const EMAIL = process.env.QA7F_EMAIL
const PASSWORD = process.env.QA7F_PASSWORD
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await puppeteer.launch({
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: 'new',
})
const results = []
try {
  const ctx = await browser.createBrowserContext()
  const login = await ctx.newPage()
  await login.goto(`${APP}/login`, { waitUntil: 'networkidle2' })
  // Log in once through the API from the page (cookies land in this context).
  const status = await login.evaluate(async (api, email, password) => {
    const r = await fetch(`${api}/auth/login/`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    return r.status
  }, API, EMAIL, PASSWORD)
  console.log('login', status)
  await login.goto(`${APP}/dashboard`, { waitUntil: 'networkidle2' })
  console.log('dashboard url', login.url())
  const tabA = login
  const tabB = await ctx.newPage()
  await tabB.goto(`${APP}/dashboard`, { waitUntil: 'networkidle2' })

  const refreshes = []
  for (const tab of [tabA, tabB]) {
    tab.on('response', (res) => {
      if (res.url().includes('/auth/token/refresh/')) refreshes.push(res.status())
    })
  }

  for (let round = 1; round <= rounds; round++) {
    refreshes.length = 0
    // The access cookie "expires": both tabs now need a refresh on their next call.
    const client = await tabA.createCDPSession()
    await client.send('Network.deleteCookies', { name: 'access_token', url: 'http://localhost:8000/' })
    await client.send('Network.deleteCookies', { name: 'access_token', domain: 'localhost' })
    await Promise.all([tabA.reload({ waitUntil: 'networkidle2' }), tabB.reload({ waitUntil: 'networkidle2' })])
    await sleep(1500)
    const urls = [tabA.url(), tabB.url()]
    const me = await tabA.evaluate(async (api) => (await fetch(`${api}/auth/me/`, { credentials: 'include' })).status, API)
    const signedOut = urls.filter((u) => !u.includes('/dashboard')).length
    results.push({ round, refreshes: [...refreshes], urls, me, signedOut })
    console.log(JSON.stringify({ label, round, refreshes, urls, me }))
    if (me !== 200) {
      // Signed out: log in again for the next round.
      await tabA.goto(`${APP}/login`, { waitUntil: 'networkidle2' })
      await tabA.evaluate(async (api, email, password) => fetch(`${api}/auth/login/`, {
        method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      }), API, EMAIL, PASSWORD)
      await Promise.all([tabA.goto(`${APP}/dashboard`, { waitUntil: 'networkidle2' }), tabB.goto(`${APP}/dashboard`, { waitUntil: 'networkidle2' })])
    }
  }
} finally {
  await browser.close()
}
const lost = results.filter((r) => r.me !== 200 || r.signedOut > 0).length
const any401 = results.filter((r) => r.refreshes.includes(401)).length
console.log(`SUMMARY ${label}: rounds=${results.length} signed_out_rounds=${lost} rounds_with_refresh_401=${any401}`)
