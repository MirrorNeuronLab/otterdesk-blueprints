const assert = require("node:assert/strict");
const {pathToFileURL} = require("node:url");
const {join, resolve} = require("node:path");
const {tmpdir} = require("node:os");
const {createRequire} = require("node:module");
const fs = require("node:fs/promises");

const app = process.env.OTTERDESK_APP_ROOT || resolve(__dirname, "../../../otterdesk-desktop-app");
const {chromium, expect} = createRequire(join(app, "package.json"))("@playwright/test");

async function main() {
  if (!process.argv[2]) throw new Error("Pass the published dispatch sample web/index.html.");
  const url = pathToFileURL(resolve(process.argv[2])).href;
  const root = process.argv[3] ? resolve(process.argv[3]) : await fs.mkdtemp(join(tmpdir(), "verifier-report-"));
  await fs.mkdir(root, {recursive: true});
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:980},acceptDownloads:true,reducedMotion:"reduce"});
    const errors = [];
    page.on("pageerror", err => errors.push(err.message));
    page.on("console", msg => {if (msg.type() === "error") errors.push(msg.text());});
    const navigate = name => page.getByRole("tab", {name, exact:true}).click();
    const action = async name => {
      await page.getByRole("button", {name:"Actions", exact:true}).click();
      await page.getByRole("menuitem", {name}).click();
    };
    const panel = page.getByRole("tabpanel");
    await page.goto(url);
    await expect(page.getByRole("banner")).toHaveCount(1);
    await expect(page.getByRole("tablist", {name:"Verification views"})).toHaveCount(1);
    await expect(panel).toHaveCount(1);
    await expect(panel.getByRole("heading", {name:"Functional intent", exact:true})).toBeVisible();
    await expect(panel).toContainText("3 / 4");
    await expect(panel.getByRole("region", {name:"Comparison evidence"})).toContainText("AI review");
    await page.screenshot({path:join(root,"functional.png")});
    await panel.getByRole("link", {name:/reproduced behavioral defect/}).click();
    await expect(panel).toContainText("2 distinct clean candidate runs");
    await panel.getByRole("link", {name:"Integration and regression", exact:true}).click();
    const proof = panel.locator('details[data-case="boundary-retry"]');
    await expect(proof).toHaveAttribute("open","");
    await expect(panel).toContainText("Queue consumer");
    const cite = proof.getByRole("button",{name:"dispatch.py:5",exact:true});
    await cite.click();
    await expect(page.getByRole("dialog")).toContainText("queue.append(request)");
    await page.keyboard.press("Escape");
    await expect(cite).toBeFocused();
    await page.screenshot({path:join(root,"integration.png")});
    await navigate("Security and authorization");
    await expect(panel).toContainText("Runtime enforcement remains unmeasured");
    await page.goBack();
    await expect(proof).toHaveAttribute("open","");
    await page.goto(url + "#section=reliability");
    await expect(panel).toContainText("Repair check · Passed");
    await expect(panel).toContainText("Tautological assertion");
    await action("Open evidence explorer");
    await expect(page.getByRole("tab",{name:"Evidence explorer",exact:true})).toHaveAttribute("aria-selected","true");
    await navigate("Functional intent");
    for (const width of [760,360,1440]) {
      await page.setViewportSize({width,height:900});
      for (const title of ["Functional intent","Verified defects","Integration and regression","Security and authorization","Independent test quality"]) {
        await navigate(title);
        await expect(panel.getByRole("heading",{name:title,exact:true})).toBeVisible();
        await expect(page.getByRole("tab", {name:title, exact:true})).toHaveAttribute("aria-selected","true");
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), title + " overflowed at " + width);
      }
      if (width === 360) await page.screenshot({path:join(root,"mobile.png")});
    }
    await page.emulateMedia({media:"print"});
    await expect(panel).toHaveCount(5);
    await page.pdf({path:join(root,"report.pdf"),format:"A4",printBackground:true,margin:{top:"12mm",bottom:"12mm",left:"12mm",right:"12mm"}});
    await page.emulateMedia({media:"screen"});
    const pending = page.waitForEvent("download");
    await action("Export HTML");
    const file = await pending;
    assert.equal(file.suggestedFilename(),"software-verification-report.html");
    const exported = join(root,file.suggestedFilename());
    await file.saveAs(exported);
    await page.goto(pathToFileURL(exported).href + "#section=security&case=reviewer-archive");
    await expect(page.getByRole("button", {name:"Actions",exact:true})).toHaveCount(1);
    await expect(page.getByRole("tablist")).toHaveCount(1);
    await expect(panel.locator('details[data-case="reviewer-archive"]')).toHaveAttribute("open","");
    await panel.locator('details[data-case="reviewer-archive"]').getByRole("button",{name:"policy.json:2"}).click();
    await expect(page.getByRole("dialog")).toContainText("reviewer");
    await page.keyboard.press("Escape");
    for (const [name, filename] of [["Download Markdown", "report.md"], ["Download editable rules", "rules.md"]]) {
      const pendingText = page.waitForEvent("download");
      await action(name);
      const textFile = await pendingText;
      assert.equal(textFile.suggestedFilename(), filename);
      const [actual, expected] = await Promise.all([
        fs.readFile(await textFile.path()), fs.readFile(resolve(process.argv[2], "../..", filename))
      ]);
      assert.deepEqual(actual, expected);
    }
    assert.deepEqual(errors, []);
    console.log("Shared report navigation, source evidence, history, resizing, PDF and offline HTML export passed.");
  } finally {
    await browser.close();
  }
}
main().catch(err => {console.error(err); process.exitCode=1;});
