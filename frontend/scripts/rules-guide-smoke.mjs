import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { rulesGuide } from '../src/constants/rulesGuide.js'

const base = process.env.RULES_URL || 'http://127.0.0.1:5178/'
const profile = await mkdtemp(join(tmpdir(), 'mahjong-rules-'))
const chrome = spawn(process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
  '--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-pipe', `--user-data-dir=${profile}`, 'about:blank',
], { windowsHide: true, stdio: ['ignore', 'ignore', 'ignore', 'pipe', 'pipe'] })
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
let sessionId, nextId = 0, buffer = ''
const pending = new Map(), errors = []
chrome.stdio[4].on('data', chunk => {
  buffer += chunk.toString()
  let end
  while ((end = buffer.indexOf('\0')) !== -1) {
    const message = JSON.parse(buffer.slice(0, end))
    buffer = buffer.slice(end + 1)
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails)
    const waiter = pending.get(message.id)
    if (!waiter) continue
    clearTimeout(waiter.timer); pending.delete(message.id)
    message.error ? waiter.reject(new Error(message.error.message)) : waiter.resolve(message.result)
  }
})
async function until(fn) {
  const deadline = Date.now() + 20000
  while (Date.now() < deadline) {
    const result = await fn()
    if (result) return result
    await pause(50)
  }
  throw new Error('Rules guide browser check timed out')
}
function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++nextId
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)) }, 15000)
    pending.set(id, { resolve, reject, timer })
    chrome.stdio[3].write(JSON.stringify({ id, method, params, sessionId }) + '\0')
  })
}
async function evaluate(expression) {
  const result = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails))
  return result.result.value
}
const atPage = page => until(() => evaluate(`document.querySelector('[data-guide-page="${page}"]') !== null`))
try {
  const { targetId } = await command('Target.createTarget', { url: 'about:blank' })
  ;({ sessionId } = await command('Target.attachToTarget', { targetId, flatten: true }))
  await command('Runtime.enable')
  await command('Page.enable')
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  await command('Page.navigate', { url: `${base}#/rules` })
  await atPage(1)
  assert.equal(await evaluate(`document.querySelector('.guide-pagination button').disabled`), true)
  for (let index = 0; index < rulesGuide.length; index++) {
    const result = await evaluate(`(() => {
      const article=document.querySelector('.guide-lesson');
      return {title:article.querySelector('h2').textContent, tiles:article.querySelectorAll('.mahjong-tile').length,
        text:article.innerText, overflow:document.documentElement.scrollWidth>innerWidth,
        primary:document.querySelectorAll('.rules-guide .ui-btn--primary').length,
        buttons:[...document.querySelectorAll('.guide-pagination .ui-btn')].every(el=>el.getBoundingClientRect().height>=44)};
    })()`)
    assert.equal(result.title, rulesGuide[index].title)
    assert.ok(result.tiles > 0, `Page ${index + 1} lacks example tiles`)
    for (const section of rulesGuide[index].sections) {
      for (const paragraph of section.paragraphs) assert.ok(result.text.includes(paragraph), `Missing text on page ${index + 1}`)
    }
    assert.equal(result.overflow, false, `Mobile overflow on page ${index + 1}`)
    assert.equal(result.primary, 1)
    assert.equal(result.buttons, true)
    if (index < rulesGuide.length - 1) {
      await evaluate(`document.querySelector('.guide-pagination .ui-btn--primary').click()`)
      await atPage(index + 2)
    }
  }
  await evaluate(`document.querySelector('.guide-directory').open=true; document.querySelectorAll('.guide-directory button')[7].click()`)
  await atPage(8)
  assert.equal(await evaluate(`document.querySelector('.guide-directory').open`), false)
  assert.deepEqual(await evaluate(`[...document.querySelectorAll('.guide-tiles .mahjong-tile')].map(tile=>!!tile.dataset.faceDown)`), [true, false, true, true])
  await command('Page.reload')
  await atPage(8)
  assert.ok(await evaluate(`location.hash.endsWith('page=8')`))
  await command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight' })
  await atPage(9)
  await command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowLeft' })
  await atPage(8)
  await evaluate(`document.querySelector('.guide-pagination button').click()`)
  await atPage(7)
  for (const width of [320, 1280]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 600 })
    assert.equal(await evaluate(`document.documentElement.scrollWidth>innerWidth`), false, `Overflow at ${width}px`)
  }
  // A fresh invalid bookmark falls back to the first chapter.
  await command('Page.navigate', { url: `${base}#/rules?page=999` })
  await atPage(1)
  if (process.env.RULES_CAPTURE) {
    await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
    const shot = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
    await writeFile(process.env.RULES_CAPTURE, Buffer.from(shot.data, 'base64'))
  }
  assert.deepEqual(errors, [], 'Browser runtime exceptions')
  console.log(`PASS: ${rulesGuide.length} chapters render with all text and tiles; next/previous, directory, keyboard, reload, invalid query, dark kong and 320/390/1280px layouts.`)
} finally {
  for (const waiter of pending.values()) clearTimeout(waiter.timer)
  chrome.kill()
}
