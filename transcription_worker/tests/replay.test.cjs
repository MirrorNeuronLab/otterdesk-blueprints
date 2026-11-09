const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const { chromium, expect } = require('@playwright/test');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');

let browser, server, root, origin;
before(async () => {
  root = await fs.mkdtemp(path.join(os.tmpdir(), 'transcribe-report-'));
  execFileSync(process.env.PYTHON || 'python3', [path.join(__dirname, 'replay_fixture.py'), root]);
  server = http.createServer(async (request, response) => {
    try {
      const name = new URL(request.url, 'http://localhost').pathname.slice(1) || 'index.html';
      if (name.includes('..')) throw new Error('Invalid path');
      const bytes = await fs.readFile(path.join(root, name));
      response.setHeader('Content-Type', name.endsWith('.wav') ? 'audio/wav' : 'text/html; charset=utf-8');
      response.setHeader('Accept-Ranges', 'bytes');
      const range = /^bytes=(\d+)-(\d*)$/.exec(request.headers.range || '');
      if (range) {
        const start = Number(range[1]), end = range[2] ? Number(range[2]) : bytes.length - 1;
        response.writeHead(206, { 'Content-Range': `bytes ${start}-${end}/${bytes.length}`, 'Content-Length': end - start + 1 });
        response.end(bytes.subarray(start, end + 1));
        return;
      }
      response.setHeader('Content-Length', bytes.length);
      response.end(bytes);
    } catch { response.writeHead(404); response.end(); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ headless: true, ...(process.env.CHROME_EXECUTABLE ? { executablePath: process.env.CHROME_EXECUTABLE } : {}) });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise(resolve => server.close(resolve));
  if (root) await fs.rm(root, { recursive: true, force: true });
});
async function open(options = {}) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 }, ...options });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(origin);
  await expect(page.getByRole('button', { name: 'Play', exact: true })).toBeVisible();
  return { page, errors };
}

