const { test, before, after } = require("node:test");
const assert = require("node:assert/strict");
const { chromium, expect } = require("@playwright/test");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const http = require("node:http");
let browser, server, root, origin;
before(async () => {
  root = await fs.mkdtemp(path.join(os.tmpdir(), "ocr-report-"));
  execFileSync(process.env.PYTHON || "python3", [
    path.join(__dirname, "report_fixture.py"),
    root,
  ]);
  server = http.createServer(async (request, response) => {
    try {
      const name = decodeURIComponent(
        new URL(request.url, "http://localhost").pathname,
      ).slice(1);
      const target = path.resolve(root, name);
      if (!target.startsWith(root + path.sep)) throw new Error("Invalid path");
      const types = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css",
        ".js": "text/javascript",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".woff2": "font/woff2",
        ".txt": "text/plain",
        ".json": "application/json",
      };
      response.setHeader(
        "Content-Type",
        types[path.extname(target)] || "application/octet-stream",
      );
      response.end(await fs.readFile(target));
    } catch {
      response.writeHead(404);
      response.end();
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROME_EXECUTABLE
      ? { executablePath: process.env.CHROME_EXECUTABLE }
      : {}),
  });
});
after(async () => {
  await browser?.close();
  if (server) await new Promise((resolve) => server.close(resolve));
  if (root) await fs.rm(root, { recursive: true, force: true });
});
async function open(offline = false) {
  const page = await browser.newPage({
    viewport: { width: 1280, height: 900 },
  });
  const errors = [],
    external = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (!request.url().startsWith(offline ? "file:" : origin))
      external.push(request.url());
  });
  await page.goto(
    offline
      ? pathToFileURL(path.join(root, "web/index.html")).href
      : origin + "/web/index.html",
  );
  await expect(
    page.getByRole("button", { name: "Actions", exact: true }),
  ).toBeVisible();
  return { page, errors, external };
}

