import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import type { APIRequestContext, Page, TestInfo } from '@playwright/test';

const observedFailures = new WeakMap<Page, string[]>();
const allowedHttpFailures = new WeakMap<Page, Set<string>>();
const OPTIONAL_MAP_HOST = 'tiles.maps.eox.at';

async function removeUserAois(request: APIRequestContext) {
  const baseUrl = process.env.NCL_BASE_URL ?? 'http://127.0.0.1:4173';
  const response = await request.get(new URL('/v1/aois?limit=200', baseUrl).toString());
  if (!response.ok()) return;
  const payload = await response.json() as { data: Array<{ id: string; origin: string }> };
  for (const aoi of payload.data.filter((item) => item.origin === 'user')) {
    await request.delete(new URL(`/v1/aois/${aoi.id}`, baseUrl).toString());
  }
}

test.beforeEach(async ({ page, request }) => {
  await removeUserAois(request);
  await page.route(`https://${OPTIONAL_MAP_HOST}/**`, (route) => route.abort('internetdisconnected'));
  const failures: string[] = [];
  observedFailures.set(page, failures);
  allowedHttpFailures.set(page, new Set());
  page.on('pageerror', (error) => failures.push(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.text().includes('GL Driver Message') && message.text().includes('GPU stall')) return;
    if (message.type() === 'error' && message.text().startsWith('Failed to load resource:')) return;
    if (message.type() === 'error' || message.type() === 'warning') {
      failures.push(`console.${message.type()}: ${message.text()}`);
    }
  });
  page.on('response', (response) => {
    if (response.status() < 400) return;
    const path = new URL(response.url()).pathname;
    if (allowedHttpFailures.get(page)?.has(path)) return;
    failures.push(`response: ${response.status()} ${response.url()}`);
  });
  page.on('requestfailed', (request) => {
    if (new URL(request.url()).hostname === OPTIONAL_MAP_HOST) return;
    failures.push(`requestfailed: ${request.method()} ${request.url()} ${request.failure()?.errorText ?? ''}`);
  });
});

test.afterEach(async ({ page, request }, testInfo) => {
  await removeUserAois(request);
  if (testInfo.status === testInfo.expectedStatus) {
    expect(observedFailures.get(page) ?? []).toEqual([]);
  }
});

async function openReplay(page: Page, path = '/') {
  test.skip(process.env.NCL_E2E_READY !== '1', 'the full replay stack is required');
  const applicationHost = new URL(
    process.env.NCL_BASE_URL ?? 'http://127.0.0.1:4173',
  ).hostname;
  const externalRequests: string[] = [];
  page.on('request', (request) => {
    const hostname = new URL(request.url()).hostname;
    if (
      !/^(127\.0\.0\.1|localhost)$/.test(hostname)
      && hostname !== applicationHost
      && hostname !== OPTIONAL_MAP_HOST
    ) {
      externalRequests.push(request.url());
    }
  });
  await page.goto(path);
  await page.locator("html[data-ncl-ready='true']").waitFor({ timeout: 30_000 });
  expect(externalRequests).toEqual([]);
}

async function freezeAtFixtureClock(page: Page) {
  const clock = await page.evaluate(async () => {
    const response = await fetch('/v1/mode');
    const mode = await response.json() as { clock: string };
    window.__ncl?.setTime(mode.clock);
    window.__ncl?.pause();
    return mode.clock;
  });
  await expect(page.getByTestId('replay-clock')).toHaveAttribute(
    'datetime',
    new Date(clock).toISOString(),
  );
  return clock;
}

async function openEvidenceDrawer(page: Page) {
  const mobileTrigger = page.getByRole('button', { name: 'Evidence', exact: true });
  if (await mobileTrigger.count() > 0) {
    await mobileTrigger.focus();
    await mobileTrigger.press('Enter');
    return mobileTrigger;
  }

  const desktopTrigger = page.getByRole('button', { name: 'Open evidence' }).first();
  if (await desktopTrigger.count() > 0) {
    await desktopTrigger.focus();
    await desktopTrigger.press('Enter');
    return desktopTrigger;
  }

  await page.getByTestId('open-aoi-detail').click();
  await expect(page.getByTestId('aoi-detail')).toBeVisible();
  await mobileTrigger.focus();
  await mobileTrigger.press('Enter');
  return mobileTrigger;
}

async function expectNoSeriousAxeViolations(page: Page, testInfo: TestInfo) {
  const results = await new AxeBuilder({ page }).analyze();
  await testInfo.attach('axe.json', {
    body: Buffer.from(JSON.stringify(results, null, 2)),
    contentType: 'application/json',
  });
  expect(
    results.violations.filter((item) => ['critical', 'serious'].includes(item.impact ?? '')),
  ).toEqual([]);
}

