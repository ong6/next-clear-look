#!/usr/bin/env node

import { brotliCompressSync, constants } from 'node:zlib';
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const dist = path.join(root, 'web', 'dist');
const html = await readFile(path.join(dist, 'index.html'), 'utf8');
const initialUrls = new Set(
  [...html.matchAll(/<(?:script|link)[^>]+(?:src|href)="([^"]+\.js)"/g)]
    .map((match) => match[1].replace(/^\//, '')),
);
const assetDirectory = path.join(dist, 'assets');
const javascriptFiles = (await readdir(assetDirectory))
  .filter((name) => name.endsWith('.js'))
  .map((name) => `assets/${name}`)
  .sort();

const chunks = [];
for (const relative of javascriptFiles) {
  const body = await readFile(path.join(dist, relative));
  const brotliBytes = brotliCompressSync(body, {
    params: { [constants.BROTLI_PARAM_QUALITY]: 11 },
  }).length;
  chunks.push({
    file: relative,
    rawBytes: body.length,
    brotliBytes,
    initial: initialUrls.has(relative),
  });
}

const initialBrotliBytes = chunks
  .filter((chunk) => chunk.initial)
  .reduce((total, chunk) => total + chunk.brotliBytes, 0);
const lazyChunks = chunks.filter((chunk) => !chunk.initial);
const largestLazyChunk = [...lazyChunks].sort(
  (left, right) => right.brotliBytes - left.brotliBytes,
)[0] ?? null;
const limitBytes = Math.floor(1.2 * 1024 * 1024);
const report = {
  initialBrotliBytes,
  initialLimitBytes: limitBytes,
  initialChunks: chunks.filter((chunk) => chunk.initial),
  lazyChunks,
  largestLazyChunk,
};
await mkdir(path.join(root, '.local', 'reports'), { recursive: true });
await writeFile(
  path.join(root, '.local', 'reports', 'bundle-budget.json'),
  `${JSON.stringify(report, null, 2)}\n`,
);
process.stdout.write(`${JSON.stringify(report)}\n`);
if (initialBrotliBytes > limitBytes) process.exitCode = 1;
