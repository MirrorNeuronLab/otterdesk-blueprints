"""Opt-in browser gate for an already running real CCTV workspace."""

import argparse
import asyncio
import json
from pathlib import Path

import httpx
from playwright.async_api import async_playwright


async def verify(url, output, timeout):
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    async with httpx.AsyncClient(base_url=url, timeout=10, trust_env=False) as client:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page(viewport={"width": 1440, "height": 1000})
                page.on("pageerror", lambda error: errors.append(str(error)))
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_function("document.getElementById('camera-image').naturalWidth > 0", timeout=timeout * 1000)
                await page.wait_for_function("document.querySelectorAll('.caption').length >= 3", timeout=timeout * 1000)
                initial = (await client.get("api/status")).json()
                count = initial["session"]["total_captions"]
                await page.reload(wait_until="domcontentloaded")
                await page.wait_for_function("document.querySelectorAll('.caption').length >= 3")
                await page.wait_for_function(f"Number(document.getElementById('caption-count').textContent) > {count}", timeout=timeout * 1000)
                for width in [1440, 320, 1000, 320, 1440]:
                    await page.set_viewport_size({"width": width, "height": 1000})
                    assert not await page.evaluate("document.documentElement.scrollWidth > innerWidth"), width
                    assert await page.get_by_role("link", name="Export observations").is_visible()
                await page.screenshot(path=str(output / "workspace-wide.png"), full_page=True)
                await page.set_viewport_size({"width": 320, "height": 900})
                await page.screenshot(path=str(output / "workspace-narrow.png"), full_page=True)
                final = (await client.get("api/export")).json()
                assert final["session"]["status"] == "running", final["session"].get("error")
                assert len(final["captions"]) >= 3
                assert not errors, errors
                (output / "captions.json").write_text(json.dumps(final, indent=2))
                print(json.dumps({"captions": final["session"]["total_captions"], "preview": final["preview"]["connected"],
                                  "browser_errors": errors, "resize_widths": [1440, 320, 1000, 320, 1440]}))
            finally:
                await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    asyncio.run(verify(args.url.rstrip("/") + "/", args.output, args.timeout))