test('Uses the shared shell, shows the detected speakers, and never autoplays', async () => {
  const { page, errors } = await open();
  try {
    await expect(page.getByRole('heading', { name: 'Audio transcript' })).toBeVisible();
    await expect(page.locator('.avatar')).toHaveCount(3);
    await expect(page.locator('#speaker-count')).toHaveText('3 speakers');
    assert.equal(await page.locator('audio').evaluate(audio => audio.paused), true);
    await expect(page.locator('.avatar[data-speaking="true"]')).toHaveCount(0);
    await page.getByRole('button', { name: 'Actions', exact: true }).click();
    await page.getByRole('menuitem', { name: 'Recording details' }).click();
    await expect(page.getByText('Source SHA-256', { exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('#report-inspector')).not.toBeVisible();
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('Actual audio playback advances words, speaker focus, scrolling, and speed', async () => {
  const { page, errors } = await open({ reducedMotion: 'reduce' });
  try {
    await page.getByRole('button', { name: 'Play', exact: true }).click();
    await expect.poll(() => page.locator('audio').evaluate(audio => audio.currentTime)).toBeGreaterThan(.2);
    await expect(page.locator('.avatar[data-speaking="true"]')).toHaveCount(1);
    await expect.poll(() => page.locator('.word[aria-current="true"]').count()).toBeGreaterThan(0);
    await page.getByLabel('Speed', { exact: true }).selectOption('2');
    assert.equal(await page.locator('audio').evaluate(audio => audio.playbackRate), 2);
    await page.locator('audio').evaluate(audio => { audio.currentTime = 5.2; audio.dispatchEvent(new Event('timeupdate')); });
    await expect.poll(() => page.locator('#transcript').evaluate(element => element.scrollTop)).toBeGreaterThan(0);
    await page.getByRole('button', { name: 'Pause', exact: true }).click();
    await expect(page.locator('.avatar[data-speaking="true"]')).toHaveCount(0);
    const paused = await page.locator('audio').evaluate(audio => audio.currentTime);
    assert.ok(paused >= 5.2);
    await page.locator('.word').nth(10).click();
    assert.ok((await page.locator('audio').evaluate(audio => audio.currentTime)) < 1);
    assert.equal(await page.locator('audio').evaluate(audio => audio.paused), true);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('Names survive reload, are escaped, and stay scoped to their section', async () => {
  const { page, errors } = await open();
  try {
    await page.getByRole('button', { name: 'Name Speaker 1', exact: true }).click();
    const custom = '<img src=x onerror=alert(1)> A very long anonymous speaker name';
    await page.getByRole('textbox', { name: 'Name', exact: true }).fill(custom);
    await page.keyboard.press('Enter');
    await expect(page.locator('.speaker-name').first()).toHaveText(custom);
    await expect(page.locator('.utterance .name').first()).toHaveText(custom);
    assert.equal(await page.locator('.speaker-seat img').count(), 0);
    await expect(page.locator('.avatar').first()).toBeFocused();
    await page.reload();
    await expect(page.locator('.speaker-name').first()).toHaveText(custom);
    await page.getByLabel('Transcript section').selectOption('1');
    await expect(page.locator('.avatar')).toHaveCount(1);
    await expect(page.locator('.speaker-name').first()).toHaveText('Speaker 1');
    await expect(page.locator('#section-label')).toHaveText('Section 2 of 2');
    await page.getByLabel('Transcript section').selectOption('0');
    await expect(page.locator('.speaker-name').first()).toHaveText(custom);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('Seeking across sections and automatic advancement use the correct audio clock', async () => {
  const { page, errors } = await open();
  try {
    await page.getByRole('slider', { name: 'Playback position' }).evaluate(slider => {
      slider.value = '10'; slider.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await expect(page.locator('#section-label')).toHaveText('Section 2 of 2');
    await expect(page.locator('#position')).toHaveText('0:10 / 0:16');
    await page.getByRole('button', { name: 'Play', exact: true }).click();
    await expect.poll(() => page.locator('audio').evaluate(audio => audio.currentTime)).toBeGreaterThanOrEqual(2);
    await page.getByRole('button', { name: 'Pause', exact: true }).click();
    await page.getByLabel('Transcript section').selectOption('0');
    await page.getByRole('button', { name: 'Play', exact: true }).click();
    await page.locator('audio').evaluate(audio => { audio.currentTime = 7.9; });
    await expect(page.locator('#section-label')).toHaveText('Section 2 of 2');
    await expect(page.getByRole('button', { name: 'Pause', exact: true })).toBeVisible();
    await page.getByLabel('Recording', { exact: true }).selectOption('empty.html');
    await expect(page.locator('.avatar')).toHaveCount(0);
    await expect(page.getByText('No transcript text was returned for this section.')).toBeVisible();
    assert.equal(await page.locator('audio').evaluate(audio => audio.paused), true);
    assert.deepEqual(errors, []);
  } finally { await page.close(); }
});

test('Long names, empty results and repeated resizing never overflow the page', async () => {
  const { page } = await open();
  try {
    await page.locator('.avatar').first().click();
    await page.getByRole('textbox', { name: 'Name', exact: true }).fill('LongParticipantName'.repeat(4));
    await page.getByRole('button', { name: 'Save name' }).click();
    for (const width of [1440, 800, 360, 1200, 360]) {
      await page.setViewportSize({ width, height: 820 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `overflow at ${width}`);
      await expect(page.getByRole('button', { name: 'Play', exact: true })).toBeInViewport();
      const seats = await page.locator('.speaker-seat').evaluateAll(nodes => nodes.map(node => {
        const r = node.getBoundingClientRect(); return { x: r.x, right: r.right };
      }));
      assert.ok(seats.every(seat => seat.x >= 0 && seat.right <= width));
    }
    if (process.env.REPORT_SCREENSHOT) await page.screenshot({ path: process.env.REPORT_SCREENSHOT, fullPage: true });
    await page.getByLabel('Recording', { exact: true }).selectOption('empty.html');
    await expect(page.getByText('No transcript text was returned for this section.')).toBeVisible();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  } finally { await page.close(); }
});

test('Unavailable audio gives a recovery action without fabricating playback', async () => {
  const { page } = await open();
  try {
    await page.route('**/*.wav', route => route.abort());
    await page.getByRole('button', { name: 'Play', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText("Couldn't");
    await expect(page.locator('.avatar[data-speaking="true"]')).toHaveCount(0);
  } finally { await page.close(); }
});

test('Eight detected voices fit around the table and overlapping speakers all highlight', async () => {
  const { page } = await open({ viewport: { width: 360, height: 900 } });
  try {
    await page.goto(origin + '/many.html');
    await expect(page.locator('.avatar')).toHaveCount(8);
    const rectangles = await page.locator('.avatar').evaluateAll(nodes => nodes.map(node => {
      const r = node.getBoundingClientRect(); return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
    }));
    for (const [i, a] of rectangles.entries()) for (const b of rectangles.slice(i + 1)) {
      assert.ok(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top, 'avatars overlap');
    }
    await page.getByRole('button', { name: 'Play', exact: true }).click();
    await expect(page.locator('.avatar[data-speaking="true"]')).toHaveCount(8);
    await page.getByRole('button', { name: 'Pause', exact: true }).click();
    await expect(page.locator('.avatar[data-speaking="true"]')).toHaveCount(0);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  } finally { await page.close(); }
});

test('Manual scrolling releases following and the control restores it', async () => {
  const { page } = await open();
  try {
    await page.locator('#transcript').dispatchEvent('wheel', { deltaY: 100 });
    await expect(page.getByRole('button', { name: 'Follow transcript' })).toHaveAttribute('aria-pressed', 'false');
    await page.getByRole('button', { name: 'Follow transcript' }).click();
    await expect(page.getByRole('button', { name: 'Follow transcript' })).toHaveAttribute('aria-pressed', 'true');
  } finally { await page.close(); }
});
