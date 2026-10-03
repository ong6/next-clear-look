import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const baseUrl = process.env.NCL_BASE_URL ?? "http://127.0.0.1:5180";
const output = process.env.NCL_PERF_OUTPUT ?? path.resolve(process.cwd(), ".local", "performance");
await mkdir(output, { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: false });
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  colorScheme: "dark",
  reducedMotion: "no-preference",
});
await page.goto(`${baseUrl}/?perf=1`, { waitUntil: "domcontentloaded" });
await page.locator("html[data-ncl-ready='true']").waitFor({ timeout: 90_000 });
await page.getByRole("button", { name: "Play pass" }).click();

const sample = await page.evaluate(async () => {
  const frameDurations = [];
  const longTasks = [];
  const observer = new PerformanceObserver((list) =>
    longTasks.push(...list.getEntries().map((entry) => entry.duration)),
  );
  observer.observe({ type: "longtask", buffered: true });
  let previous = performance.now();
  const started = previous;
  await new Promise((resolve) => {
    const frame = (now) => {
      frameDurations.push(now - previous);
      previous = now;
      if (now - started >= 10_000) resolve();
      else requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  });
  observer.disconnect();
  const frameRates = frameDurations
    .slice(2)
    .map((duration) => 1_000 / duration)
    .sort((a, b) => a - b);
  return {
    viewport: "1440x900",
    duration_ms: Math.round(performance.now() - started),
    frames: frameDurations.length,
    average_fps: Number(((frameDurations.length * 1_000) / (performance.now() - started)).toFixed(1)),
    p10_fps: Number((frameRates[Math.floor(frameRates.length * 0.1)] ?? 0).toFixed(1)),
    longest_task_ms: Number(Math.max(0, ...longTasks).toFixed(1)),
    effects: {
      sun: true,
      sun_bloom: false,
      bloom: false,
      starfield: true,
      aperture_light_sheet: true,
      sampled_spacecraft: true,
    },
    measured_at: new Date().toISOString(),
  };
});

await page.screenshot({ path: path.join(output, "performance-overlay-1440.png") });
await writeFile(path.join(output, "performance.json"), `${JSON.stringify(sample, null, 2)}\n`);
await browser.close();
process.stdout.write(`${JSON.stringify(sample, null, 2)}\n`);
if (sample.p10_fps < 50) process.exitCode = 2;
