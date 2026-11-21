// Exercise a running Web Lab validation job through its workspace URL.
const assert = require('node:assert/strict');
const {mkdir} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require(path.resolve(__dirname, '../../../otterdesk-desktop-app/node_modules/playwright'));

async function main() {
  const [url, screenshots] = process.argv.slice(2);
  assert(url, 'Pass a running Web Lab workspace URL');
  if (screenshots) await mkdir(screenshots, {recursive: true});
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 900}});
    page.setDefaultTimeout(20000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const button = name => page.getByRole('button', {name, exact: true});
    const waitForText = (locator, value) => locator.filter({hasText: value}).waitFor();
    const waitLive = () => waitForText(page.locator('#connection'), /^Live$/);
    const sampleStatus = page.locator('#sample-status');
    const observed = () => page.locator('#sample-wells .observed').allTextContents();

    await page.goto(url);
    await waitLive();
    await page.getByRole('img', {name: 'Overview camera of the simulated workcell'}).waitFor();
    await page.waitForFunction(() => document.querySelector('#frame').naturalWidth > 0);
    await sampleStatus.filter({hasText: /^Passed$/}).waitFor({timeout: 120000});
    assert.deepEqual(await observed(), ['100%', '50%', '25%', '12.5%', '0%']);
    assert.deepEqual(await page.locator('#sample-wells .check').allTextContents(), Array(5).fill('Match'));
    assert.equal(await button('Move joint').count(), 0);
    if (screenshots) await page.screenshot({path: path.join(screenshots, 'mk3-overview.png')});

    await button('Sample tray').click();
    await page.getByRole('img', {name: 'Sample tray camera of the simulated workcell'}).waitFor();
    await page.waitForFunction(() => document.querySelector('#frame').naturalWidth > 0);
    if (screenshots) await page.screenshot({path: path.join(screenshots, 'mk3-sample-tray.png')});

    await button('Run sample again').click();
    await waitForText(sampleStatus, /^Running$/);
    assert.deepEqual(await observed(), ['100%', '0%', '0%', '0%', '0%']);
    await button('Stop sample').click();
    await waitForText(sampleStatus, /^Stopped$/);
    const stopped = await observed();
    await page.reload();
    await waitLive();
    await waitForText(sampleStatus, /^Stopped$/);
    assert.deepEqual(await observed(), stopped);
    await page.getByText('Recent controls', {exact: true}).click();
    await page.getByText('Stopped dye dilution', {exact: true}).waitFor();

    for (const width of [360, 1280, 360, 1280]) {
      await page.setViewportSize({width, height: 900});
      await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth);
      await button('Run sample again').waitFor();
    }
    assert.deepEqual(errors, []);
    console.log('Verified MK3 views, reference checks, stop, replay, reconnect and resizing.');
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
