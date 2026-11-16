// Offline browser gate using the desktop's declared Playwright dependency.
// OTTERDESK_APP_ROOT=/path/to/otterdesk-desktop-app node tests/e2e/cctv-workspace.cjs [output-directory]
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { createRequire } = require('node:module');
const app = process.env.OTTERDESK_APP_ROOT || path.resolve(__dirname, '../../../otterdesk-desktop-app');
const { chromium } = createRequire(path.join(app, 'package.json'))('playwright');
const { expect } = createRequire(path.join(app, 'package.json'))('@playwright/test');
const assets = path.resolve(__dirname, '../../cctv_operator/payloads/web_assets');
const output = process.argv[2];
const image = '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540"><rect width="960" height="540" fill="#26313b"/><path d="M0 420L400 200H560L960 420V540H0" fill="#59636d"/><g fill="#9b8060" stroke="#26313b" stroke-width="12"><path d="M0 40H240V420H0Z M720 40H960V420H720Z"/></g><g stroke="#60717e" stroke-width="12"><path d="M0 160H240M0 280H240M720 160H960M720 280H960"/></g><circle cx="500" cy="260" r="20" fill="#c9a586"/><path d="M470 285H530L545 370H455Z" fill="#bc5156"/><path d="M478 365V440M520 365V440" stroke="#242e38" stroke-width="18"/></svg>';
const rows = Array.from({ length: 35 }, (_, i) => ({ id: `window-${i}`, start_time: new Date(Date.UTC(2026, 10, 4, 18, 0, i * 4)).toISOString(),
  end_time: new Date(Date.UTC(2026, 10, 4, 18, 0, i * 4 + 4)).toISOString(), received_at: '2026-11-04T18:02:30Z',
  content: i === 33 ? 'A person without a visible safety helmet walks through the aisle. The head is partly obscured; review the source video.' : 'A person walks through the aisle. No change in the monitored area is visible.',
  goal_match: i === 33 ? 'matched' : 'not_matched', snapshot: i === 1 ? null : { received_at: '2026-11-04T18:02:14Z', ...(i === 33 ? { bbox_2d: [470, 430, 580, 830] } : {}) }
}));
let data = { run_id: 'run', camera: 'Warehouse · aisle 3', preview: { connected: true }, has_target: true,
  session: { status: 'running', total_captions: 35, instruction_revision: 2, instruction: 'Watch for people without a visible safety helmet.', last_caption_at: '2026-11-04T18:02:30Z', inference_ms: 1930 },
  captions: rows, goal_matches: rows.filter(row => row.goal_match === 'matched'), match_count: 1, omitted_count: 0,
  history: { summary: 'Saved footage search · 35 of 35 windows indexed.' } };
let statusUnavailable = false;

