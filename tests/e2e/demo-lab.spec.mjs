/**
 * Gen 2 — Playwright smoke: lab UI on :8042, capabilities, unified pipeline.
 */
import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../..');
const FIXTURE = path.join(ROOT, 'tests', 'fixtures', 'comic_2x2.png');

function requireComicFixture() {
  if (!fs.existsSync(FIXTURE)) {
    throw new Error(
      'Missing tests/fixtures/comic_2x2.png — run: python scripts/generate_comic_fixture.py',
    );
  }
}

async function waitForHealth(maxMs = 20000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    try {
      const res = await fetch('http://127.0.0.1:8042/health');
      if (res.ok) {
        const body = await res.json();
        if (body.version >= 5) return body;
      }
    } catch { /* retry */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  return null;
}

let labProc;

test.beforeAll(async () => {
  requireComicFixture();
  labProc = spawn('python', ['-m', 'lookbook.lab_server'], {
    cwd: ROOT,
    env: { ...process.env },
    stdio: 'ignore',
    shell: true,
  });
  const health = await waitForHealth();
  if (!health) console.warn('lab_server v5 did not respond on :8042');
});

test.afterAll(async () => {
  if (labProc) labProc.kill('SIGTERM');
});

test('demo-lab loads from lab_server on 8042', async ({ page }) => {
  await page.goto('http://127.0.0.1:8042/');
  await expect(page.locator('h1')).toContainText('Demo Lab');
  await expect(page.locator('#runBtn')).toBeVisible();
});

test('health reports Gen 2 capabilities', async ({ request }) => {
  const res = await request.get('http://127.0.0.1:8042/health');
  test.skip(!res.ok(), 'lab_server not running');
  const body = await res.json();
  expect(body.ok).toBe(true);
  expect(body.version).toBeGreaterThanOrEqual(5);
  expect(body.capabilities).toBeTruthy();
  expect(typeof body.capabilities.ready_for_pipeline).toBe('boolean');
});

test('unified pipeline/run accepts upload', async ({ request }) => {
  const health = await request.get('http://127.0.0.1:8042/health');
  test.skip(!health.ok(), 'lab_server not running');
  const h = await health.json();
  test.skip(!h.capabilities?.ready_for_pipeline, 'lab deps not installed');

  const png = fs.readFileSync(FIXTURE);
  const boundary = '----PlaywrightBoundary';
  const body = Buffer.concat([
    Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="comic.png"\r\nContent-Type: image/png\r\n\r\n`),
    png,
    Buffer.from(`\r\n--${boundary}--\r\n`),
  ]);
  const res = await request.post('http://127.0.0.1:8042/api/pipeline/run', {
    headers: { 'Content-Type': `multipart/form-data; boundary=${boundary}` },
    data: body,
  });
  expect(res.ok()).toBeTruthy();
  const json = await res.json();
  expect(json.project_id).toBeTruthy();
  expect(json.pipeline.panel_count).toBeGreaterThanOrEqual(4);
  const interp = json.pipeline.interpretation;
  expect(interp).toBeTruthy();
  expect(Array.isArray(interp.scenes)).toBe(true);
  expect(interp.scenes.length).toBeGreaterThanOrEqual(1);

  const proj = await request.get(`http://127.0.0.1:8042/api/project/${json.project_id}`);
  expect(proj.ok()).toBeTruthy();
  const projBody = await proj.json();
  expect(projBody.analysis?.scene_graph?.scenes?.length).toBeGreaterThanOrEqual(1);
  expect(projBody.analysis?.ocr_result?.blocks?.length).toBeGreaterThanOrEqual(1);
});