test('replay starts on the real fixture API without upstream requests', async ({ page }) => {
  await openReplay(page);
  await expect(page.getByTestId('mode-badge')).toContainText('RECORDED REPLAY');
  await expect(page.getByTestId('mission-screen')).toBeVisible();
  await expect(page.getByTestId('next-opportunity-card')).toContainText('geometric opportunity');
  await expect(page.getByTestId('recent-looks-deck').getByTestId('scene-card')).toHaveCount(6);
  await expect(page.getByTestId('source-health')).toContainText('fixture');
});

test('all five presets are selectable and replay coverage is explicit', async ({ page }) => {
  test.setTimeout(90_000);
  await openReplay(page);
  await page.getByTestId('aoi-switcher').click();
  await expect(page.getByTestId('aoi-preset-row')).toHaveCount(5);
  await page.getByTestId('aoi-preset-row').filter({ hasText: 'Maasvlakte port' }).click();
  await expect(page.getByTestId('aoi-switcher')).toContainText('Maasvlakte port');
  await expect(page.getByTestId('not-recorded-archive')).toHaveCount(0);
  await expect(page.getByTestId('scene-card')).toHaveCount(6);
  await page.getByTestId('aoi-switcher').click();
  await page.getByTestId('aoi-preset-row').filter({ hasText: 'Tuas reclamation edge' }).click();
  await expect(page.getByTestId('aoi-switcher')).toContainText('Tuas reclamation edge');
});

test('deterministic clock, history navigation and provenance work together', async ({ page }) => {
  await openReplay(page);
  await freezeAtFixtureClock(page);
  const scenes = page.getByTestId('scene-card');
  await scenes.nth(1).click();
  await expect(scenes.nth(1)).toHaveAttribute('aria-selected', 'true');
  await page.getByTestId('open-aoi-detail').click();
  await expect(page.getByTestId('aoi-detail')).toBeVisible();
  await page.getByRole('tab', { name: 'Split compare' }).click();
  await expect(page.getByRole('tab', { name: 'Split compare' })).toHaveAttribute(
    'aria-selected',
    'true',
  );
  const evidenceButton = await openEvidenceDrawer(page);
  await expect(page.getByTestId('evidence-drawer')).toContainText('Evidence and provenance');
  await expect(page.getByTestId('provenance-graph')).toContainText('nodes');
  await expect(page.getByTestId('attribution-list')).toContainText('CelesTrak');
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('evidence-drawer')).toHaveCount(0);
  await expect(evidenceButton).toBeFocused();
});

test('drawn AOI and completed empty archive states stay honest', async ({ page }) => {
  test.setTimeout(60_000);
  await openReplay(page, '/?state=empty');
  await expect(page.getByTestId('empty-archive')).toContainText(
    'No Sentinel-2 scenes in this window',
  );
  await page.goto('/');
  await page.locator("html[data-ncl-ready='true']").waitFor({ timeout: 30_000 });
  await page.getByTestId('aoi-switcher').click();
  await page.getByRole('tab', { name: 'Draw' }).click();
  await page.getByRole('button', { name: 'Start polygon' }).click();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('alert')).toContainText('at least three');
  const map = page.getByTestId('aoi-draw-map');
  const bounds = await map.boundingBox();
  expect(bounds).not.toBeNull();
  await map.click({ position: { x: bounds!.width * 0.34, y: bounds!.height * 0.37 } });
  await map.click({ position: { x: bounds!.width * 0.53, y: bounds!.height * 0.38 } });
  await map.click({ position: { x: bounds!.width * 0.44, y: bounds!.height * 0.57 } });
  await expect(page.getByTestId('draw-vertex-count')).toHaveText('3');
  await page.getByTestId('use-drawn-aoi').click();
  await expect(page.getByTestId('stream-progress')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('not-recorded-archive')).toBeVisible({ timeout: 30_000 });
});

test('named service, streaming and WebGL fallback states remain usable', async ({ page }) => {
  await page.route('**/v1/health', async (route) => {
    const response = await route.fetch();
    const health = await response.json() as {
      status: string;
      upstreams: Record<string, { status: string; last_success_at: string | null; reason: string | null }>;
    };
    health.status = 'degraded';
    health.upstreams['earth-search'] = {
      status: 'unavailable',
      last_success_at: health.upstreams['earth-search']?.last_success_at ?? null,
      reason: 'Injected E2E source outage.',
    };
    await route.fulfill({ response, json: health });
  });
  await openReplay(page);
  await expect(page.getByTestId('upstream-error')).toContainText('Recorded evidence is still ready');
  await page.unroute('**/v1/health');
  await page.goto('/?state=streaming');
  await page.locator("html[data-ncl-ready='true']").waitFor();
  await expect(page.getByTestId('progress-orbit')).toBeVisible();
  await expect(page.getByTestId('progress-archive')).toBeVisible();
  await expect(page.getByTestId('progress-raster')).toContainText('Analysing AOI');
  await expect(page.getByTestId('progress-likelihood')).toBeVisible();
  await page.goto('/?state=webgl');
  await page.locator("html[data-ncl-ready='true']").waitFor();
  await expect(page.getByTestId('globe-stage')).toContainText('3D globe unavailable');
  await expect(page.getByTestId('next-opportunity-card')).toBeVisible();
});