async function checkPinnedPreview(page) {
  const video = await page.locator('.camera-card:visible .video-stage').first().boundingBox();
  const preview = await page.locator('.camera-card:visible .preview-badge').first().boundingBox();
  const primary = await page.locator('.workspace-primary').boundingBox();
  const events = await page.getByRole('heading', { name: /^Recent observations/ }).boundingBox();
  const timeline = await page.locator('#transcript').boundingBox();
  assert(video && preview && primary && events && timeline);
  assert(preview.x >= video.x && preview.x < video.x + 16, 'Preview label stays at the video’s left edge');
  assert(preview.y >= video.y && preview.y < video.y + 16, 'Preview label stays at the video’s top edge');
  assert(video.height > 24, 'The camera preview remains usable');
  assert(timeline.height > 0 && timeline.y + timeline.height <= page.viewportSize().height,
    `Timeline fits inside the window: ${JSON.stringify({ timeline, viewport: page.viewportSize() })}`);
  if (page.viewportSize().width >= 960) {
    assert(events.x >= primary.x + primary.width && events.y < video.y, 'Events sit to the right of the camera section');
  } else {
    assert(events.y >= video.y + video.height, 'Events sit below the video');
  }
  const size = await page.evaluate(() => ({ width: document.documentElement.scrollWidth,
    height: document.documentElement.scrollHeight, viewport: [innerWidth, innerHeight] }));
  assert(size.width <= size.viewport[0] && size.height <= size.viewport[1],
    `The page does not overflow: ${JSON.stringify(size)}`);
  await page.evaluate(() => document.getElementById('transcript').scrollTop = 0);
  await page.locator('#transcript').hover();
  await page.mouse.wheel(0, 500);
  await expect.poll(() => page.locator('#transcript').evaluate(el => el.scrollTop)).toBeGreaterThan(0);
  assert.deepEqual(await page.locator('.camera-card:visible .video-stage').first().boundingBox(), video, 'Scrolling keeps the video in place');
  assert.equal(await page.evaluate(() => scrollY), 0, 'Only the timeline scrolls');
  await page.getByRole('button', { name: 'Back to latest' }).click();
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  let page;
  try {
    page = await browser.newPage({ viewport: { width: 640, height: 1000 }, colorScheme: 'light' });
    const errors = [];
    const previewRequests = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://cctv.test/**', async route => {
      const url = new URL(route.request().url());
      const headers = { 'Content-Security-Policy': "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'" };
      if (url.pathname.endsWith('/api/status') && statusUnavailable) return route.fulfill({ status: 503, body: 'Unavailable', headers });
      if (url.pathname.endsWith('/api/status')) return route.fulfill({ json: {
        ...data, cameras: data.cameras || [{...data.session, slot: 1, camera: data.camera, preview: data.preview}],
      }, headers });
      if (url.pathname.endsWith('/api/observations')) return route.fulfill({ json: { observations: rows.slice(0, 2), omitted_count: 0 }, headers });
      if (url.pathname.endsWith('/api/preview.mjpeg')) previewRequests.push(url.searchParams.get('camera'));
      if (/snapshot.jpg$|preview.mjpeg$/.test(url.pathname)) return route.fulfill({ contentType: 'image/svg+xml', body: image, headers });
      const file = url.pathname.split('/static/')[1] || 'index.html';
      return route.fulfill({ path: path.join(assets, file), headers });
    });
    await page.goto('https://cctv.test/jobs/camera/ui/');
    await expect(page.locator('.caption')).toHaveCount(35);
    await expect(page.locator('.camera-status')).toHaveText('Running');
    const goalToggle = page.locator('summary').and(page.getByLabel('Monitoring goal', { exact: true }));
    const goal = page.getByRole('region', { name: 'Monitoring goal' });
    const video = await page.locator('.video-stage').boundingBox();
    const toggleBounds = await goalToggle.boundingBox();
    assert(video && toggleBounds && toggleBounds.y < video.y && toggleBounds.x + toggleBounds.width > video.x + video.width - 16);
    await expect(goal).toBeHidden();
    await goalToggle.press('Enter');
    await expect(goal).toContainText(data.session.instruction);
    assert.deepEqual(await page.locator('.video-stage').boundingBox(), video, 'Opening the goal keeps the video in place');
    await goalToggle.press('Space');
    await expect(goal).toBeHidden();
    await expect(page.locator('.preview-state')).toBeHidden();
    await checkPinnedPreview(page);
    await expect(page.locator('.caption .snapshot')).toHaveCount(34);
    const first = page.locator('.caption').first();
    await first.getByRole('button', { name: /View saved frame/ }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).not.toBeVisible();
    await page.getByRole('radio', { name: 'Goal matches' }).check();
    await expect(page.locator('.caption')).toHaveCount(1);
    await expect(page.getByText('View highlighted frame')).toBeVisible();
    await page.getByRole('button', { name: /View saved frame/ }).click();
    await expect(page.locator('#evidence-caption')).toContainText('Box estimated on this image.');
    await page.getByRole('button', { name: 'Close', exact: true }).click();
    await expect(page.getByRole('button', { name: /View saved frame/ })).toBeFocused();
    await page.getByRole('radio', { name: 'Everything' }).check();
    await first.getByText('Analysis details', { exact: true }).click();
    await expect(first.locator('details[open]')).toBeVisible();
    await page.evaluate(() => document.getElementById('transcript').scrollTop = 500);
    const anchor = await page.locator('#transcript').evaluate(el => el.scrollTop);
    data = { ...data, captions: [...rows, { ...rows[34], id: 'new', content: 'New observation.' }] };
    await expect(page.locator('.caption')).toHaveCount(36);
    assert((await page.locator('#transcript').evaluate(el => el.scrollTop)) > anchor);
    await expect(page.locator('[data-id="window-34"] details')).toHaveAttribute('open', '');
    await page.getByRole('button', { name: 'Back to latest' }).click();
    data = { ...data, omitted_count: 2 };
    await page.getByRole('button', { name: 'Show earlier' }).click();
    await expect(page.locator('.caption')).toHaveCount(2);
    await expect(page.locator('#transcript')).toBeFocused();
    await page.getByRole('button', { name: 'Back to latest' }).click();
    await expect(page.locator('.caption')).toHaveCount(36);
    data = { ...data, omitted_count: 0 };
    for (const [width, height] of [[1440, 1000], [215, 480], [360, 450], [320, 640], [640, 700], [1440, 480], [320, 640], [1440, 1000]]) {
      await page.setViewportSize({ width, height });
      await checkPinnedPreview(page);
      await expect(page.getByRole('link', { name: 'Export observations' })).toBeVisible();
      if (output && (width === 320 || width === 1440)) {
        await fs.mkdir(output, { recursive: true });
        await page.screenshot({ path: path.join(output, `workspace-${width}.png`), fullPage: true });
      }
    }
    data = { ...data, camera: 'Warehouse-camera-with-a-very-long-name-'.repeat(20), session: { ...data.session, instruction: 'LongGoal'.repeat(500) } };
    await expect(page.locator('.camera-card')).toHaveAttribute('title', data.camera);
    await expect(page.locator('.camera-card')).toHaveAttribute('aria-label', `Live video · ${data.camera}`);
    for (const width of [215, 1440, 320]) {
      await page.setViewportSize({ width, height: 900 });
      await checkPinnedPreview(page);
      await goalToggle.click();
      await expect(goal).toContainText(data.session.instruction);
      await expect(goal).toBeInViewport({ ratio: 1 });
      await goalToggle.click();
      await expect(goal).toBeHidden();
    }
    data = { ...data, has_target: false, goal_matches: [], match_count: 0 };
    await page.getByRole('radio', { name: 'Goal matches' }).check();
    await expect(page.locator('#empty')).toHaveText('Set a monitoring goal in Chat to see matches here.');
    data = { ...data, has_target: true };
    await expect(page.locator('#empty')).toHaveText('No matches reported for this goal yet.');
    data = { ...data, captions: [{ ...rows[0], id: 'untrusted', content: '<img src=x onerror=alert(1)>', snapshot: null }] };
    await page.getByRole('radio', { name: 'Everything' }).check();
    await expect(page.locator('.caption')).toHaveCount(1);
    await expect(page.locator('.caption-excerpt')).toHaveText('<img src=x onerror=alert(1)>');
    await expect(page.locator('.caption img')).toHaveCount(0);
    data = { ...data, captions: [] };
    await expect(page.locator('#empty')).toHaveText('No completed video observations yet.');
    await expect(page.locator('#transcript')).toBeHidden();
    data = { ...data, preview: { connected: false } };
    await expect(page.locator('.preview-state')).toBeVisible();
    await expect(page.locator('.preview-state')).toHaveText('Connecting to live video…');
    data = { ...data, preview: { connected: false, error: 'Preview disconnected.' },
      session: { ...data.session, status: 'error', error: 'Video analysis needs attention.' } };
    await expect(page.locator('.preview-state')).toHaveText('Video analysis needs attention.');
    await expect(page.locator('.camera-status')).toHaveText('Needs review');
    await expect(page.getByRole('alert')).toHaveText('Video analysis needs attention.');
    data = { ...data, preview: { connected: true }, session: { ...data.session, status: 'running', error: null } };
    await expect(page.locator('.preview-state')).toBeHidden();
    await expect(page.getByRole('alert')).toBeHidden();
    data = {
      ...data, session: { ...data.session, status: 'degraded', instruction: 'Watch for activity near the entrance' },
      cameras: [1, 2, 3, 4].map(slot => ({
        slot, camera: `Camera ${slot}`, status: slot === 4 ? 'error' : 'running',
        preview: { connected: slot !== 4 }, error: slot === 4 ? 'Video analysis disconnected.' : null,
      })),
      captions: rows.map((row, index) => ({ ...row, camera: `Camera ${index % 4 + 1}` })),
      goal_matches: [{ ...rows[33], camera: 'Camera 2' }], match_count: 1,
    };
    const liveCameras = page.getByRole('group', { name: 'Live cameras' });
    await expect(liveCameras.getByRole('region')).toHaveCount(4);
    await expect(page.locator('#preview-count')).toHaveText('3 / 4');
    await expect(page.locator('#attention-count')).toHaveText('1');
    await expect(page.locator('#monitor-status')).toHaveText('Needs review');
    await expect(page.locator('#observation-count')).toHaveText('35');
    await expect(page.locator('#match-count')).toHaveText('1');
    const selector = page.getByRole('combobox', { name: 'Preview camera' });
    await expect(selector).toBeEnabled();
    for (let slot = 1; slot <= 4; slot++) {
      const tile = liveCameras.getByRole('region', { name: `Live video · Camera ${slot}`, exact: true });
      await expect(tile.getByRole('img')).toHaveAttribute('src', `api/preview.mjpeg?camera=${slot}`);
      await expect(tile.locator('.camera-status')).toHaveText(slot === 4 ? 'Needs review' : 'Running');
      await expect(tile.locator('.preview-badge')).toHaveText(slot === 4 ? 'Connecting' : 'Live preview');
    }
    await expect(page.locator('.caption-camera').first()).toHaveText('Camera 3');
    for (const [width, height] of [[1440, 1000], [215, 480], [360, 450], [320, 640], [360, 800], [1440, 480], [1440, 1000]]) {
      await page.setViewportSize({ width, height });
      await expect(liveCameras).toBeInViewport({ ratio: 1 });
      for (const focus of await liveCameras.getByRole('button', { name: /Focus preview/ }).all()) {
        await expect(focus).toBeInViewport({ ratio: 1 });
      }
      await expect(page.getByRole('link', { name: 'Export observations' })).toBeVisible();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth
        && document.documentElement.scrollHeight <= innerHeight), 'The four-camera layout does not overflow');
      await checkPinnedPreview(page);
      if (output && height > 600 && [320, 360, 1440].includes(width)) {
        await page.screenshot({ path: path.join(output, `workspace-four-${width}.png`), fullPage: true });
      }
    }
    await selector.selectOption('3');
    await expect(liveCameras.getByRole('region')).toHaveCount(1);
    await expect(liveCameras.getByRole('region')).toHaveAccessibleName('Live video · Camera 3');
    await expect(page.locator('.caption')).toHaveCount(35);
    await page.setViewportSize({ width: 360, height: 800 });
    await checkPinnedPreview(page);
    await liveCameras.getByRole('button', { name: 'Show all cameras' }).click();
    await expect(liveCameras.getByRole('region')).toHaveCount(4);
    await liveCameras.getByRole('button', { name: 'Focus preview · Camera 2', exact: true }).press('Enter');
    await expect(selector).toHaveValue('2');
    await expect(liveCameras.getByRole('region')).toHaveAccessibleName('Live video · Camera 2');
    await selector.selectOption('all');
    await liveCameras.getByRole('button', { name: 'Focus preview · Camera 4', exact: true }).click();
    await expect(selector).toHaveValue('4');
    await expect(liveCameras.getByRole('region')).toHaveAccessibleName('Live video · Camera 4');
    await liveCameras.getByRole('button', { name: 'Show all cameras' }).click();
    assert.deepEqual(previewRequests, ['1', '2', '3', '4'], 'Polling, focusing and resizing reuse the four preview streams');
    // Both intermediate camera counts render all selected sources, with no phantom tiles.
    for (const count of [3, 2]) {
      data = { ...data, cameras: data.cameras.slice(0, count) };
      await expect(liveCameras.getByRole('region')).toHaveCount(count);
      await expect(selector.locator('option')).toHaveCount(count + 1);
      await checkPinnedPreview(page);
    }
    await selector.selectOption('2');
    data = { ...data, cameras: data.cameras.slice(0, 1) };
    await expect(selector).toHaveValue('all');
    await expect(selector).toBeDisabled();
    await expect(liveCameras.getByRole('region')).toHaveAccessibleName('Live video · Camera 1');
    await expect(page.locator('#attention-count')).toHaveText('0');
    // A preview-only failure must not mislabel healthy analysis or other cameras.
    data = { ...data, session: { ...data.session, status: 'running' },
      cameras: [{ ...data.cameras[0], preview: { connected: false, error: 'Preview disconnected.' } }] };
    await expect(page.locator('#attention-count')).toHaveText('1');
    await expect(page.locator('.camera-status')).toHaveText('Running');
    await expect(page.locator('.preview-badge')).toHaveText('Preview unavailable');
    await expect(page.locator('.preview-state')).toHaveText('Preview disconnected.');
    statusUnavailable = true;
    await expect(page.locator('#monitor-status')).toHaveText('Reconnecting');
    await expect(page.getByRole('alert')).toHaveText("Couldn't refresh camera status. Reconnecting…");
    statusUnavailable = false;
    data = { ...data, cameras: [{ ...data.cameras[0], preview: { connected: true } }] };
    await expect(page.locator('#monitor-status')).toHaveText('Running');
    await expect(page.getByRole('alert')).toBeHidden();
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.setViewportSize({ width: 1440, height: 900 });
    await checkPinnedPreview(page);
    await page.setViewportSize({ width: 320, height: 640 });
    await checkPinnedPreview(page);
    assert.deepEqual(errors, []);
    console.log('CCTV workspace passed for one to four cameras, including summary counts, preview selection, evidence, camera-specific status, and narrow/wide resizing.');
  } catch (error) {
    if (output && page) {
      await fs.mkdir(output, { recursive: true });
      await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true });
    }
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
