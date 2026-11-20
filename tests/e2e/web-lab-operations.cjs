// Exercise a running Web Lab validation job through its workspace URL.
const assert = require('node:assert/strict');
const {mkdir} = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require(path.resolve(__dirname, '../../../otterdesk-desktop-app/node_modules/playwright'));

async function main() {
  const [url, screenshots] = process.argv.slice(2);
  assert(url, 'Pass a running Web Lab workspace URL');
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({viewport: {width: 1280, height: 900}});
    page.setDefaultTimeout(20000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const button = name => page.getByRole('button', {name, exact: true});
    const reading = name => page.locator('[data-reading="' + name + '"]');
    const waitForText = (locator, value) => locator.filter({hasText: value}).waitFor();
    const waitLive = () => waitForText(page.locator('#connection'), /^Live$/);
    const waitReady = () => waitForText(page.locator('#motion'), /^Ready$/);

    await page.goto(url);
    await waitLive();
    await page.getByRole('img', {name: 'Overview camera of the simulated workcell'}).waitFor();
    await page.waitForFunction(() => document.querySelector('#frame').naturalWidth > 0);
    await button('Home arm').click();
    await waitReady();
    await waitForText(reading('lift'), /^450 mm$/);
    if (await button('Close lid').isVisible()) {
      await button('Close lid').click();
      await waitForText(reading('lid'), /^0°$/);
    }
    if (await button('Turn light off').isVisible()) {
      await button('Turn light off').click();
      await waitForText(page.locator('#light-state'), /^Off$/);
    }
    await page.locator('#command-feedback').filter({hasText: /^$/}).waitFor();
    if (screenshots) {
      await mkdir(screenshots, {recursive: true});
      await page.screenshot({path: path.join(screenshots, 'web-lab-overview.png')});
    }

    await button('Deck').click();
    await page.getByRole('img', {name: 'Deck camera of the simulated workcell'}).waitFor();
    await button('Open lid').click();
    await waitForText(reading('lid'), /^-72°$/);
    await waitReady();
    await button('Turn light on').click();
    await waitForText(page.locator('#light-state'), /^On$/);

    await page.getByLabel('Target (mm)').fill('540');
    await button('Move joint').click();
    await waitForText(page.locator('#motion'), /^Moving$/);
    await button('Hold motion').click();
    await waitForText(page.locator('#motion'), /^Held$/);
    const held = await reading('lift').textContent();
    assert(parseFloat(held) > 450 && parseFloat(held) < 540, 'Hold should preserve an intermediate lift position');
    await page.reload();
    await waitLive();
    await waitForText(reading('lift'), held);
    await page.getByText('Held motion', {exact: true}).first().waitFor();

    await page.getByRole('combobox', {name: /^Joint\b/}).selectOption('shoulder');
    await page.getByLabel('Target (°)').fill('-105');
    await button('Move joint').click();
    await waitForText(reading('shoulder'), /^-105°$/);
    await waitReady();
    await button('Deck').click();
    await page.getByRole('img', {name: 'Deck camera of the simulated workcell'}).waitFor();
    if (screenshots) await page.screenshot({path: path.join(screenshots, 'web-lab-deck.png')});

    for (const width of [360, 1280, 360, 1280]) {
      await page.setViewportSize({width, height: 900});
      await page.waitForFunction(() => document.documentElement.scrollWidth <= innerWidth);
      await button('Hold motion').waitFor();
    }
    await button('Home arm').click();
    await waitForText(reading('lift'), /^450 mm$/);
    await waitForText(reading('shoulder'), /^-127°$/);
    await waitReady();
    await button('Close lid').click();
    await waitForText(reading('lid'), /^0°$/);
    await button('Turn light off').click();
    await waitForText(page.locator('#light-state'), /^Off$/);
    assert.deepEqual(errors, []);
    console.log('Verified live views, motion, hold, reconnect, lid, light and responsive controls.');
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