test("Offline report renders actual previews, escaped text and local controls", async () => {
  const { page, errors, external } = await open(true);
  try {
    await expect(
      page.getByRole("heading", { name: "OCR report" }),
    ).toBeVisible();
    await expect(page.locator("#page-text")).toContainText(
      "</script><img src=x",
    );
    assert.equal(await page.evaluate(() => window.injected), undefined);
    assert.equal(await page.locator("#page-text img").count(), 0);
    assert.equal(
      await page
        .locator("#page-preview image")
        .evaluate((image) => image.getBBox().width),
      626,
    );
    await page.getByRole("button", { name: "Next page" }).click();
    await expect(page.locator("#page-text")).toHaveText("Page two text");
    await expect(
      page.getByRole("button", { name: "Next page" }),
    ).toBeDisabled();
    await page.getByRole("button", { name: "Previous page" }).click();
    await expect(
      page.getByRole("button", { name: "Previous page" }),
    ).toBeDisabled();
    await page.getByRole("button", { name: "Actions", exact: true }).click();
    await page.getByRole("menuitem", { name: "Document details" }).click();
    await expect(
      page.getByText("Source SHA-256", { exact: true }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.locator("#report-inspector")).not.toBeVisible();
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
  } finally {
    await page.close();
  }
});

test("Page selection, region correspondence, zoom and copying work together", async () => {
  const { page, errors } = await open();
  try {
    await page.getByLabel("Show text regions").check();
    await page.locator(".region-box").first().focus();
    await page.keyboard.press("Enter");
    await expect(page.getByLabel("Result view")).toHaveValue("regions");
    await expect(
      page.locator('#region-list [data-selected="true"]'),
    ).toHaveCount(1);
    await page.locator("#region-list button").nth(1).click();
    await expect(
      page.locator('.region-box[data-selected="true"]'),
    ).toHaveAttribute("data-region", "1");
    await page.getByLabel("Preview zoom").selectOption("200");
    assert.ok(
      await page
        .locator("#preview-scroll")
        .evaluate((node) => node.scrollWidth > node.clientWidth),
    );
    await page.getByLabel("Page", { exact: true }).selectOption("1");
    await expect(page.locator("#region-list")).toContainText("Page two text");
    await page.evaluate(() =>
      Object.defineProperty(navigator, "clipboard", {
        value: {
          writeText: async (text) => {
            window.copied = text;
          },
        },
      }),
    );
    await page.getByRole("button", { name: "Copy page text" }).click();
    await expect(
      page.getByText("Page text copied.", { exact: true }),
    ).toBeVisible();
    assert.equal(await page.evaluate(() => window.copied), "Page two text");
    assert.deepEqual(errors, []);
  } finally {
    await page.close();
  }
});

test("Files list accounts for failures, skipped formats and empty Office pages", async () => {
  const { page } = await open();
  try {
    await page.getByRole("tab", { name: "Files", exact: true }).click();
    await expect(page.locator("#batch-counts")).toContainText(
      "2 completed · 1 failed · 1 skipped",
    );
    await page.getByLabel("Find a file").fill("notes");
    await expect(page.locator("#file-list")).toContainText(
      "Unsupported format",
    );
    await page.getByLabel("Find a file").fill("missing");
    await expect(
      page.getByText("No matching files.", { exact: true }),
    ).toBeVisible();
    await page.getByLabel("Find a file").fill("broken");
    await page.getByRole("link", { name: "broken.pdf Failed" }).click();
    await expect(page.locator("#document-error")).toContainText(
      "Couldn't read this document",
    );
    await expect(
      page.getByRole("button", { name: "Copy page text" }),
    ).toBeDisabled();
    await page
      .getByLabel("Document", { exact: true })
      .selectOption("empty.html");
    await expect(
      page.getByText("No text was detected on this page.", { exact: true }),
    ).toBeVisible();
    await expect(page.locator("#document-note")).toContainText("Office pages");
    for (const width of [1440, 800, 360, 1280, 360]) {
      await page.setViewportSize({ width, height: 900 });
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        true,
        `overflow at ${width}`,
      );
      await expect(
        page.getByRole("button", { name: "Actions", exact: true }),
      ).toBeInViewport();
      await expect(
        page.getByLabel("Document", { exact: true }),
      ).toBeInViewport();
    }
  } finally {
    await page.close();
  }
});

test("Broken previews and blocked clipboard retain usable results", async () => {
  const { page } = await open();
  try {
    await page.route("**/previews/*", (route) => route.abort());
    await page.reload();
    await expect(
      page.getByText("Preview unavailable. Download the original file.", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.locator("#page-text")).toContainText("Synthetic Nasdaq");
    await page.evaluate(() =>
      Object.defineProperty(navigator, "clipboard", {
        value: {
          writeText: async () => {
            throw new Error("unavailable");
          },
        },
      }),
    );
    await page.getByRole("button", { name: "Copy page text" }).click();
    await expect(page.locator("#copy-status")).toContainText(
      "use your browser",
    );
    await expect(
      page.getByRole("link", { name: "Download original", exact: true }),
    ).toHaveAttribute("download", "Newspaper.jpg");
  } finally {
    await page.close();
  }
});

test("Original and text downloads preserve bytes without navigating away", async () => {
  const { page } = await open();
  try {
    let pending = page.waitForEvent("download");
    await page
      .getByRole("link", { name: "Download original", exact: true })
      .click();
    let download = await pending;
    assert.equal(download.suggestedFilename(), "Newspaper.jpg");
    assert.deepEqual(
      await fs.readFile(await download.path()),
      await fs.readFile(path.join(root, "web/originals/sample.jpg")),
    );
    await page.getByRole("button", { name: "Actions", exact: true }).click();
    pending = page.waitForEvent("download");
    await page
      .getByRole("menuitem", { name: "Download text", exact: true })
      .click();
    download = await pending;
    assert.equal(download.suggestedFilename(), "text.txt");
    assert.deepEqual(
      await fs.readFile(await download.path()),
      await fs.readFile(path.join(root, "documents/sample/text.txt")),
    );
    assert.ok(page.url().endsWith("/web/index.html"));
  } finally {
    await page.close();
  }
});
