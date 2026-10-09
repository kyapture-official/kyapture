// 7.5-D browser QA: opens every email that qa_trigger.py put in Mailpit, HTML and text, at desktop (1000 px) and
// 390 px, light and dark. Needs puppeteer-core (npm i puppeteer-core) and Chrome.
//   node qa-script.mjs <tag> <outDir>
import fs from 'node:fs'
import puppeteer from 'puppeteer-core'

const [tag, outDir] = process.argv.slice(2)
const MAILPIT = 'http://localhost:8025'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
fs.mkdirSync(outDir, { recursive: true })

const search = async (q) => (await (await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(q)}&limit=100`)).json()).messages
let messages = [...(await search(tag)), ...(await search('subject:"New payment to review"'))]
const seen = new Set()
messages = messages.filter((m) => !seen.has(m.ID) && seen.add(m.ID))
// the staff alerts of OTHER runs are filtered out by their creation time: keep only messages created since this tag
const since = Number(tag.replace('qa75d', '')) * 1000 - 5000
messages = messages.filter((m) => new Date(m.Created).getTime() >= since)

const results = []
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
try {
  for (const m of messages) {
    const full = await (await fetch(`${MAILPIT}/api/v1/message/${m.ID}`)).json()
    const subject = full.Subject
    const to = full.To.map((a) => a.Address).join(',')
    const slug = subject.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') + '-' + to.split('@')[0].replace(/[^a-z0-9]+/g, '').slice(-8)
    const row = { subject, to, id: m.ID, slug, replyTo: (full.ReplyTo || []).map((a) => a.Address).join(','), from: full.From.Address,
      hasHtml: !!full.HTML, hasText: !!full.Text, checks: {} }

    // text version
    const text = full.Text
    row.checks.textNoMarkup = !/<\/?(html|head|body|table|tr|td|div|p|a|h1|style|span|br)[\s>\/]/i.test(text)   // template markup only: a user's own typed '<i>' is legitimate text/plain
    row.checks.textHasSupport = text.includes('support@kyapture.com')
    row.checks.subjectHasNoDigits6 = !/\d{6}/.test(subject)

    for (const [label, width, dark] of [['desktop', 1000, false], ['m390', 390, false], ['m390-dark', 390, true], ['desktop-dark', 1000, true]]) {
      const page = await browser.newPage()
      const requests = []
      page.on('request', (r) => requests.push(r.url()))
      await page.setViewport({ width, height: width === 390 ? 844 : 900, deviceScaleFactor: 1 })
      await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: dark ? 'dark' : 'light' }])
      await page.goto(`${MAILPIT}/view/${m.ID}.html`, { waitUntil: 'networkidle0' })
      const info = await page.evaluate(() => {
        const card = document.querySelector('table.em-card')
        const rect = card.getBoundingClientRect()
        const cs = getComputedStyle(document.body)
        const bg = getComputedStyle(document.querySelector('td.em-outer') || document.body).backgroundColor
        const cardBg = getComputedStyle(card).backgroundColor
        const h1 = document.querySelector('h1')
        const lines = (document.body.innerText || '').split('\n').filter(Boolean)
        const widest = Math.max(...[...document.querySelectorAll('td,p,h1,a')].map((e) => e.getBoundingClientRect().right))
        return {
          cardWidth: Math.round(rect.width), scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth,
          overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth, widest: Math.round(widest),
          images: document.images.length, scripts: document.scripts.length, font: getComputedStyle(h1).fontFamily.slice(0, 60),
          bg, cardBg, h1: h1.textContent.trim(), firstLines: lines.slice(0, 3),
          wordmark: !!document.querySelector('.em-mark') && document.querySelector('.em-mark').textContent.trim(),
          support: !!document.querySelector('a[href^="mailto:"]'), links: [...document.querySelectorAll('a[href]')].map((a) => a.href),
        }
      })
      const remote = requests.filter((u) => !u.startsWith(MAILPIT) && !u.startsWith('data:'))
      row.checks[label] = { ...info, remoteRequests: remote }
      await page.screenshot({ path: `${outDir}/${slug}-${label}.png`, fullPage: true })
      await page.close()
    }
    // the text part as Mailpit serves it
    const tp = await browser.newPage()
    await tp.setViewport({ width: 390, height: 844 })
    await tp.goto(`${MAILPIT}/view/${m.ID}.txt`, { waitUntil: 'networkidle0' })
    row.checks.txtPageChars = (await tp.evaluate(() => document.body.innerText)).length
    await tp.screenshot({ path: `${outDir}/${slug}-text-m390.png`, fullPage: true })
    await tp.close()
    results.push(row)
  }
} finally {
  await browser.close()
}
fs.writeFileSync(`${outDir}/results.json`, JSON.stringify(results, null, 2))

// verdicts
let bad = 0
const fail = (m) => { bad++; console.log('FAIL', m) }
for (const r of results) {
  const d = r.checks.desktop, p = r.checks.m390
  if (!(d.cardWidth <= 600)) fail(`${r.slug} desktop card ${d.cardWidth}`)
  if (p.overflowX) fail(`${r.slug} 390 overflow ${p.scrollWidth}`)
  if (p.widest > 390) fail(`${r.slug} 390 widest ${p.widest}`)
  for (const k of ['desktop', 'm390', 'm390-dark', 'desktop-dark']) {
    const c = r.checks[k]
    if (c.images || c.scripts || c.remoteRequests.length) fail(`${r.slug} ${k} images/scripts/remote ${c.images}/${c.scripts}/${c.remoteRequests}`)
    if (!/apple|segoe|system|helvetica|arial/i.test(c.font)) fail(`${r.slug} font ${c.font}`)
    if (c.wordmark !== 'Kyapture' || !c.support) fail(`${r.slug} ${k} wordmark/support`)
  }
  if (r.checks['m390-dark'].cardBg === r.checks.m390.cardBg) fail(`${r.slug} dark mode did not change the card`)
  if (!r.checks.textNoMarkup || !r.checks.textHasSupport || !r.checks.subjectHasNoDigits6) fail(`${r.slug} text checks`)
  console.log(r.slug.padEnd(60), 'card', d.cardWidth, '| 390 scroll', p.scrollWidth, '| dark card', r.checks['m390-dark'].cardBg, '| h1', JSON.stringify(d.h1))
}
console.log(results.length, 'emails,', bad, 'failed checks')
