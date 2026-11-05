// Run via web-lab-operations.py. Uses the desktop's declared Playwright dependency.
'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const readline = require('node:readline');
const {createRequire} = require('node:module');
const app = process.env.OTTERDESK_APP_ROOT || path.resolve(__dirname, '../../../otterdesk-desktop-app');
const {chromium} = createRequire(path.join(app, 'package.json'))('playwright');

(async () => {
  const browser = await chromium.launch({headless:true});
  const lines = readline.createInterface({input:process.stdin});
  const input = lines[Symbol.asyncIterator]();
  const errors = [];
  try {
    const page = await browser.newPage({viewport:{width:1280,height:850}});
    page.setDefaultTimeout(10000);
    page.on('response', response => { if(response.status() >= 400) console.error(response.status(), response.url()); });
    page.on('pageerror', error => {errors.push(error.message); console.error(error.message);});
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    const sockets = [];
    const images = [];
    page.on('request', request => {
      if (request.resourceType() === 'image') images.push(request.response().then(response => response?.finished()));
    });
    page.on('websocket', socket => sockets.push(socket.url()));
    await page.goto(process.argv[2]);
    await page.locator('#status').filter({hasText:'Running'}).waitFor();
    const frame = page.frames().find(value => value.url().includes('/visualizer/'));
    await frame.locator('#status-label').filter({hasText:'Connected'}).waitFor();
    await frame.waitForFunction(() => Boolean(resources.destination));
    assert(sockets.some(url => url.endsWith('/ws/monitor/ws')), 'Monitor must use the Job proxy');
    assert(sockets.some(url => url.endsWith('/ws/visualizer/ws')), 'Native canvas must use the Job proxy');
    console.log('ready');
    let count = 0;
    for (;;) {
      const line = await input.next();
      assert(!line.done, 'Expected the next simulation observation');
      const expected = JSON.parse(line.value);
      if (expected.done) {
        await page.locator('#status').filter({hasText:'Completed'}).waitFor();
        await frame.locator('#status-label').filter({hasText:'Completed'}).waitFor();
        await page.locator('#operation').waitFor({state:'hidden'});
        break;
      }
      await page.waitForFunction(label => document.getElementById('operation-label').textContent === label, expected.operation.label);
      await page.waitForFunction(count => document.getElementById('progress').textContent === `${count} / 2 steps completed`, expected.steps_completed);
      await frame.waitForFunction(({wells, resource}) => {
        const volumesMatch = Object.entries(wells).every(([name, volume]) =>
          Math.abs(resources[name]?.volume - volume) < 1e-6);
        const markers = resourceLayer.find('.web-lab-operation');
        return volumesMatch && (resource ? markers.length === 1 : markers.length === 0);
      }, {wells:expected.wells,resource:expected.operation.resource});
      if (expected.operation.label.startsWith('Mix 1/')) {
        for (const width of [360,1280,360]) {
          await page.setViewportSize({width,height:850});
          await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth);
          await frame.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth && stage.scaleX() > 0);
        }
        await page.screenshot({path:path.join(process.argv[3], 'live-mix.png')});
      }
      count++;
      console.log('observed');
    }
    // A fresh page receives current completed state, without transient activity.
    await page.reload();
    await page.locator('#status').filter({hasText:'Completed'}).waitFor();
    await page.locator('#operation').waitFor({state:'hidden'});
    const finalFrame = page.frames().find(value => value.url().includes('/visualizer/'));
    await finalFrame.locator('#status-label').filter({hasText:'Completed'}).waitFor();
    await finalFrame.waitForFunction(() => Boolean(resources.destination));
    await Promise.all(images);
    console.log('terminal');
    assert.equal(JSON.parse((await input.next()).value).closed, true);
    await finalFrame.waitForFunction(() => webSocket.readyState === WebSocket.CLOSED);
    assert.equal(await finalFrame.locator('#status-label').textContent(), 'Completed');
    assert(await page.locator('#connection').isHidden(), 'Normal cleanup must not show a reconnect error');
    assert.equal(errors.length, 0, errors.join('\n'));
    assert(count >= 10, 'Must observe pickup, transfer, and each mix half-cycle');
    console.log('verified');
  } finally {
    lines.close();
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
