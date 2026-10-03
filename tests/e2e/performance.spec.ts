import { expect, test } from '@playwright/test';
import type { Browser, TestInfo } from '@playwright/test';

interface LoadSample {
  readyMs: number;
  lcpMs: number;
  cls: number;
}

const OPTIONAL_MAP_HOST = 'tiles.maps.eox.at';

function percentile(values: number[], percentileValue: number): number {
  const ordered = [...values].sort((left, right) => left - right);
  return ordered[Math.max(0, Math.ceil(ordered.length * percentileValue) - 1)] ?? 0;
}

async function coldLoad(
  browser: Browser,
  testInfo: TestInfo,
): Promise<LoadSample> {
  const viewport = testInfo.project.name === 'mobile-390'
    ? { width: 390, height: 844 }
    : { width: 1440, height: 900 };
  const context = await browser.newContext({
    colorScheme: 'dark',
    locale: 'en-SG',
    reducedMotion: 'no-preference',
    timezoneId: 'UTC',
    viewport,
  });
  const page = await context.newPage();
  await page.route(`https://${OPTIONAL_MAP_HOST}/**`, (route) => route.abort('internetdisconnected'));
  const failures: string[] = [];
  const external: string[] = [];
  page.on('pageerror', (error) => failures.push(error.message));
  page.on('console', (message) => {
    if (message.text().includes('GL Driver Message') && message.text().includes('GPU stall')) return;
    if (message.text().startsWith('Failed to load resource:')) return;
    if (message.type() === 'error' || message.type() === 'warning') failures.push(message.text());
  });
  page.on('request', (request) => {
    const hostname = new URL(request.url()).hostname;
    if (!/^(127\.0\.0\.1|localhost)$/.test(hostname) && hostname !== OPTIONAL_MAP_HOST) {
      external.push(request.url());
    }
  });
  await page.addInitScript(() => {
    const values = { cls: 0, lcpMs: 0 };
    Object.defineProperty(window, '__nclVitals', { value: values, writable: false });
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) values.lcpMs = Math.max(values.lcpMs, entry.startTime);
    }).observe({ type: 'largest-contentful-paint', buffered: true });
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        const shift = entry as PerformanceEntry & { hadRecentInput?: boolean; value?: number };
        if (!shift.hadRecentInput) values.cls += shift.value ?? 0;
      }
    }).observe({ type: 'layout-shift', buffered: true });
  });
  const response = await page.goto(process.env.NCL_BASE_URL ?? 'http://127.0.0.1:4173/');
  expect(response?.status()).toBe(200);
  await page.locator("html[data-ncl-ready='true']").waitFor({ timeout: 30_000 });
  await page.waitForTimeout(100);
  const sample = await page.evaluate(() => {
    const values = (window as Window & {
      __nclVitals: { cls: number; lcpMs: number };
    }).__nclVitals;
    return {
      readyMs: performance.now(),
      lcpMs: values.lcpMs,
      cls: values.cls,
    };
  });
  await context.close();
  expect(failures).toEqual([]);
  expect(external).toEqual([]);
  return sample;
}

test('@perf-ci cold replay load stays within the blocking budgets', async ({ browser }, testInfo) => {
  test.skip(process.env.NCL_E2E_READY !== '1', 'performance checks require the real replay stack');
  test.setTimeout(180_000);
  // Warm the container, fixture caches and first GPU frame before measuring five cold contexts.
  await coldLoad(browser, testInfo);
  const samples: LoadSample[] = [];
  for (let index = 0; index < 5; index += 1) samples.push(await coldLoad(browser, testInfo));
  const report = {
    project: testInfo.project.name,
    samples,
    readyP95Ms: percentile(samples.map((sample) => sample.readyMs), 0.95),
    lcpP75Ms: percentile(samples.map((sample) => sample.lcpMs), 0.75),
    clsMax: Math.max(...samples.map((sample) => sample.cls)),
  };
  await testInfo.attach('browser-performance.json', {
    body: Buffer.from(JSON.stringify(report, null, 2)),
    contentType: 'application/json',
  });
  console.log(JSON.stringify({ browserPerformance: report }));
  const mobile = testInfo.project.name === 'mobile-390';
  expect(report.readyP95Ms).toBeLessThanOrEqual(mobile ? 3_500 : 2_500);
  expect(report.lcpP75Ms).toBeGreaterThan(0);
  expect(report.lcpP75Ms).toBeLessThanOrEqual(mobile ? 3_000 : 2_500);
  expect(report.clsMax).toBeLessThanOrEqual(0.1);
});

test('@perf-local reports animation frames and long tasks without a CI GPU gate', async ({ page }, testInfo) => {
  test.skip(process.env.NCL_E2E_READY !== '1', 'performance checks require the real replay stack');
  test.setTimeout(30_000);
  await page.goto('/?perf=1');
  await page.locator("html[data-ncl-ready='true']").waitFor({ timeout: 30_000 });
  await page.getByTestId('pass-playback-button').click();
  const sample = await page.evaluate(async () => {
    const frameDurations: number[] = [];
    const longTasks: number[] = [];
    const observer = new PerformanceObserver((list) => {
      longTasks.push(...list.getEntries().map((entry) => entry.duration));
    });
    observer.observe({ type: 'longtask', buffered: true });
    let previous = performance.now();
    const started = previous;
    await new Promise<void>((resolve) => {
      const frame = (now: number) => {
        frameDurations.push(now - previous);
        previous = now;
        if (now - started >= 10_000) resolve();
        else requestAnimationFrame(frame);
      };
      requestAnimationFrame(frame);
    });
    observer.disconnect();
    const rates = frameDurations
      .slice(2)
      .map((duration) => 1_000 / duration)
      .sort((left, right) => left - right);
    return {
      frames: frameDurations.length,
      p10Fps: rates[Math.floor(rates.length * 0.1)] ?? 0,
      longestTaskMs: Math.max(0, ...longTasks),
    };
  });
  await testInfo.attach('local-gpu-performance.json', {
    body: Buffer.from(JSON.stringify(sample, null, 2)),
    contentType: 'application/json',
  });
  console.log(JSON.stringify({ reportOnly: true, project: testInfo.project.name, ...sample }));
});
