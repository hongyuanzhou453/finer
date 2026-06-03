/**
 * One-off helper: capture the live demo workbench for use as the landing
 * "interactive demo" preview image. Run against the dev server (port 4311).
 *
 *   NODE_PATH=../finer_dashboard/node_modules node scripts/screenshot-demo.cjs <out.png> [url]
 *
 * Reuses the dashboard's already-installed playwright + chromium.
 */
const { chromium } = require("playwright");

(async () => {
  const out = process.argv[2];
  const url = process.argv[3] || "http://localhost:4311/demo";
  if (!out) {
    console.error("usage: node screenshot-demo.cjs <out.png> [url]");
    process.exit(1);
  }
  const browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
  });
  await page.goto(url, { waitUntil: "load" });
  // optional: click a KOL in the left rail to vary the captured state
  const kolName = process.argv[4];
  if (kolName) {
    await page.locator("button", { hasText: kolName }).first().click();
  }
  // let the cumulative-return draw-in animation settle
  await page.waitForTimeout(2200);
  await page.screenshot({ path: out });
  await browser.close();
  console.log("saved", out);
})().catch((e) => {
  console.error(e.message || e);
  process.exit(1);
});