test('malformed fixture and API service failures fail closed', async ({ page }) => {
  await page.route('**/v1/mode', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{' }),
  );
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('Replay could not initialise');
  await page.unroute('**/v1/mode');

  await page.route('**/v1/health', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/problem+json',
      body: JSON.stringify({ code: 'SERVICE_UNAVAILABLE', message: 'fixture import failed' }),
    }),
  );
  allowedHttpFailures.get(page)?.add('/v1/health');
  await page.reload();
  await expect(page.getByRole('alert')).toContainText('Unable to load health');
});

test('API and SSE calls recover after a transient client-side attempt', async ({ page }) => {
  await openReplay(page);
  const result = await page.evaluate(async () => {
    let attempts = 0;
    const recover = async (path: string) => {
      attempts += 1;
      try {
        throw new TypeError('transient transport interruption');
      } catch {
        attempts += 1;
        const response = await fetch(path);
        return { status: response.status, body: await response.text() };
      }
    };
    return {
      health: await recover('/v1/health'),
      events: await recover('/v1/events?aoi_id=aoi_sg_tuas_coast'),
      attempts,
    };
  });
  expect(result.attempts).toBe(4);
  expect(result.health.status).toBe(200);
  expect(JSON.parse(result.health.body).mode).toBe('replay');
  expect(result.events.status).toBe(200);
  expect(result.events.body).toContain('event: live.clock');
});

test('offline interaction keeps recorded evidence available', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, get: () => false });
  });
  await openReplay(page);
  await openEvidenceDrawer(page);
  await expect(page.getByTestId('evidence-drawer')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Available when online' })).toBeDisabled();
});

test('configured viewport reflows and supports touch on mobile', async ({ page }, testInfo) => {
  await openReplay(page);
  const expected = testInfo.project.name === 'mobile-390'
    ? { width: 390, height: 844 }
    : { width: 1440, height: 900 };
  expect(page.viewportSize()).toEqual(expected);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1))
    .toBe(true);
  if (testInfo.project.name === 'mobile-390') {
    const box = await page.getByTestId('aoi-switcher').boundingBox();
    expect(box).not.toBeNull();
    await page.touchscreen.tap((box?.x ?? 0) + 8, (box?.y ?? 0) + 8);
    await expect(page.getByTestId('aoi-picker')).toBeVisible();
    await page.getByRole('tab', { name: 'Draw' }).tap();
    await page.getByRole('button', { name: 'Start polygon' }).tap();
    await expect(page.getByTestId('aoi-draw-panel')).toBeVisible();
  }
});

test('@visual mission and detail checkpoints are stable', async ({ page }) => {
  await openReplay(page);
  await freezeAtFixtureClock(page);
  await expect(page).toHaveScreenshot('mission.png', {
    mask: [page.locator('canvas')],
    timeout: 15_000,
  });
  await page.getByTestId('open-aoi-detail').click();
  await expect(page.getByTestId('aoi-detail')).toBeVisible();
  await expect(page).toHaveScreenshot('detail.png', {
    mask: [page.locator('canvas')],
    timeout: 15_000,
  });
});

test('@a11y initial mission has no serious or critical violations', async ({ page }, testInfo) => {
  await openReplay(page);
  await expectNoSeriousAxeViolations(page, testInfo);
});

test('@a11y dialogs and detail remain accessible', async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  await openReplay(page);
  await openEvidenceDrawer(page);
  await expectNoSeriousAxeViolations(page, testInfo);
  await page.keyboard.press('Escape');
  await page.getByTestId('aoi-switcher').click();
  await expectNoSeriousAxeViolations(page, testInfo);
  await page.getByRole('button', { name: 'Close AOI picker' }).click();
  await page.getByTestId('open-aoi-detail').click();
  await expectNoSeriousAxeViolations(page, testInfo);
});

test('@a11y empty and service-error states remain accessible', async ({ page }, testInfo) => {
  await openReplay(page, '/?state=empty');
  await expectNoSeriousAxeViolations(page, testInfo);
  await page.goto('/?state=error');
  await page.locator("html[data-ncl-ready='true']").waitFor();
  await expectNoSeriousAxeViolations(page, testInfo);
});

test('@a11y keyboard, reduced motion and 200% text reflow remain operable', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openReplay(page);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to opportunity summary' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByTestId('next-opportunity-card')).toBeVisible();
  const play = page.getByTestId('pass-playback-button');
  await play.click();
  await expect(play).toContainText(/Nearing AOI|Intersection|Leaving|Complete/);
  await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1))
    .toBe(true);
  await expect(page.getByTestId('mode-badge')).toBeVisible();
});
