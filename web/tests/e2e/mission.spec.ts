import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-ncl-ready", "true", { timeout: 20_000 });
});

test("mission, playback, detail, and evidence smoke", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Next geometric opportunity" })).toBeVisible();
  await expect(
    page.getByText("An overpass is a geometric opportunity, not a promised acquisition."),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent looks" })).toBeVisible();
  await expect(page.getByTestId("globe-stage")).toBeVisible();

  await page.getByRole("button", { name: "Play pass" }).click();
  await expect(page.getByRole("button", { name: "Pause pass" })).toBeVisible();
  await page.getByRole("button", { name: "Pause pass" }).click();

  await page.keyboard.press("e");
  await expect(page.getByRole("dialog", { name: "Evidence and provenance" })).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "Open AOI detail" }).click();
  await expect(page.getByTestId("aoi-detail")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Catalogue context" })).toBeVisible();
  await page.getByRole("tab", { name: "SCL classes" }).click();
  await expect(page.getByTestId("class-distribution")).toBeVisible();
});

test("test clock hooks and AOI picker are available", async ({ page }) => {
  const mode = await page.evaluate(
    async () => (await fetch("/v1/mode")).json() as Promise<{ clock: string }>,
  );
  const recordedDate = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  })
    .format(new Date(mode.clock))
    .toUpperCase();
  await expect(page.getByTestId("replay-clock")).toContainText(recordedDate);
  await page.evaluate(() => window.__ncl?.setTime("2026-10-03T06:18:00.000Z"));
  await expect(page.getByTestId("replay-clock")).toContainText("06:18");
  await page.getByTestId("aoi-switcher").click();
  await expect(page.getByTestId("aoi-preset-row")).toHaveCount(5);
});

test("opportunity phase never freezes at zero after swath entry", async ({ page }) => {
  await page.evaluate(() => window.__ncl?.setTime("2026-10-03T02:31:30.100Z"));
  await expect(page.getByTestId("opportunity-phase")).toContainText("In swath · 00:10 since entry");

  await page.evaluate(() => window.__ncl?.setTime("2026-10-03T02:33:00.000Z"));
  await expect(page.getByTestId("next-opportunity-card")).not.toContainText("00:00:00");
  await expect(page.getByTestId("next-opportunity-card")).toContainText(
    /Time to closest approach|No later opportunity in this window/,
  );
});

test("reduced motion advances pass playback as manual steps", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-ncl-ready", "true", { timeout: 20_000 });

  await page.getByTestId("pass-playback-button").click();
  await expect(page.getByTestId("pass-playback-button")).not.toContainText("Pause pass");
  await expect(page.getByTestId("globe-playback-scrubber")).toHaveValue("25");
});

test("live-disabled mode switch keeps replay available with the engine reason", async ({ page }) => {
  test.skip(
    process.env.NCL_E2E_REAL === "1",
    "The integrated engine is started with live mode enabled for its separate flow.",
  );
  await page.getByTestId("mode-badge").click();
  await page.getByRole("button", { name: "Use live data" }).click();
  await expect(page.getByTestId("mode-error")).toContainText("disabled by the engine");
  await expect(page.getByTestId("mode-badge")).toContainText("RECORDED REPLAY");
});

test("drawn AOI streams recorded orbit progress and stays honest about archive coverage", async ({
  page,
}) => {
  await page.getByTestId("aoi-switcher").click();
  await page.getByRole("tab", { name: "Draw" }).click();
  await page.getByRole("button", { name: "Start polygon" }).click();
  const globe = page.getByTestId("aoi-draw-map");
  const bounds = await globe.boundingBox();
  expect(bounds).not.toBeNull();
  await globe.click({ position: { x: bounds!.width * 0.34, y: bounds!.height * 0.37 } });
  await globe.click({ position: { x: bounds!.width * 0.53, y: bounds!.height * 0.38 } });
  await globe.click({ position: { x: bounds!.width * 0.44, y: bounds!.height * 0.57 } });
  await expect(page.getByTestId("draw-vertex-count")).toHaveText("3");
  await page.getByTestId("use-drawn-aoi").click();
  await expect(page.getByTestId("stream-progress")).toBeVisible();
  await expect(page.getByTestId("not-recorded-archive")).toContainText("will not invent imagery");
  await expect(page.getByTestId("opportunity-row").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("stream-progress")).toContainText("Analysis ready", { timeout: 30_000 });
});

test("@live-real drawn AOI starts the live analysis stream", async ({ page }, testInfo) => {
  test.skip(
    process.env.NCL_E2E_REAL !== "1" || testInfo.project.name !== "desktop-1440",
    "Runs once against an NCL_ALLOW_LIVE=1 engine.",
  );
  await page.getByTestId("mode-badge").click();
  await page.getByRole("button", { name: "Use live data" }).click();
  await expect(page.getByTestId("mode-badge")).toContainText("LIVE DATA", { timeout: 30_000 });
  await page.getByTestId("aoi-switcher").click();
  await page.getByRole("tab", { name: "Draw" }).click();
  await page.getByRole("button", { name: "Start polygon" }).click();
  const globe = page.getByTestId("aoi-draw-map");
  const bounds = await globe.boundingBox();
  expect(bounds).not.toBeNull();
  await globe.click({ position: { x: bounds!.width * 0.34, y: bounds!.height * 0.37 } });
  await globe.click({ position: { x: bounds!.width * 0.53, y: bounds!.height * 0.38 } });
  await globe.click({ position: { x: bounds!.width * 0.44, y: bounds!.height * 0.57 } });
  await page.getByTestId("use-drawn-aoi").click();
  await expect(page.getByTestId("stream-progress")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("progress-orbit")).toBeVisible();
  await expect(page.getByTestId("progress-archive")).toBeVisible();
});

test("mission has no serious automated accessibility violations", async ({ page }) => {
  const results = await new AxeBuilder({ page }).exclude(".cesium-host").analyze();
  expect(
    results.violations.filter(
      (violation) => violation.impact === "serious" || violation.impact === "critical",
    ),
  ).toEqual([]);
});
