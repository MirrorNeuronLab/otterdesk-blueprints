// Run via web-lab-operations.py. Uses the desktop's declared Playwright dependency.
'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const readline = require('node:readline');
const {pathToFileURL} = require('node:url');
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
    await frame.waitForFunction(() => Boolean(resources.readout) && webSocket.readyState === WebSocket.OPEN);
    assert(await frame.locator('nav.navbar').isHidden());
    assert(await frame.locator('#sidepanel').isHidden());
    const deck = await page.locator('.deck-panel').boundingBox();
    const stream = await page.getByRole('region', {name:'Event stream'}).boundingBox();
    assert(stream.y >= deck.y + deck.height, 'The event stream must be below the simulation');
    assert(sockets.some(url => url.endsWith('/ws/monitor/ws')), 'Monitor must use the Job proxy');
    assert(sockets.some(url => url.endsWith('/ws/visualizer/ws')), 'Native canvas must use the Job proxy');
    console.log('ready');
    let count = 0;
    let warnings = 0;
    for (;;) {
      const line = await input.next();
      assert(!line.done, 'Expected the next simulation observation');
      const expected = JSON.parse(line.value);
      if (expected.risks) {
        for (const risk of expected.risks) {
          await page.getByText(risk.message, {exact:true}).waitFor();
          warnings++;
        }
        console.log('warned');
        continue;
      }
      if (expected.done) {
        await page.locator('#status').filter({hasText:'Completed'}).waitFor();
        await frame.waitForFunction(() => document.getElementById('status-label').textContent === 'Completed');
        await page.locator('#operation').waitFor({state:'hidden'});
        break;
      }
      await page.waitForFunction(label => document.getElementById('operation-label').textContent === label, expected.operation.label);
      await page.waitForFunction(({steps_completed,steps_total}) => document.getElementById('progress').textContent === `${steps_completed} / ${steps_total}`, expected);
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
    await finalFrame.waitForFunction(() => Boolean(resources.readout) && document.getElementById('status-label').textContent === 'Completed');
    await Promise.all(images);
    console.log('terminal');
    assert.equal(JSON.parse((await input.next()).value).closed, true);
    await finalFrame.waitForFunction(() => webSocket.readyState === WebSocket.CLOSED);
    assert.equal(await finalFrame.locator('#status-label').textContent(), 'Completed');
    assert(await page.locator('#connection').isHidden(), 'Normal cleanup must not show a reconnect error');
    assert.equal(errors.length, 0, errors.join('\n'));
    assert(count >= 70, 'Must observe all transfers, mixes and checks');
    assert.equal(warnings, 2);
    await page.goto(pathToFileURL(path.join(process.argv[3], 'replay.html')).href);
    await page.locator('.well').first().waitFor();
    assert.equal(await page.locator('#events li').count(), 0);
    await page.getByRole('button', {name:'Next', exact:true}).click();
    await page.getByText('Transferred 320 uL from source/A2 to dilution/A1.', {exact:true}).waitFor();
    assert.equal(await page.locator('#events > .warning').count(), 1);
    await page.getByRole('slider', {name:'Observation'}).focus();
    await page.getByRole('slider', {name:'Observation'}).press('End');
    await page.getByText('Completed', {exact:true}).waitFor();
    assert.equal(await page.locator('#events > .warning').count(), 2);
    assert.equal(await page.locator('#progress').textContent(), '20 / 20');
    for (const width of [360,1280,360,1280]) {
      await page.setViewportSize({width,height:850});
      await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth);
      const deck = await page.locator('.deck-panel').boundingBox();
      const stream = await page.getByRole('region', {name:'Event stream'}).boundingBox();
      assert(stream.y >= deck.y + deck.height);
    }
    await page.getByRole('button', {name:'readout/B1: 40 uL; diluent', exact:true}).click();
    await page.locator('#well-detail').filter({hasText:'readout/B1: 40 uL; diluent'}).waitFor();
    await page.screenshot({path:path.join(process.argv[3], 'replay.png')});
    await page.goto(pathToFileURL(path.join(process.argv[3], 'empty.html')).href);
    await page.getByText('Needs review', {exact:true}).waitFor();
    assert(await page.getByRole('button', {name:'Play',exact:true}).isDisabled());
    await page.getByText('Clarify the procedure before starting.', {exact:true}).waitFor();
    assert.equal(errors.length, 0, errors.join('\n'));
    console.log('verified');
  } finally {
    lines.close();
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
