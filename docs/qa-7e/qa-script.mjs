// docs/qa-7e/qa-script.mjs - 7-E security regression in a real browser (Chrome headless, Docker stack :3000/:8000).
//
// Phases (run one per process so throttles get their pause between them):
//   node qa-script.mjs owner      login (UI), create gallery, upload real JPEGs + a video through the workspace input,
//                                 wait for the worker, workspace thumbnails + photo viewer
//   node qa-script.mjs public     open gallery: every tile image, video plays, favorite, share link, High Resolution,
//                                 gallery ZIP via the download page, 390 px
//   node qa-script.mjs close      unpublish -> republish: old public URLs dead, new ones load
//   node qa-script.mjs password   gallery password: wrong refused, right unlocks, images + video load
//   node qa-script.mjs pin        download PIN (+ password): High Resolution needs the PIN, still works, images load
//   node qa-script.mjs original   Pro "Original" mode: High Resolution returns the stored original bytes
//   node qa-script.mjs reset      forgot -> Mailpit link -> new password -> login
// Env: QA_PRO_EMAIL, QA_RESET_EMAIL, QA_PW, QA_NEW_PW, QA_FILES (dir with the JPEGs + one .mp4), QA_OUT (screens,
// downloads, state.json), QA_GALLERY_PASSWORD, QA_PIN. No secret is written in this file.
// It starts nothing and kills nothing: it only closes the browser it launched.
import { execFileSync } from 'node:child_process'
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import puppeteer from 'puppeteer-core'

const APP = 'http://localhost:3000'
const API = 'http://localhost:8000/api/v1'
const MAILPIT = 'http://localhost:8025/api/v1'
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const OUT = process.env.QA_OUT || '.'
const STATE = path.join(OUT, 'state.json')
const PHASE = process.argv[2]
const env = process.env
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const state = fs.existsSync(STATE) ? JSON.parse(fs.readFileSync(STATE, 'utf8')) : {}
const saveState = () => fs.writeFileSync(STATE, JSON.stringify(state, null, 2))

