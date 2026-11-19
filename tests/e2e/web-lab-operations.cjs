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
  const browser = await chromium.launch({headless:true,args:['--enable-unsafe-swiftshader']});
  const lines = readline.createInterface({input:process.stdin});
  const input = lines[Symbol.asyncIterator]();
  const errors = [];
  try {
    const page = await browser.newPage({viewport:{width:1280,height:850},reducedMotion:'no-preference'});
    page.setDefaultTimeout(10000);
    page.on('response', response => { if(response.status() >= 400) console.error(response.status(), response.url()); });
    page.on('pageerror', error => {errors.push(error.message); console.error(error.message);});
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    const sockets = [];
    const foreignRequests = [];
    const origin = new URL(process.argv[2]).origin;
    page.on('request', request => {
      if (request.url().startsWith('http') && new URL(request.url()).origin !== origin) {
        foreignRequests.push(request.url());
      }
    });
    page.on('websocket', socket => sockets.push(socket));
    await page.goto(process.argv[2]);
    const canvas = page.getByRole('img', {name:'3D lab deck'});
    const plate = page.getByRole('combobox', {name:'Plate',exact:true});
    const well = page.getByRole('combobox', {name:'Well',exact:true});
    const detail = page.locator('#well-detail');
    const tipCount = page.locator('#tip-count');
    const target = page.locator('#deck-target');
    await canvas.waitFor();
    await page.locator('#status').filter({hasText:'Planning'}).waitFor();
    assert(await plate.isHidden() && await tipCount.isHidden());
    assert.deepEqual(await page.locator('#deck-labels span:visible').allTextContents(), []);
    console.log('planning');
    await page.locator('#status').filter({hasText:'Running'}).waitFor();
    await tipCount.filter({hasText:'96 unused tips'}).waitFor();
    const deck = await page.locator('.deck-panel').boundingBox();
    const stream = await page.getByRole('region', {name:'Event stream'}).boundingBox();
    assert(stream.y >= deck.y + deck.height, 'The event stream must be below the simulation');
    assert.equal(sockets.length, 1);
    assert(sockets[0].url().endsWith('/ws/monitor/ws'), 'Monitor must use the Job proxy');

    await canvas.focus();
    const initial = await canvas.screenshot();
    await canvas.press('ArrowLeft');
    assert(!(await canvas.screenshot()).equals(initial), 'Rotating the camera must change the scene');
    await page.getByRole('button', {name:'Zoom in'}).click();
    await page.getByRole('button', {name:'Fit deck'}).click();

    async function inspect(address, volume) {
      const [plateName, wellName] = address.split('/');
      await plate.selectOption(plateName);
      await well.selectOption(wellName);
      await detail.filter({hasText:`${address}: ${volume} µL ·`}).waitFor();
    }

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
        await page.locator('#operation').waitFor({state:'hidden'});
        await target.waitFor({state:'hidden'});
        break;
      }
      await page.waitForFunction(label => document.getElementById('operation-label').textContent === label, expected.operation.label);
      await page.waitForFunction(({steps_completed,steps_total}) => document.getElementById('progress').textContent === `${steps_completed} / ${steps_total}`, expected);
      await tipCount.filter({hasText:`${expected.tips_remaining} unused tips`}).waitFor();
      const {kind, tip_index, well: targetWell} = expected.operation;
      const active = kind === 'pick_up_tip' ? `Tip ${'ABCDEFGH'[tip_index % 8]}${Math.floor(tip_index / 8) + 1}`
        : kind === 'discard_tip' ? 'Waste' : targetWell;
      if (active) await target.filter({hasText:active}).waitFor();
      else await target.waitFor({state:'hidden'});
      for (const [address, volume] of Object.entries(expected.wells)) await inspect(address, volume);
      if (count === 2) await page.screenshot({path:path.join(process.argv[3], 'live.png')});
      if (expected.operation.label.startsWith('Mix 1/')) {
        for (const width of [320,1280,360]) {
          await page.setViewportSize({width,height:850});
          await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth);
          await canvas.waitFor();
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
    await inspect('readout/B1', 40);
    const closed = new Promise(resolve => sockets.at(-1).once('close', resolve));
    console.log('terminal');
    assert.equal(JSON.parse((await input.next()).value).closed, true);
    await closed;
    assert.equal(await page.locator('#status').textContent(), 'Completed');
    assert(await page.locator('#connection').isHidden(), 'Normal cleanup must not show a reconnect error');
    assert.equal(errors.length, 0, errors.join('\n'));
    assert(count >= 70, 'Must observe all transfers, mixes and checks');
    assert.equal(warnings, 2);
    await page.context().setOffline(true);
    await page.goto(pathToFileURL(path.join(process.argv[3], 'replay.html')).href);
    await canvas.waitFor();
    await inspect('source/A2', 350);
    assert.deepEqual(await plate.locator('option').allTextContents(), ['source','dilution','readout']);
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
    await inspect('readout/B1', 40);
    await detail.filter({hasText:'readout/B1: 40 µL · diluent'}).waitFor();
    await page.screenshot({path:path.join(process.argv[3], 'replay.png')});
    await page.goto(pathToFileURL(path.join(process.argv[3], 'empty.html')).href);
    await page.getByText('Needs review', {exact:true}).waitFor();
    assert(await page.getByRole('button', {name:'Play',exact:true}).isDisabled());
    await page.getByText('Clarify the procedure before starting.', {exact:true}).waitFor();
    assert(await plate.isHidden() && await tipCount.isHidden());

    const withoutWebGL = await browser.newPage({offline:true});
    await withoutWebGL.addInitScript(() => {
      const getContext = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function(type, ...args) {
        return type === 'webgl2' ? null : getContext.call(this, type, ...args);
      };
    });
    await withoutWebGL.goto(pathToFileURL(path.join(process.argv[3], 'replay.html')).href);
    await withoutWebGL.getByText('3D view unavailable in this browser.', {exact:true}).waitFor();
    await withoutWebGL.getByRole('combobox', {name:'Well',exact:true}).selectOption('A2');
    await withoutWebGL.locator('#well-detail').filter({hasText:'source/A2: 350 µL'}).waitFor();
    await withoutWebGL.close();

    assert.deepEqual(foreignRequests, []);
    assert.equal(errors.length, 0, errors.join('\n'));
    console.log('verified');
  } finally {
    lines.close();
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
