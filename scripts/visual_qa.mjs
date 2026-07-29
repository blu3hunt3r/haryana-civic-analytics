import { mkdir } from "node:fs/promises";
import { chromium } from "playwright";

const baseUrl = process.env.PORTAL_URL ?? "http://127.0.0.1:5173/";
const output = new URL("../artifacts/visual-qa/", import.meta.url);
await mkdir(output, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  executablePath:
    process.env.CHROME_PATH ??
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  args: process.env.HOST_RESOLVER_RULES
    ? [`--host-resolver-rules=${process.env.HOST_RESOLVER_RULES}`]
    : [],
});

const results = [];
for (const viewport of [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "mobile", width: 390, height: 844 },
]) {
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  const failedResponses = [];
  const failedRequests = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push({ text: message.text(), location: message.location() });
    }
  });
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("response", (response) => {
    if (response.status() >= 400) {
      failedResponses.push(`${response.status()} ${response.url()}`);
    }
  });
  page.on("requestfailed", (request) => {
    const error = request.failure()?.errorText ?? "failed";
    // MapLibre cancels obsolete tiles during a zoom and when a QA context closes.
    if (error !== "net::ERR_ABORTED") {
      failedRequests.push(`${error} ${request.url()}`);
    }
  });
  const started = performance.now();
  const response = await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.locator('#evidence-map[data-map-ready="true"]').waitFor({ timeout: 30_000 });
  await page.locator("#index-state.is-ready").waitFor({ timeout: 60_000 });
  await page.locator(".tender-row").first().waitFor({ timeout: 10_000 });
  await page.waitForTimeout(2_000);
  const readyMs = Math.round(performance.now() - started);
  await page.screenshot({
    path: new URL(`${viewport.name}-full.png`, output).pathname,
    fullPage: true,
  });

  await page.locator("#gurugram-view").click();
  await page.locator('input[data-layer="sectors"]').check();
  await page.locator("#search").fill("drainage");
  await page
    .locator('#search[data-search-state="ready"]')
    .waitFor({ timeout: 20_000 });
  const resultText = await page.locator("#result-count").innerText();
  await page.locator(".tender-row").first().click();
  await page.locator("#tender-dialog[open]").waitFor();
  await page.locator("#tender-detail .detail-header").waitFor({ timeout: 20_000 });
  await page.screenshot({
    path: new URL(`${viewport.name}-tender.png`, output).pathname,
    fullPage: false,
  });

  const horizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  results.push({
    viewport: viewport.name,
    httpStatus: response?.status(),
    readyMs,
    resultText,
    consoleErrors,
    pageErrors,
    failedResponses,
    failedRequests,
    horizontalOverflow,
  });
  await context.close();
}
await browser.close();

const failures = results.filter(
  (result) =>
    result.httpStatus !== 200 ||
    result.consoleErrors.length ||
    result.pageErrors.length ||
    result.failedResponses.length ||
    result.failedRequests.length ||
    result.horizontalOverflow,
);
console.log(JSON.stringify({ ok: failures.length === 0, results }, null, 2));
if (failures.length) process.exitCode = 1;