const results = []
function check(name, ok, detail = '') {
  results.push({ phase: PHASE, name, ok: Boolean(ok), detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`)
}
const sha = (buf) => crypto.createHash('sha256').update(buf).digest('hex')

function shell(code) {
  return execFileSync('docker', ['exec', 'kyapture-backend-1', 'python', 'manage.py', 'shell', '-c', code]).toString().trim().split('\n').pop()
}

// ── owner API, from the logged-in page (same cookies + CSRF the SPA uses) ──
async function ownerApi(page, method, p, body) {
  return page.evaluate(async (m, url, b) => {
    const csrf = (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || ''
    const r = await fetch(url, {
      method: m, credentials: 'include',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': decodeURIComponent(csrf) },
      body: b ? JSON.stringify(b) : undefined,
    })
    let j = null
    try { j = await r.json() } catch { /* empty */ }
    return { status: r.status, body: j }
  }, method, `${API}${p}`, body)
}

async function login(page, email, password) {
  await page.goto(`${APP}/login`, { waitUntil: 'networkidle0' })
  await page.type('#login-email', email)
  await page.type('#login-password', password)
  await Promise.all([page.waitForNavigation({ waitUntil: 'networkidle0', timeout: 20000 }).catch(() => {}), page.click('button.btn-submit')])
  return page.url()
}

// Scroll a page top to bottom so lazy images mount, then report every <img> in `root`.
async function imageReport(page, root, settleMs = 2500) {
  await page.evaluate(async (sel) => {
    const el = document.querySelector(sel) || document.body
    el.scrollIntoView()
    for (let y = 0; y < document.body.scrollHeight; y += 400) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 120)) }
    window.scrollTo(0, 0)
  }, root)
  await sleep(settleMs)
  return page.evaluate(async (sel) => {
    const imgs = [...document.querySelectorAll(`${sel} img`)]
    await Promise.all(imgs.map((i) => (i.complete ? null : new Promise((r) => { i.onload = r; i.onerror = r; setTimeout(r, 8000) }))))
    return imgs.map((i) => ({ src: i.currentSrc || i.src, ok: i.complete && i.naturalWidth > 0, w: i.naturalWidth }))
  }, root)
}

async function tileReport(page) {
  // one entry per public grid tile: does it show a loaded image (photo or video poster)?
  await imageReport(page, '#gallery-grid')
  return page.evaluate(() => [...document.querySelectorAll('#gallery-grid [data-ky-media-guard]')].map((t) => {
    const img = t.querySelector('img')
    return { ok: Boolean(img && img.complete && img.naturalWidth > 0), src: img ? (img.currentSrc || img.src) : null }
  }))
}

async function setDownloads(context, page, dir) {
  fs.rmSync(dir, { recursive: true, force: true })
  fs.mkdirSync(dir, { recursive: true })
  const cdp = await page.createCDPSession()
  await cdp.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: dir, browserContextId: context.id, eventsEnabled: true })
}
async function waitFile(dir, ms = 60000) {
  const end = Date.now() + ms
  while (Date.now() < end) {
    const f = fs.readdirSync(dir).find((n) => !n.endsWith('.crdownload'))
    if (f) { await sleep(500); return { name: f, bytes: fs.readFileSync(path.join(dir, f)) } }
    await sleep(500)
  }
  return null
}
function jpegSize(buf) {
  let i = 2
  while (i < buf.length) {
    if (buf[i] !== 0xff) return null
    const m = buf[i + 1]
    const len = buf.readUInt16BE(i + 2)
    if (m >= 0xc0 && m <= 0xc3) return { h: buf.readUInt16BE(i + 5), w: buf.readUInt16BE(i + 7) }
    i += 2 + len
  }
  return null
}

// Visitor: open the download dialog of tile `index`, pass any gate, pick High Resolution, download.
async function photoDownload(page, dir, index, { email, pin } = {}) {
  fs.readdirSync(dir).forEach((f) => fs.rmSync(path.join(dir, f)))
  await page.evaluate((i) => {
    const t = document.querySelectorAll('#gallery-grid [data-ky-media-guard]')[i]
    t.scrollIntoView({ block: 'center' })
    t.querySelector('button[aria-label="Download this photo"]').click()
  }, index)
  await sleep(1200)
  const dialog = () => page.evaluate(() => {
    const d = [...document.querySelectorAll('[role=dialog]')].find((x) => /download/i.test(x.textContent))
    return d ? d.innerText.slice(0, 300) : null
  })
  let text = await dialog()
  const gateText = text
  const pinField = Boolean(await page.$('[role=dialog] input[placeholder="Enter download PIN"]'))
  if (text && /PIN|email/i.test(text) && !/Photo Size/i.test(text)) {
    if (email && await page.$('[role=dialog] input[type=email]')) await page.type('[role=dialog] input[type=email]', email)
    if (pin && await page.$('[role=dialog] input[placeholder="Enter download PIN"]')) await page.type('[role=dialog] input[placeholder="Enter download PIN"]', pin)
    await page.evaluate(() => [...document.querySelectorAll('[role=dialog] button[type=submit]')].pop().click())
    await sleep(2000)
    text = await dialog()
  }
  const sizes = await page.evaluate(() => [...document.querySelectorAll('[role=dialog] [role=radio]')].map((b) => b.innerText.trim()))
  await page.evaluate(() => {
    const hr = [...document.querySelectorAll('[role=dialog] [role=radio]')].find((b) => /high resolution/i.test(b.innerText))
    hr?.click()
  })
  await sleep(300)
  await page.evaluate(() => [...document.querySelectorAll('[role=dialog] button[type=submit]')].pop().click())
  const file = await waitFile(dir, 60000)
  const alert = await page.evaluate(() => document.querySelector('[role=dialog] [role=alert]')?.innerText || '')
  await page.keyboard.press('Escape')
  await sleep(500)
  return { sizes, file, alert, gateText, pinField }
}

async function playVideo(page) {
  // open the lightbox on tile 0, walk until a <video> is shown, play it muted
  await page.evaluate(() => document.querySelectorAll('#gallery-grid [data-ky-media-guard]')[0].click())
  await sleep(1200)
  for (let i = 0; i < 15; i++) {
    if (await page.$('[role=dialog][aria-label="Photo viewer"] video')) break
    await page.keyboard.press('ArrowRight')
    await sleep(700)
  }
  const result = await page.evaluate(async () => {
    const v = document.querySelector('[role=dialog][aria-label="Photo viewer"] video')
    if (!v) return { found: false }
    v.muted = true
    try { await v.play() } catch (e) { /* reported below */ }
    await new Promise((r) => setTimeout(r, 3000))
    return { found: true, t: v.currentTime, ready: v.readyState, err: v.error ? v.error.code : null, src: (v.currentSrc || '').replace(/token=[^&]+/, 'token=<redacted>') }
  })
  await page.keyboard.press('Escape')
  await sleep(500)
  return result
}

async function newVisitor(browser, viewport = { width: 1366, height: 900 }) {
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  await page.setViewport(viewport)
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  const failed = []
  page.on('response', (r) => { if (r.request().resourceType() === 'image' && r.status() >= 400) failed.push(`${r.status()} ${r.url()}`) })
  return { ctx, page, errors, failed }
}
const galleryUrl = () => `${APP}/g/${state.username}/${state.slug}`

async function openGallery(page) {
  await page.goto(galleryUrl(), { waitUntil: 'networkidle2' })
  await sleep(1500)
}

async function unlock(page, password) {
  await page.waitForSelector('form input[type=password], form input[type=text]', { timeout: 10000 })
  const input = await page.$('form input[type=password]') || await page.$('form input[type=text]')
  await input.evaluate((el) => { el.focus(); el.select() })
  await page.keyboard.press('Backspace')
  await input.type(password)
  await page.evaluate(() => [...document.querySelectorAll('form button[type=submit]')].pop().click())
  await sleep(2500)
}

async function ownerPage(browser) {
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  await page.setViewport({ width: 1366, height: 900 })
  if (state.ownerCookies) {
    await ctx.setCookie(...state.ownerCookies)
    await page.goto(`${APP}/dashboard`, { waitUntil: 'networkidle0' })
    await ownerApi(page, 'POST', '/auth/token/refresh/')   // a fresh 15-min access cookie for this phase
    state.ownerCookies = await ctx.cookies()
    saveState()
  }
  return { ctx, page }
}

// ═════════════════════════════════════════════════════════════════════════════
async function phaseOwner(browser) {
  const { ctx, page } = await ownerPage(browser)
  const resume = Boolean(state.slug)   // a second run after a crash: the gallery and uploads already exist
  const files = fs.readdirSync(env.QA_FILES).map((f) => path.join(env.QA_FILES, f))
  if (!resume) {
  const landed = await login(page, env.QA_PRO_EMAIL, env.QA_PW)
  check('O1 login through the UI lands on the dashboard', landed.includes('/dashboard'), landed)
  state.ownerCookies = await ctx.cookies()

  const created = await ownerApi(page, 'POST', '/galleries/', { title: 'QA 7-E regression' })
  check('O2 gallery created', created.status === 201, `${created.status}`)
  state.slug = created.body.slug
  const me = (await ownerApi(page, 'GET', '/auth/me/')).body
  state.username = me.username || me.user?.username
  saveState()

  await page.goto(`${APP}/dashboard/galleries/${state.slug}`, { waitUntil: 'networkidle0' })
  await sleep(1500)
  const uploads = []
  page.on('response', async (r) => {
    if (/\/photos\/[^/]+\/upload\/$/.test(new URL(r.url()).pathname) && r.request().method() === 'POST') {
      let body = ''
      try { body = JSON.stringify(await r.json()).slice(0, 300) } catch { /* empty */ }
      uploads.push({ status: r.status(), body })
    }
  })
  const input = await page.$('input[type=file]')
  await input.uploadFile(...files)
  // wait for the HTTP uploads, then for the worker
  for (let i = 0; i < 120 && uploads.length < files.length; i++) await sleep(1000)
  check('O3 every upload request answered 2xx', uploads.length === files.length && uploads.every((u) => u.status < 300),
    uploads.map((u) => u.status).join(','))
  state.uploads = uploads
  saveState()
  } else {
    await page.goto(`${APP}/dashboard/galleries/${state.slug}`, { waitUntil: 'networkidle0' })
  }
  let ready = ''
  for (let i = 0; i < 90; i++) {
    ready = shell(`from apps.photos.models import MediaAsset as M; qs=M.objects.filter(gallery__slug=${JSON.stringify(state.slug)}, gallery__photographer__email=${JSON.stringify(env.QA_PRO_EMAIL)}); print(qs.count(), qs.filter(processing_status='ready').count(), qs.filter(processing_status='failed').count())`)
    const [n, r, f] = ready.split(' ').map(Number)
    if (n === files.length && r + f === n) break
    await sleep(3000)
  }
  const [n, r] = ready.split(' ').map(Number)
  check('O4 worker made every asset READY', n === files.length && r === n, `count/ready/failed = ${ready}`)
  saveState()

  await page.reload({ waitUntil: 'networkidle0' })
  await sleep(2000)
  const thumbs = await imageReport(page, 'body')
  const media = thumbs.filter((t) => /\/(thumbnails|videos)\//.test(t.src))   // grid tiles (photo thumbnails + video poster)
  check('O5 workspace: one loaded thumbnail per asset, no empty image box', media.length >= files.length && media.every((t) => t.ok),
    `${media.filter((t) => t.ok).length}/${media.length} loaded, expected ${files.length}`)
  await page.screenshot({ path: path.join(OUT, 'o5-workspace.png') })

  // open the first photo in the photographer's viewer: the large photo must load
  const opened = await page.evaluate(() => {
    const img = [...document.querySelectorAll('img')].find((i) => /\/thumbnails\//.test(i.src))
    const clickable = img?.closest('[role=button], button, a')
    clickable?.click()
    return Boolean(img)
  })
  await sleep(2500)
  const viewer = await page.evaluate(() => {
    const d = document.querySelector('[role=dialog]')
    if (!d) return null
    const imgs = [...d.querySelectorAll('img')]
    return imgs.map((i) => ({ ok: i.complete && i.naturalWidth > 0, w: i.naturalWidth, src: i.currentSrc || i.src }))
  })
  check('O6 workspace photo viewer shows the photo', opened && viewer && viewer.some((v) => v.ok && v.w >= 1000), JSON.stringify(viewer?.map((v) => v.w)))
  await page.screenshot({ path: path.join(OUT, 'o6-workspace-viewer.png') })
  await page.keyboard.press('Escape')

  // downloads on, no email/PIN yet, High Resolution = 3600 master; publish
  const patch = await ownerApi(page, 'PATCH', `/galleries/${state.slug}/`, {
    is_downloadable: true,
    design_settings: { downloads: { require_email: false, high_res: { enabled: true, mode: '3600' }, web: { enabled: true } } },
  })
  const pub = await ownerApi(page, 'POST', `/galleries/${state.slug}/publish/`, { is_published: true })
  check('O7 downloads on (High Resolution = master) and published', patch.status === 200 && pub.status === 200, `${patch.status}/${pub.status}`)
  saveState()
  await ctx.close()
}

async function phasePublic(browser) {
  const v = await newVisitor(browser)
  await setDownloads(v.ctx, v.page, path.join(OUT, 'dl-public'))
  await v.page.evaluateOnNewDocument(() => {
    window.__copied = []
    const rec = (t) => { window.__copied.push(String(t)); return Promise.resolve() }
    try { Object.defineProperty(navigator, 'clipboard', { value: { writeText: rec }, configurable: true }) } catch { /* empty */ }
    const orig = document.execCommand.bind(document)
    document.execCommand = (cmd, ...a) => { if (cmd === 'copy') { window.__copied.push(String(window.getSelection() || document.activeElement?.value || '')); return true } return orig(cmd, ...a) }
  })
  await openGallery(v.page)
  const tiles = await tileReport(v.page)
  state.publicSrcBefore = tiles.map((t) => t.src)
  saveState()
  check('P1 public gallery: every tile shows its image (photos + video poster)', tiles.length >= 8 && tiles.every((t) => t.ok),
    `${tiles.filter((t) => t.ok).length}/${tiles.length}`)
  await v.page.screenshot({ path: path.join(OUT, 'p1-public-desktop.png') })
  const vid = await playVideo(v.page)
  check('P2 video plays in the lightbox', vid.found && vid.t > 0.5 && !vid.err, JSON.stringify(vid))

  // favorite
  await v.page.evaluate(() => {
    const t = document.querySelectorAll('#gallery-grid [data-ky-media-guard]')[1]
    t.scrollIntoView({ block: 'center' })
    t.querySelector('button[aria-label="Add to favorites"]').click()
  })
  await sleep(1200)
  if (await v.page.$('[role=dialog] input[type=email]')) {
    await v.page.type('[role=dialog] input[type=email]', `qa7e-visitor-${Date.now()}@example.invalid`)
    await v.page.evaluate(() => [...document.querySelectorAll('[role=dialog] button[type=submit]')].pop().click())
    await sleep(1500)
  }
  await v.page.reload({ waitUntil: 'networkidle2' })
  await v.page.evaluate(() => document.getElementById('gallery-grid')?.scrollIntoView())
  await sleep(2000)
  const favCount = await v.page.evaluate(() => document.querySelectorAll('#gallery-grid button[aria-label="Remove from favorites"]').length)
  check('P3 favorite survives a reload', favCount === 1, `${favCount} hearted`)
  await v.page.evaluate(() => document.querySelector('button[aria-label="View favorites"]')?.click())
  await sleep(1500)
  const panelImgs = await v.page.evaluate(() => {
    const d = [...document.querySelectorAll('[role=dialog], aside')].find((x) => /favorite/i.test(x.textContent))
    return d ? [...d.querySelectorAll('img')].map((i) => i.complete && i.naturalWidth > 0) : null
  })
  check('P4 favorites panel shows the photo', panelImgs && panelImgs.length >= 1 && panelImgs.every(Boolean), JSON.stringify(panelImgs))
  await v.page.screenshot({ path: path.join(OUT, 'p4-favorites.png') })
  await v.page.keyboard.press('Escape')
  await sleep(500)

  // share link: tile Share -> Get direct link -> open it in a fresh browser
  await v.page.evaluate(() => {
    const t = document.querySelectorAll('#gallery-grid [data-ky-media-guard]')[0]
    t.scrollIntoView({ block: 'center' })
    t.querySelector('button[aria-label="Share photo"]').click()
  })
  await sleep(800)
  await v.page.evaluate(() => [...document.querySelectorAll('button, [role=menuitem], a')].find((b) => /get direct link/i.test(b.textContent))?.click())
  await sleep(1200)
  const copied = await v.page.evaluate(() => {
    const field = [...document.querySelectorAll('input')].map((i) => i.value).find((x) => /^https?:\/\//.test(x))
    return (window.__copied || []).concat(field ? [field] : [])
  })
  const shareUrl = copied.find((c) => /^https?:\/\//.test(c))
  check('P5 share gives a plain gallery link with no token', shareUrl && !/token|key=/.test(shareUrl), shareUrl)
  await v.page.keyboard.press('Escape')
  if (shareUrl) {
    const r = await newVisitor(browser)
    await r.page.goto(shareUrl, { waitUntil: 'networkidle2' })
    const rt = await tileReport(r.page)
    check('P6 share link opens the gallery for someone else, images load', rt.length >= 8 && rt.every((t) => t.ok), `${rt.filter((t) => t.ok).length}/${rt.length}`)
    await r.ctx.close()
  }

  // High Resolution single photo = Download Master (long edge <= 3600, not the original bytes)
  const d = await photoDownload(v.page, path.join(OUT, 'dl-public'), 0)
  const dims = d.file ? jpegSize(d.file.bytes) : null
  state.hrMaster = d.file ? { name: d.file.name, sha: sha(d.file.bytes), size: d.file.bytes.length, dims } : null
  check('P7 High Resolution photo download works (JPEG)', d.file && d.file.bytes[0] === 0xff && d.file.bytes[1] === 0xd8,
    `${d.file?.name} ${d.file?.bytes.length} B ${JSON.stringify(dims)} sizes=${d.sizes.join('|')} ${d.alert}`)
  saveState()

  // gallery ZIP through the download page -> job page (the emailed/share-able link) -> file
  fs.readdirSync(path.join(OUT, 'dl-public')).forEach((f) => fs.rmSync(path.join(OUT, 'dl-public', f)))
  await v.page.goto(`${galleryUrl()}/download`, { waitUntil: 'networkidle2' })
  await sleep(1500)
  await v.page.evaluate(() => [...document.querySelectorAll('button[type=submit]')].pop()?.click())
  await v.page.waitForFunction(() => /\/download\/file\//.test(location.pathname), { timeout: 20000 }).catch(() => {})
  const jobUrl = v.page.url()
  check('P8 download page starts a ZIP job (job page with its key)', /\/download\/file\/.+\?key=/.test(jobUrl), jobUrl.replace(/key=[^&]+/, 'key=<k>'))
  await v.page.waitForSelector('button[aria-label^="Download "]', { timeout: 120000 }).catch(() => {})
  await v.page.evaluate(() => document.querySelector('button[aria-label^="Download "]')?.click())
  const zip = await waitFile(path.join(OUT, 'dl-public'), 90000)
  check('P9 the ZIP downloads (PK header)', zip && zip.bytes[0] === 0x50 && zip.bytes[1] === 0x4b, `${zip?.name} ${zip?.bytes.length} B`)
  // the job link works for a second person (what the ready email carries)
  const r2 = await newVisitor(browser)
  await setDownloads(r2.ctx, r2.page, path.join(OUT, 'dl-joblink'))
  await r2.page.goto(jobUrl, { waitUntil: 'networkidle2' })
  await r2.page.waitForSelector('button[aria-label^="Download "]', { timeout: 30000 }).catch(() => {})
  await r2.page.evaluate(() => document.querySelector('button[aria-label^="Download "]')?.click())
  const zip2 = await waitFile(path.join(OUT, 'dl-joblink'), 60000)
  check('P10 the download link opened in another browser downloads the ZIP', zip2 && zip2.bytes[0] === 0x50, `${zip2?.bytes.length} B`)
  await r2.ctx.close()
  check('P11 no failed image request, no page error (desktop)', v.failed.length === 0 && v.errors.length === 0, [...v.failed, ...v.errors].join(' | ').slice(0, 400))
  await v.ctx.close()

  // 390 px
  const m = await newVisitor(browser, { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 })
  await openGallery(m.page)
  const mt = await tileReport(m.page)
  check('M1 390px: every tile shows its image', mt.length >= 8 && mt.every((t) => t.ok), `${mt.filter((t) => t.ok).length}/${mt.length}`)
  await m.page.screenshot({ path: path.join(OUT, 'm1-public-390.png') })
  const mv = await playVideo(m.page)
  check('M2 390px: video plays', mv.found && mv.t > 0.5 && !mv.err, JSON.stringify(mv))
  check('M3 390px: no horizontal overflow', await m.page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
  await m.ctx.close()
}

async function phaseClose(browser) {
  const { ctx, page } = await ownerPage(browser)
  const off = await ownerApi(page, 'POST', `/galleries/${state.slug}/publish/`, { is_published: false })
  const v = await newVisitor(browser)
  await openGallery(v.page)
  const closedTiles = await v.page.evaluate(() => document.querySelectorAll('#gallery-grid [data-ky-media-guard]').length)
  check('C1 unpublished gallery shows no photos to a visitor', off.status === 200 && closedTiles === 0, `${off.status}, ${closedTiles} tiles`)
  await sleep(6000) // rotate_public_media runs in the worker
  const oldStatus = await v.page.evaluate(async (u) => (await fetch(u, { cache: 'no-store' })).status, state.publicSrcBefore[0])
  check('C2 an old public image URL is dead after closing', oldStatus === 404, `${oldStatus}`)
  const on = await ownerApi(page, 'POST', `/galleries/${state.slug}/publish/`, { is_published: true })
  await sleep(4000)
  await openGallery(v.page)
  const tiles = await tileReport(v.page)
  const moved = tiles.length && tiles.every((t) => !state.publicSrcBefore.includes(t.src))
  check('C3 republished: every tile loads from its new URL, no empty box', on.status === 200 && tiles.length >= 8 && tiles.every((t) => t.ok) && moved,
    `${tiles.filter((t) => t.ok).length}/${tiles.length}, moved=${moved}`)
  const vid = await playVideo(v.page)
  check('C4 republished: video plays', vid.found && vid.t > 0.5 && !vid.err, JSON.stringify(vid))
  state.publicSrcBefore = tiles.map((t) => t.src)
  saveState()
  await v.ctx.close()
  await ctx.close()
}

async function phasePassword(browser) {
  const { ctx, page } = await ownerPage(browser)
  const set = await ownerApi(page, 'POST', `/galleries/${state.slug}/set-password/`, { password: env.QA_GALLERY_PASSWORD })
  check('W1 owner sets a gallery password', set.status === 200, `${set.status}`)
  await sleep(6000)
  const v = await newVisitor(browser)
  await openGallery(v.page)
  const locked = await v.page.evaluate(() => ({ tiles: document.querySelectorAll('#gallery-grid [data-ky-media-guard]').length, pw: Boolean(document.querySelector('form input[type=password]')) }))
  check('W2 visitor sees the password form, no photos', locked.pw && locked.tiles === 0, JSON.stringify(locked))
  await unlock(v.page, `${env.QA_GALLERY_PASSWORD}-wrong`)
  const wrong = await v.page.evaluate(() => ({ tiles: document.querySelectorAll('#gallery-grid [data-ky-media-guard]').length, alert: document.querySelector('[aria-live="assertive"]')?.innerText || document.querySelector('[role=alert]')?.innerText || '', invalid: document.querySelector('form input[aria-invalid="true"]') !== null }))
  check('W3 a wrong password is refused with a message', wrong.tiles === 0 && wrong.alert && wrong.invalid, wrong.alert)
  await unlock(v.page, env.QA_GALLERY_PASSWORD)
  const tiles = await tileReport(v.page)
  check('W4 right password: every tile shows its image (new URLs)', tiles.length >= 8 && tiles.every((t) => t.ok) && tiles.every((t) => !state.publicSrcBefore.includes(t.src)),
    `${tiles.filter((t) => t.ok).length}/${tiles.length}`)
  await v.page.screenshot({ path: path.join(OUT, 'w4-unlocked.png') })
  const vid = await playVideo(v.page)
  check('W5 unlocked: video plays (token-bound stream)', vid.found && vid.t > 0.5 && !vid.err, JSON.stringify(vid))
  const oldStatus = await v.page.evaluate(async (u) => (await fetch(u, { cache: 'no-store' })).status, state.publicSrcBefore[0])
  check('W6 the URL seen before the password is dead', oldStatus === 404, `${oldStatus}`)
  state.publicSrcBefore = tiles.map((t) => t.src)
  saveState()
  await v.ctx.close()
  await ctx.close()
}

async function phasePin(browser) {
  const { ctx, page } = await ownerPage(browser)
  const set = await ownerApi(page, 'POST', `/galleries/${state.slug}/set-download-pin/`, { pin: env.QA_PIN })
  check('N1 owner sets a download PIN', set.status === 200, `${set.status}`)
  const v = await newVisitor(browser)
  await setDownloads(v.ctx, v.page, path.join(OUT, 'dl-pin'))
  await openGallery(v.page)
  await unlock(v.page, env.QA_GALLERY_PASSWORD)
  const tiles = await tileReport(v.page)
  check('N2 with password + PIN: every tile shows its image', tiles.length >= 8 && tiles.every((t) => t.ok), `${tiles.filter((t) => t.ok).length}/${tiles.length}`)
  const d = await photoDownload(v.page, path.join(OUT, 'dl-pin'), 0, { pin: env.QA_PIN })
  check('N3 the download asks for the PIN first', d.pinField && /PIN/i.test(d.gateText || ''), (d.gateText || '').replace(/\s+/g, ' ').slice(0, 120))
  check('N4 after the PIN, High Resolution downloads', d.file && d.file.bytes[0] === 0xff, `${d.file?.name} ${d.file?.bytes.length} B ${d.alert}`)
  const vid = await playVideo(v.page)
  check('N5 video still plays', vid.found && vid.t > 0.5 && !vid.err, JSON.stringify(vid))
  await v.ctx.close()
  await ctx.close()
}

async function phaseOriginal(browser) {
  const { ctx, page } = await ownerPage(browser)
  const p = await ownerApi(page, 'PATCH', `/galleries/${state.slug}/`, { design_settings: { downloads: { require_email: false, high_res: { enabled: true, mode: 'original' }, web: { enabled: true } } } })   // the full block, as the settings screen sends it
  check('R1 Pro owner switches High Resolution to Original', p.status === 200, `${p.status} ${JSON.stringify(p.body?.design_settings?.downloads?.high_res || p.body).slice(0, 120)}`)
  const v = await newVisitor(browser)
  await setDownloads(v.ctx, v.page, path.join(OUT, 'dl-original'))
  await openGallery(v.page)
  await unlock(v.page, env.QA_GALLERY_PASSWORD)
  await tileReport(v.page)
  const d = await photoDownload(v.page, path.join(OUT, 'dl-original'), 0, { pin: env.QA_PIN })
  const got = d.file ? sha(d.file.bytes) : null
  // the sha of every stored image original of this gallery (exact gallery + owner)
  const stored = shell(`import hashlib; from apps.photos.models import MediaAsset as M; print(' '.join(hashlib.sha256(a.original_file.read()).hexdigest() for a in M.objects.filter(gallery__slug=${JSON.stringify(state.slug)}, gallery__photographer__email=${JSON.stringify(env.QA_PRO_EMAIL)}, media_type='image')))`)
  check('R2 Pro Original download returns the stored original, byte for byte', got && stored.split(' ').includes(got),
    `${d.file?.name} ${d.file?.bytes.length} B; master sha differs: ${state.hrMaster ? state.hrMaster.sha !== got : 'n/a'} ${d.alert}`)
  await v.ctx.close()
  await ctx.close()
}

async function phaseReset(browser) {
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  await page.setViewport({ width: 1366, height: 900 })
  await page.goto(`${APP}/forgot-password`, { waitUntil: 'networkidle0' })
  await page.type('#recovery-email', env.QA_RESET_EMAIL)
  await page.click('button[type="submit"]')
  await page.waitForSelector('.auth-card__body[data-forgot-state="sent"]', { timeout: 10000 }).catch(() => {})
  let link = null
  for (let i = 0; i < 40 && !link; i++) {
    const res = await (await fetch(`${MAILPIT}/search?query=${encodeURIComponent(`to:${env.QA_RESET_EMAIL}`)}`)).json()
    const msg = res.messages.find((m) => m.Subject === 'Reset your Kyapture password')
    if (msg) {
      const full = await (await fetch(`${MAILPIT}/message/${msg.ID}`)).json()
      link = (full.Text.match(/http:\/\/localhost:3000\/reset-password#token=[A-Za-z0-9_-]+/) || [])[0] || null
    }
    if (!link) await sleep(500)
  }
  check('S1 reset email arrives with a fragment link', Boolean(link))
  await page.goto(link, { waitUntil: 'networkidle0' })
  await page.waitForSelector('#new-password', { timeout: 10000 })
  await page.type('#new-password', env.QA_NEW_PW)
  await page.type('#new-password-confirm', env.QA_NEW_PW)
  await page.click('button[type="submit"]')
  await page.waitForSelector('.auth-card__body[data-reset-state="done"]', { timeout: 10000 }).catch(() => {})
  check('S2 new password accepted', await page.$('.auth-card__body[data-reset-state="done"]').then(Boolean))
  const landed = await login(page, env.QA_RESET_EMAIL, env.QA_NEW_PW)
  check('S3 login with the new password', landed.includes('/dashboard'), landed)
  await ctx.close()
  const old = await fetch(`${API}/auth/login/`, { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: APP }, body: JSON.stringify({ email: env.QA_RESET_EMAIL, password: env.QA_PW }) })
  check('S4 the old password is refused', old.status === 400, `${old.status}`)
}

const PHASES = { owner: phaseOwner, public: phasePublic, close: phaseClose, password: phasePassword, pin: phasePin, original: phaseOriginal, reset: phaseReset }
const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--autoplay-policy=no-user-gesture-required'] })
try {
  await PHASES[PHASE](browser)
} catch (e) {
  check(`phase ${PHASE} crashed`, false, String(e).slice(0, 300))
} finally {
  await browser.close()
  fs.appendFileSync(path.join(OUT, 'results.jsonl'), results.map((r) => JSON.stringify(r)).join('\n') + '\n')
  console.log(`${PHASE}: ${results.filter((r) => r.ok).length}/${results.length} passed`)
}
