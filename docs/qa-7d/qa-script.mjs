import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'

// 7-D browser QA for the PUBLIC client gallery (desktop 1366 + mobile 390).
//   QA_GALLERY_URL=http://localhost:3000/g/<username>/<slug> node qa-script.mjs [desktop|mobile]
// Needs `npm i puppeteer-core` next to it, Chrome, and a published gallery with allow_download on,
// no email/PIN rule, >= 9 READY assets where the LAST one is a video (a watermark is optional).
// Writes screenshots, downloads and results JSON to QA_OUT (default: the OS temp folder).
// It starts nothing and kills nothing: it only closes the browser it launched.
import os from 'node:os'
const SP = process.env.QA_OUT || os.tmpdir()
const ONLY = process.argv[2] // 'desktop' | 'mobile'
const BASE = process.env.QA_GALLERY_URL
if (!BASE) throw new Error('Set QA_GALLERY_URL=http://localhost:3000/g/<username>/<slug>')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const VIEWPORTS = {
  desktop: { width: 1366, height: 900 },
  mobile: { width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
}

const results = []
const check = (name, ok, detail = '') => {
  results.push({ name, ok: Boolean(ok), detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  -> ' + detail : ''}`)
}

const RECORDER = `
window.__cmE = []; window.__dsE = [];
const d = (el) => el && el.tagName ? el.tagName.toLowerCase() + (el.getAttribute('aria-label') ? '[' + el.getAttribute('aria-label') + ']' : '') : '?';
window.addEventListener('contextmenu', (e) => window.__cmE.push({ t: d(e.target), e }), true);
window.addEventListener('dragstart', (e) => window.__dsE.push({ t: d(e.target), e }), true);
Object.defineProperty(window, '__cm', { get() { return window.__cmE.map((x) => ({ t: x.t, p: x.e.defaultPrevented })) }, set(v) { window.__cmE = [] } });
Object.defineProperty(window, '__ds', { get() { return window.__dsE.map((x) => ({ t: x.t, p: x.e.defaultPrevented })) }, set(v) { window.__dsE = [] } });
`

const browser = await puppeteer.launch({
  executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: 'new',
  args: ['--autoplay-policy=no-user-gesture-required'],
})

async function runViewport(name) {
  const vp = VIEWPORTS[name]
  console.log(`\n===== ${name.toUpperCase()} ${vp.width}px =====`)
  const page = await browser.newPage()
  await page.setViewport(vp)
  await page.evaluateOnNewDocument(RECORDER)
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  const dlDir = path.join(SP, `downloads-${name}`)
  fs.rmSync(dlDir, { recursive: true, force: true })
  fs.mkdirSync(dlDir, { recursive: true })
  const cdp = await page.createCDPSession()
  await cdp.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: dlDir, eventsEnabled: true })

  const lastCm = () => page.evaluate(() => window.__cm[window.__cm.length - 1] || null)
  const rightClickAt = async (x, y) => {
    await page.evaluate(() => { window.__cm = [] })
    await page.mouse.click(x, y, { button: 'right' })
    await sleep(80)
    return lastCm()
  }
  const centerOf = async (selector, index = 0) => {
    const box = await page.evaluate((s, i) => {
      const el = document.querySelectorAll(s)[i]
      if (!el) return null
      el.scrollIntoView({ block: 'center' })
      const r = el.getBoundingClientRect()
      return { x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height }
    }, selector, index)
    await sleep(150)
    // scrollIntoView may move it; re-measure
    return page.evaluate((s, i) => {
      const r = document.querySelectorAll(s)[i].getBoundingClientRect()
      return { x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height }
    }, selector, index)
  }
  const counter = () => page.evaluate(() => document.querySelector('[role=dialog][aria-label="Photo viewer"] header span')?.textContent.trim() || null)
  const lightboxOpen = () => page.evaluate(() => Boolean(document.querySelector('[role=dialog][aria-label="Photo viewer"]')))

  await page.goto(BASE, { waitUntil: 'networkidle2' })
  console.log('INFO  OS prefers-reduced-motion matches at start:', await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches))
  await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'no-preference' }])
  await page.evaluate(() => document.getElementById('gallery-grid')?.scrollIntoView())
  await sleep(2500)

  // ── 1. tile right-click ────────────────────────────────────────────────
  const TILE = '#gallery-grid [data-ky-media-guard]'
  const tileBox = await centerOf(TILE, 0)
  let cm = await rightClickAt(tileBox.x, tileBox.y - tileBox.h / 4)
  check('grid tile image: right-click is cancelled', cm && cm.p === true, JSON.stringify(cm))

  // ── 2. controls inside the tile keep the browser menu ─────────────────
  await page.mouse.move(tileBox.x, tileBox.y)
  const heart = await centerOf(`${TILE} button[aria-label="Add to favorites"]`, 0)
  cm = await rightClickAt(heart.x, heart.y)
  check('tile heart button: right-click NOT cancelled', cm && cm.p === false, JSON.stringify(cm))
  const synthetic = await page.evaluate(() => {
    const btn = document.querySelector('#gallery-grid [data-ky-media-guard] button[aria-label="Add to favorites"]')
    btn.focus()
    // what the keyboard "context menu" key / Shift+F10 sends: a contextmenu event on the focused control
    return btn.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true }))
  })
  check('focused button + menu key (synthetic contextmenu): NOT cancelled', synthetic === true)
  const dl = await centerOf(`${TILE} button[aria-label="Download this photo"]`, 0)
  cm = await rightClickAt(dl.x, dl.y)
  check('tile download button: right-click NOT cancelled', cm && cm.p === false, JSON.stringify(cm))

  // ── 3. text / controls outside the media are untouched ────────────────
  const title = await centerOf('[data-testid="toolbar-title"]', 0)
  cm = await rightClickAt(title.x, title.y)
  check('gallery title text: right-click NOT cancelled', cm && cm.p === false, JSON.stringify(cm))
  const tbDownload = await centerOf('#gallery-toolbar button[aria-label="Download"]', 0)
  cm = await rightClickAt(tbDownload.x, tbDownload.y)
  check('toolbar Download button: right-click NOT cancelled', cm && cm.p === false, JSON.stringify(cm))
  const selected = await page.evaluate(() => {
    const el = document.querySelector('[data-testid="toolbar-title"]')
    const style = getComputedStyle(el)
    const range = document.createRange(); range.selectNodeContents(el)
    const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range)
    return { text: sel.toString(), userSelect: style.userSelect }
  })
  check('gallery title text is still selectable', selected.text.includes('QA Deterrence') && selected.userSelect !== 'none', JSON.stringify(selected))
  await page.evaluate(() => window.getSelection().removeAllRanges())

  // ── 4. computed styles: drag/select/callout off, no touch lock ────────
  const styles = await page.evaluate(() => {
    const img = document.querySelector('#gallery-grid [data-ky-media-guard] img')
    const tile = document.querySelector('#gallery-grid [data-ky-media-guard]')
    const cs = getComputedStyle(img)
    return {
      draggableAttr: img.getAttribute('draggable'),
      userDrag: cs.webkitUserDrag || cs.userDrag,
      userSelect: cs.userSelect,
      callout: cs.webkitTouchCallout,
      imgTouchAction: cs.touchAction,
      tileTouchAction: getComputedStyle(tile).touchAction,
      pointerEvents: cs.pointerEvents,
      alt: img.getAttribute('alt'),
    }
  })
  check('img: draggable=false, user-drag/select none', styles.draggableAttr === 'false' && styles.userDrag === 'none' && styles.userSelect === 'none', JSON.stringify(styles))
  check('no touch-action lock on tile or img', styles.imgTouchAction === 'auto' && styles.tileTouchAction === 'auto', `${styles.imgTouchAction}/${styles.tileTouchAction}`)
  check('alt text kept on the image', Boolean(styles.alt), styles.alt)

  // ── 5. drag ───────────────────────────────────────────────────────────
  const synthDrag = await page.evaluate(() => {
    const img = document.querySelector('#gallery-grid [data-ky-media-guard] img')
    return img.dispatchEvent(new DragEvent('dragstart', { bubbles: true, cancelable: true }))
  })
  check('dragstart on the tile photo is cancelled', synthDrag === false)
  await page.evaluate(() => { window.__ds = [] })
  const tb2 = await centerOf(TILE, 1)
  await page.mouse.move(tb2.x, tb2.y); await page.mouse.down(); await page.mouse.move(tb2.x + 120, tb2.y + 60, { steps: 8 }); await page.mouse.up()
  await sleep(100)
  const ds = await page.evaluate(() => window.__ds)
  check('real mouse drag from a tile starts no un-cancelled drag', ds.every((e) => e.p === true), JSON.stringify(ds))
  await sleep(300)
  if (await lightboxOpen()) { await page.keyboard.press('Escape'); await sleep(200) }

  // ── 6. keyboard: Tab reaches tile controls, Enter works, focus ring ───
  await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0) })
  let reached = null
  for (let i = 0; i < 40; i += 1) {
    await page.keyboard.press('Tab')
    reached = await page.evaluate(() => {
      const el = document.activeElement
      const tile = el?.closest('#gallery-grid [data-ky-media-guard]')
      return tile ? { label: el.getAttribute('aria-label'), steps: 1 } : null
    })
    if (reached) { reached.steps = i + 1; break }
  }
  check('keyboard Tab reaches a control inside a tile', Boolean(reached), JSON.stringify(reached))
  if (reached) {
    await sleep(500)
    const ring = await page.evaluate(() => {
      const el = document.activeElement
      const cs = getComputedStyle(el)
      const wrapper = el.parentElement
      return { outline: cs.outlineStyle, shadow: cs.boxShadow !== 'none', wrapperOpacity: getComputedStyle(wrapper).opacity, vis: el.matches(':focus-visible') }
    })
    check('focused tile control shows a focus ring (:focus-visible)', ring.vis && (ring.shadow || ring.outline !== 'none'), JSON.stringify(ring))
    check('tile controls are visible while keyboard-focused (opacity 1)', ring.wrapperOpacity === '1', ring.wrapperOpacity)
    await page.keyboard.press('Enter')
    await sleep(800)
    const modal = await page.evaluate(() => {
      const dlg = document.querySelector('[role=dialog]:not([aria-label="Photo viewer"])')
      return dlg ? { label: dlg.getAttribute('aria-label') || dlg.querySelector('h2,h3,h4')?.textContent, hasEmailInput: Boolean(dlg.querySelector('input[type=email]')) } : null
    })
    check('Enter on a focused heart acts (opens the email step)', Boolean(modal), JSON.stringify(modal))
    if (modal?.hasEmailInput) {
      const inp = await centerOf('[role=dialog] input[type=email]', 0)
      cm = await rightClickAt(inp.x, inp.y)
      check('email input: right-click NOT cancelled', cm && cm.p === false, JSON.stringify(cm))
    }
    await page.keyboard.press('Escape'); await sleep(400)
  }

  // ── 7. lightbox ───────────────────────────────────────────────────────
  const t0 = await centerOf(TILE, 0)
  await page.mouse.click(t0.x, t0.y - t0.h / 4)
  await sleep(1200)
  check('click on a tile opens the lightbox', await lightboxOpen())
  check('lightbox counter starts at 1 / 9', (await counter()) === '1 / 9', await counter())
  await sleep(800)
  const stage = await page.evaluate(() => {
    const img = document.querySelector('[role=dialog][aria-label="Photo viewer"] img')
    const cs = getComputedStyle(img)
    const r = img.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2, userDrag: cs.webkitUserDrag || cs.userDrag, userSelect: cs.userSelect, callout: cs.webkitTouchCallout, pe: cs.pointerEvents, alt: img.alt, draggable: img.getAttribute('draggable'), td: cs.transitionDuration }
  })
  check('lightbox img: drag/select off, draggable=false, alt kept', stage.userDrag === 'none' && stage.userSelect === 'none' && stage.draggable === 'false' && stage.alt, JSON.stringify(stage))
  cm = await rightClickAt(stage.x, stage.y)
  check('lightbox photo: right-click is cancelled', cm && cm.p === true, JSON.stringify(cm))
  const lbDrag = await page.evaluate(() => document.querySelector('[role=dialog][aria-label="Photo viewer"] img').dispatchEvent(new DragEvent('dragstart', { bubbles: true, cancelable: true })))
  check('lightbox photo: dragstart cancelled', lbDrag === false)
  const closeBtn = await centerOf('[role=dialog][aria-label="Photo viewer"] button[aria-label="Close Lightbox"]', 0)
  cm = await rightClickAt(closeBtn.x, closeBtn.y)
  check('lightbox Close button: right-click NOT cancelled', cm && cm.p === false, JSON.stringify(cm))
  const lbDl = await page.evaluate(() => Boolean(document.querySelector('[role=dialog][aria-label="Photo viewer"] button[aria-label="Download this photo"]')))
  check('lightbox keeps its Download button (legit download)', lbDl)

  // keyboard in the lightbox
  await page.keyboard.press('ArrowRight'); await sleep(250)
  check('ArrowRight -> 2 / 9', (await counter()) === '2 / 9', await counter())
  await page.keyboard.press('ArrowLeft'); await sleep(250)
  check('ArrowLeft -> 1 / 9', (await counter()) === '1 / 9', await counter())
  await page.keyboard.press('Space'); await sleep(250)
  let playLabel = await page.evaluate(() => document.querySelector('[role=dialog][aria-label="Photo viewer"] header button')?.getAttribute('aria-label'))
  check('Space toggles the slideshow (Pause label)', playLabel === 'Pause slideshow', playLabel)
  await page.keyboard.press('Space'); await sleep(250)
  playLabel = await page.evaluate(() => document.querySelector('[role=dialog][aria-label="Photo viewer"] header button')?.getAttribute('aria-label'))
  check('Space again pauses (Play label)', playLabel === 'Play slideshow', playLabel)
  let trapped = true
  for (let i = 0; i < 9; i += 1) {
    await page.keyboard.press('Tab')
    trapped = trapped && (await page.evaluate(() => Boolean(document.activeElement?.closest('[role=dialog][aria-label="Photo viewer"]'))))
  }
  check('Tab stays trapped inside the lightbox (9 presses)', trapped)

  if (name === 'mobile') {
    const sw = async (x1, x2, y) => {
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: x1, y }] })
      for (let s = 1; s <= 6; s += 1) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x1 + ((x2 - x1) * s) / 6, y }] })
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
      await sleep(400)
    }
    const before = await counter()
    await sw(300, 100, 400)
    const after = await counter()
    check('touch: swipe left in the lightbox goes to the next photo', before === '1 / 9' && after === '2 / 9', `${before} -> ${after}`)
    // A raw CDP swipe to the RIGHT is taken by Chrome's own history-back gesture in touch emulation
    // (the page navigates to about:blank; the pre-7-D build does the same), so drive the app's own
    // touch handlers with synthetic touch events for this direction.
    await page.evaluate(async () => {
      const stage = document.querySelector('[role=dialog][aria-label="Photo viewer"] [data-ky-media-guard]').parentElement
      const t = (x) => new Touch({ identifier: 1, target: stage, clientX: x, clientY: 400 })
      const fire = (type, x) => stage.dispatchEvent(new TouchEvent(type, { bubbles: true, cancelable: true, touches: x == null ? [] : [t(x)], changedTouches: [t(x ?? 0)] }))
      fire('touchstart', 100); fire('touchmove', 200); fire('touchmove', 300); fire('touchend', null)
    })
    await sleep(400)
    check('touch handler: swipe right goes back (synthetic touch events)', (await counter()) === '1 / 9', await counter())
  }
  await page.screenshot({ path: path.join(SP, `qa-${name}-lightbox.png`) })

  // reduced motion
  const tdNormal = await page.evaluate(() => getComputedStyle(document.querySelector('[role=dialog][aria-label="Photo viewer"] img')).transitionProperty)
  await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }])
  await sleep(200)
  const tdReduced = await page.evaluate(() => getComputedStyle(document.querySelector('[role=dialog][aria-label="Photo viewer"] img')).transitionProperty)
  check('prefers-reduced-motion: lightbox transition off', tdNormal !== 'none' && tdReduced === 'none', `${tdNormal} -> ${tdReduced}`)
  await page.keyboard.press('Escape'); await sleep(400)
  check('Escape closes the lightbox', !(await lightboxOpen()))
  const tileTd = await page.evaluate(() => getComputedStyle(document.querySelector('#gallery-grid [data-ky-media-guard] img')).transitionProperty)
  check('prefers-reduced-motion: grid image transition off', tileTd === 'none', tileTd)
  await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'no-preference' }])

  // ── 8. video ──────────────────────────────────────────────────────────
  const vidIdx = 8
  const vtile = await centerOf(TILE, vidIdx)
  await page.mouse.click(vtile.x, vtile.y - vtile.h / 4)
  await sleep(1500)
  const vid = await page.evaluate(() => {
    const v = document.querySelector('[role=dialog][aria-label="Photo viewer"] video')
    if (!v) return null
    const r = v.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 3, controlsList: v.getAttribute('controlslist'), controls: v.controls, userDrag: getComputedStyle(v).webkitUserDrag, src: v.currentSrc.replace(/token=[^&]+/, 'token=…') }
  })
  check('video lightbox: <video controls> with controlsList=nodownload', vid && vid.controls && vid.controlsList === 'nodownload', JSON.stringify(vid))
  if (vid) {
    cm = await rightClickAt(vid.x, vid.y)
    check('lightbox video: right-click is cancelled', cm && cm.p === true, JSON.stringify(cm))
    const played = await page.evaluate(async () => {
      const v = document.querySelector('[role=dialog][aria-label="Photo viewer"] video')
      for (let i = 0; i < 40 && v.readyState < 2; i += 1) await new Promise((r) => setTimeout(r, 100))
      try { await v.play() } catch (e) { return { err: String(e), ready: v.readyState } }
      await new Promise((r) => setTimeout(r, 1200))
      return { t: v.currentTime, ready: v.readyState, paused: v.paused }
    })
    check('video still plays (currentTime advances)', played.t > 0.3, JSON.stringify(played))
    const vSpace = await page.evaluate(() => document.querySelector('[role=dialog][aria-label="Photo viewer"] header button[aria-label*="slideshow"]') === null)
    check('video slide: slideshow button hidden, native controls own Space', vSpace)
  }
  await page.keyboard.press('Escape'); await sleep(400)

  // ── 9. slideshow ──────────────────────────────────────────────────────
  await page.evaluate(() => window.scrollTo(0, document.getElementById('gallery-toolbar').offsetTop))
  await sleep(300)
  const ssBtn = await centerOf('#gallery-toolbar button[aria-label="Start slideshow"]', 0)
  await page.mouse.click(ssBtn.x, ssBtn.y)
  await sleep(1200)
  check('slideshow opens', await lightboxOpen())
  const c1 = await counter()
  const lbl = await page.evaluate(() => document.querySelector('[role=dialog][aria-label="Photo viewer"] header button')?.getAttribute('aria-label'))
  check('slideshow autoplays (Pause label shown)', lbl === 'Pause slideshow', lbl)
  await sleep(4600)
  const c2 = await counter()
  check('slideshow advances on its timer', c1 === '1 / 9' && c2 === '2 / 9', `${c1} -> ${c2}`)
  const ssImg = await page.evaluate(() => { const r = document.querySelector('[role=dialog][aria-label="Photo viewer"] img').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 } })
  cm = await rightClickAt(ssImg.x, ssImg.y)
  check('slideshow photo: right-click is cancelled', cm && cm.p === true, JSON.stringify(cm))
  await page.keyboard.press('Escape'); await sleep(400)
  check('Escape closes the slideshow', !(await lightboxOpen()))

  // ── 10. scroll + long-press (touch) ───────────────────────────────────
  const touchDrag = async (x, y, dist) => {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] })
    for (let i = 1; i <= 20; i += 1) { await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: y + (dist * i) / 20 }] }); await sleep(16) }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await sleep(900)
  }
  if (name === 'mobile') {
    await page.evaluate(() => window.scrollTo(0, 0)); await sleep(300)
    const y0 = await page.evaluate(() => window.scrollY)
    await touchDrag(195, 600, -500)
    const y1 = await page.evaluate(() => window.scrollY)
    check('touch scroll starting on the page moves it', y1 - y0 > 400, `${y0} -> ${y1}`)
    await page.evaluate(() => { document.getElementById('gallery-grid').scrollIntoView(); window.scrollBy(0, 200) }); await sleep(300)
    const g0 = await page.evaluate(() => window.scrollY)
    await touchDrag(195, 500, -400)
    const g1 = await page.evaluate(() => window.scrollY)
    check('touch scroll starting ON a photo tile scrolls smoothly (not captured)', g1 - g0 > 300, `${g0} -> ${g1}`)
    // long-press on a photo
    await page.evaluate(() => { window.__cm = []; window.__ds = [] })
    const lp = await page.evaluate(() => { const r = document.querySelectorAll('#gallery-grid [data-ky-media-guard]')[1].getBoundingClientRect(); return { x: r.x + r.width / 2, y: Math.min(Math.max(r.y + r.height / 3, 150), 600) } })
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: lp.x, y: lp.y }] })
    await sleep(1100)
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
    await sleep(500)
    const lpCm = await page.evaluate(() => ({ cm: window.__cm, ds: window.__ds }))
    const opened = await lightboxOpen()
    console.log(`INFO  long-press events: ${JSON.stringify(lpCm)} lightboxOpened=${opened}`)
    check('long-press on a photo: every contextmenu is cancelled (none un-cancelled)', lpCm.cm.every((e) => e.p === true))
    if (opened) { await page.keyboard.press('Escape'); await sleep(300) }
    const noOverlay = await page.evaluate(async () => {
      const tile = document.querySelectorAll('#gallery-grid [data-ky-media-guard]')[1]
      tile.scrollIntoView({ block: 'center' })
      await new Promise((r) => setTimeout(r, 300))
      const r = tile.getBoundingClientRect()
      const el = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
      return el === tile || tile.contains(el)
    })
    check('no invisible overlay: the point on a tile hits the tile itself', noOverlay)
  } else {
    await page.evaluate(() => window.scrollTo(0, 0)); await sleep(200)
    await page.mouse.move(600, 500)
    const y0 = await page.evaluate(() => window.scrollY)
    await page.mouse.wheel({ deltaY: 700 }); await sleep(600)
    const y1 = await page.evaluate(() => window.scrollY)
    check('wheel scroll over the page works', y1 - y0 > 500, `${y0} -> ${y1}`)
    const noOverlay = await page.evaluate(() => {
      document.getElementById('gallery-grid').scrollIntoView()
      const tile = document.querySelectorAll('#gallery-grid [data-ky-media-guard]')[0]
      const r = tile.getBoundingClientRect()
      const el = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
      return el === tile || tile.contains(el)
    })
    check('no invisible overlay: the point on a tile hits the tile itself', noOverlay)
  }

  // ── 11. legit download still works ────────────────────────────────────
  await page.evaluate(() => document.getElementById('gallery-grid').scrollIntoView()); await sleep(300)
  const dBtn = await centerOf(`${TILE} button[aria-label="Download this photo"]`, 0)
  await page.mouse.click(dBtn.x, dBtn.y)
  await sleep(1500)
  const dialog = await page.evaluate(() => {
    const dlg = [...document.querySelectorAll('[role=dialog]')].find((d) => /download/i.test(d.textContent))
    return dlg ? { text: dlg.textContent.replace(/\s+/g, ' ').slice(0, 200), buttons: [...dlg.querySelectorAll('button')].map((b) => b.textContent.trim()) } : null
  })
  console.log('INFO  download dialog:', JSON.stringify(dialog))
  check('tile Download opens the download dialog', Boolean(dialog))
  await page.screenshot({ path: path.join(SP, `qa-${name}-download-dialog.png`) })
  if (dialog) {
    const clicked = await page.evaluate(() => {
      const dlg = [...document.querySelectorAll('[role=dialog]')].find((d) => /download/i.test(d.textContent))
      const btn = dlg.querySelector('button[type=submit]') || [...dlg.querySelectorAll('button')].find((b) => /^download/i.test(b.textContent.trim()))
      btn?.click()
      return Boolean(btn)
    })
    let file = null
    for (let i = 0; i < 40 && !file; i += 1) {
      await sleep(500)
      file = fs.readdirSync(dlDir).find((f) => !f.endsWith('.crdownload'))
    }
    const bytes = file ? fs.readFileSync(path.join(dlDir, file)) : null
    check('the file really downloads (a JPEG with real bytes)', clicked && file && bytes.length > 1000 && bytes[0] === 0xff && bytes[1] === 0xd8, `${file} ${bytes?.length}`)
    await page.keyboard.press('Escape'); await sleep(300)
  }

  // lightbox Download button
  const t3 = await centerOf(TILE, 2)
  await page.mouse.click(t3.x, t3.y - t3.h / 4)
  await sleep(1000)
  const lbDlBox = await page.evaluate(() => { const b = document.querySelector('[role=dialog][aria-label="Photo viewer"] button[aria-label="Download this photo"]'); if (!b) return null; const r = b.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 } })
  if (lbDlBox) {
    await page.mouse.click(lbDlBox.x, lbDlBox.y)
    await sleep(1500)
    const state = await page.evaluate(() => {
      const dlgs = [...document.querySelectorAll('[role=dialog]')]
      const dlg = dlgs.find((d) => d.getAttribute('aria-label') !== 'Photo viewer' && /download/i.test(d.textContent))
      if (!dlg) return { dialog: false, lightbox: dlgs.length }
      const r = dlg.getBoundingClientRect()
      const top = document.elementFromPoint(r.x + r.width / 2, r.y + Math.min(40, r.height / 2))
      return { dialog: true, reachable: Boolean(top && dlg.contains(top)) }
    })
    check('lightbox Download opens the download dialog, and it is reachable', state.dialog && state.reachable, JSON.stringify(state))
    await page.screenshot({ path: path.join(SP, `qa-${name}-lightbox-download.png`) })
  }
  await page.keyboard.press('Escape'); await sleep(300)
  if (await lightboxOpen()) { await page.keyboard.press('Escape'); await sleep(300) }

  const realErrors = errors.filter((e) => !/favicon|Failed to load resource.*(401|404)|net::ERR/.test(e))
  check('no page errors in the console', realErrors.length === 0, realErrors.slice(0, 3).join(' | '))
  await page.close()
}

try {
  for (const name of ONLY ? [ONLY] : ['desktop', 'mobile']) await runViewport(name)
} finally {
  await browser.close()
  fs.writeFileSync(path.join(SP, `qa7d-results-${ONLY || 'all'}.json`), JSON.stringify(results, null, 2))
  const failed = results.filter((r) => !r.ok)
  console.log(`\n${results.length - failed.length}/${results.length} passed`)
  if (failed.length) console.log('FAILED:', failed.map((f) => f.name).join('; '))
}
