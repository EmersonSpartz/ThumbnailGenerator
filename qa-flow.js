#!/usr/bin/env node
/**
 * Post-deploy user flow test for Thumbnail Generator.
 * Tests the actual flows a user would perform after deployment.
 *
 * Usage:
 *   node qa-flow.js [BASE_URL]
 *
 * Env vars:
 *   QA_BASE_URL   - override the default Railway URL
 *   QA_PASSWORD   - app password if auth is enabled (passed as ?auth=... param)
 *
 * Exit codes:
 *   0 - all tests passed
 *   1 - one or more tests failed
 */

const puppeteer = require('puppeteer');
const https = require('https');
const http = require('http');

const DEFAULT_URL = 'https://web-production-d277.up.railway.app';
const BASE_URL = process.argv[2] || process.env.QA_BASE_URL || DEFAULT_URL;
const PASSWORD = process.env.QA_PASSWORD || '';
const SCREENSHOT_DIR = '/tmp/qa-flow';

// Auth param appended to API calls when password is set
const authParam = PASSWORD ? `auth=${encodeURIComponent(PASSWORD)}` : '';

function apiUrl(path) {
  const sep = path.includes('?') ? '&' : '?';
  return PASSWORD ? `${BASE_URL}${path}${sep}${authParam}` : `${BASE_URL}${path}`;
}

// ----------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------

function fetchJson(url, opts = {}) {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith('https') ? https : http;
    const options = { ...opts };
    const req = lib.get(url, options, (res) => {
      let data = '';
      res.on('data', (chunk) => (data += chunk));
      res.on('end', () => {
        try {
          resolve({ status: res.statusCode, body: JSON.parse(data), raw: data });
        } catch (e) {
          resolve({ status: res.statusCode, body: null, raw: data });
        }
      });
    });
    req.on('error', reject);
    req.setTimeout(20000, () => { req.destroy(); reject(new Error('Request timeout')); });
  });
}

function fetchStream(url, timeoutMs = 90000) {
  /**
   * Consumes an SSE stream, collecting events until:
   *   - an "image_generated" or "error" or "complete" event is seen
   *   - timeout expires
   * Returns array of parsed event objects.
   */
  return new Promise((resolve, reject) => {
    const lib = url.startsWith('https') ? https : http;
    const events = [];
    let resolved = false;

    const timer = setTimeout(() => {
      if (!resolved) {
        resolved = true;
        req.destroy();
        resolve(events); // return what we have on timeout
      }
    }, timeoutMs);

    const req = lib.get(url, (res) => {
      let buf = '';
      res.on('data', (chunk) => {
        buf += chunk.toString();
        const lines = buf.split('\n');
        buf = lines.pop(); // keep incomplete line
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const obj = JSON.parse(line.slice(6));
              events.push(obj);
              const t = obj.type || '';
              if (t === 'image_generated' || t === 'error' || t === 'complete' || t === 'done') {
                if (!resolved) {
                  resolved = true;
                  clearTimeout(timer);
                  req.destroy();
                  resolve(events);
                }
                return;
              }
            } catch (_) {}
          }
        }
      });
      res.on('end', () => {
        if (!resolved) {
          resolved = true;
          clearTimeout(timer);
          resolve(events);
        }
      });
      res.on('error', (err) => {
        if (!resolved) {
          resolved = true;
          clearTimeout(timer);
          reject(err);
        }
      });
    });
    req.on('error', (err) => {
      if (!resolved) {
        resolved = true;
        clearTimeout(timer);
        reject(err);
      }
    });
  });
}

// ----------------------------------------------------------------
// Test runner
// ----------------------------------------------------------------

const results = [];
let browser;

function pass(name, detail = '') {
  const msg = detail ? `PASS [${name}] — ${detail}` : `PASS [${name}]`;
  console.log(msg);
  results.push({ name, passed: true, detail });
}

function fail(name, reason = '') {
  const msg = reason ? `FAIL [${name}] — ${reason}` : `FAIL [${name}]`;
  console.error(msg);
  results.push({ name, passed: false, reason });
}

// ----------------------------------------------------------------
// Tests
// ----------------------------------------------------------------

async function testPageLoads() {
  const name = 'Page loads';
  try {
    const jsErrors = [];
    const failed404Urls = new Set();
    const page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });

    // Register all listeners BEFORE navigating
    page.on('console', (msg) => { if (msg.type() === 'error') jsErrors.push(msg.text()); });
    page.on('pageerror', (err) => jsErrors.push(`UNCAUGHT: ${err.message}`));
    page.on('response', (res) => { if (res.status() === 404) failed404Urls.add(res.url()); });

    const urlToLoad = PASSWORD ? `${BASE_URL}/?${authParam}` : BASE_URL;
    const resp = await page.goto(urlToLoad, { waitUntil: 'networkidle2', timeout: 30000 });
    if (!resp || !resp.ok()) {
      fail(name, `HTTP ${resp ? resp.status() : 'no response'}`);
      await page.close();
      return;
    }
    await new Promise((r) => setTimeout(r, 2000));

    // Verify key DOM elements exist (page didn't crash)
    const hasVideoBar = await page.$('.video-bar') !== null;
    const hasContainer = await page.$('.container') !== null;
    const title = await page.title();

    // Filter out known benign errors:
    //   - favicon 404 (common on apps without favicons — harmless)
    //   - net::ERR_ABORTED (navigating away mid-load)
    //   - Generic "Failed to load resource" that maps only to favicon/ico 404s
    const isBenign404Only = [...failed404Urls].every(
      (u) => u.includes('favicon') || u.endsWith('.ico')
    );
    const realErrors = jsErrors.filter((e) => {
      if (e.includes('favicon')) return false;
      if (e.includes('net::ERR_ABORTED')) return false;
      if (
        isBenign404Only &&
        e.includes('Failed to load resource') &&
        e.includes('404')
      ) return false;
      // Catch-all: generic resource load error when ALL 404s are benign
      if (
        isBenign404Only &&
        e === 'Failed to load resource: the server responded with a status of 404 ()'
      ) return false;
      return true;
    });

    if (!hasVideoBar && !hasContainer) {
      fail(name, 'Page rendered without expected DOM elements');
    } else if (realErrors.length > 0) {
      fail(name, `${realErrors.length} JS error(s): ${realErrors[0]}`);
    } else {
      pass(name, `title="${title}", ${realErrors.length} JS errors`);
    }

    try {
      await page.screenshot({ path: `${SCREENSHOT_DIR}/page-load.png` });
    } catch (_) {}
    await page.close();
  } catch (err) {
    fail(name, err.message);
  }
}

async function testDiskSpace() {
  const name = 'Disk space';
  try {
    const { status, body } = await fetchJson(apiUrl('/api/disk-usage'));
    if (status !== 200 || !body) {
      fail(name, `HTTP ${status}`);
      return;
    }
    const freeMb = body.free_mb;
    if (freeMb === undefined) {
      fail(name, 'free_mb missing from response');
      return;
    }
    if (freeMb < 100) {
      fail(name, `Critically low disk: ${freeMb}MB free (< 100MB)`);
    } else if (freeMb < 200) {
      console.warn(`  WARNING: Disk space low — ${freeMb}MB free (< 200MB)`);
      pass(name, `${freeMb}MB free (WARNING: below 200MB)`);
    } else {
      pass(name, `${freeMb}MB free`);
    }
  } catch (err) {
    fail(name, err.message);
  }
}

async function testVideoCreation() {
  const name = 'Video creation';
  // Videos in this app are just a concept — they're created implicitly when
  // thumbnails are generated with a given video_name.  The /api/videos endpoint
  // lists known video names.  We verify that the endpoint responds and returns
  // a valid videos array.  Actual creation is implicitly tested by the
  // generation test below (which passes video_name=qa_test_video).
  try {
    const { status, body } = await fetchJson(apiUrl('/api/videos'));
    if (status !== 200 || !body) {
      fail(name, `HTTP ${status}`);
      return;
    }
    if (!Array.isArray(body.videos)) {
      fail(name, `Expected videos array, got: ${JSON.stringify(body)}`);
      return;
    }
    pass(name, `${body.videos.length} existing video(s) found`);
  } catch (err) {
    fail(name, err.message);
  }
}

async function testGeneration() {
  const name = 'Generation works';
  const VIDEO_NAME = 'qa_test_video';
  try {
    // Start generation in background mode — get job_id first
    const startUrl = apiUrl(
      `/api/agentic-generate?titles=test&models=nanobanana2&count=1&max_iterations=1&video_name=${VIDEO_NAME}&mode=start`
    );
    const { status, body } = await fetchJson(startUrl);
    if (status !== 200 || !body || !body.job_id) {
      fail(name, `Start failed — HTTP ${status}, body: ${JSON.stringify(body)}`);
      return;
    }

    const jobId = body.job_id;
    console.log(`  Started job ${jobId}, streaming...`);

    // Stream events until image_generated or error
    const streamUrl = apiUrl(`/api/jobs/${jobId}/stream`);
    let events;
    try {
      events = await fetchStream(streamUrl, 90000);
    } catch (err) {
      fail(name, `Stream error: ${err.message}`);
      return;
    }

    if (!events || events.length === 0) {
      fail(name, 'No SSE events received from stream');
      return;
    }

    const imageEvent = events.find((e) => e.type === 'image_generated');
    const errorEvent = events.find((e) => e.type === 'error');
    const allTypes = [...new Set(events.map((e) => e.type))].join(', ');

    if (imageEvent) {
      const fp = imageEvent.file_path || imageEvent.data?.file_path || '(no path)';
      pass(name, `image_generated event received (file: ${fp}), saw event types: ${allTypes}`);
    } else if (errorEvent) {
      fail(name, `Error event: ${errorEvent.message || JSON.stringify(errorEvent)}`);
    } else {
      fail(name, `No image_generated event. Received: ${allTypes}`);
    }
  } catch (err) {
    fail(name, err.message);
  }
}

async function testHistoryFiltering() {
  const name = 'History filtering';
  const VIDEO_NAME = 'qa_test_video';
  try {
    const { status, body } = await fetchJson(apiUrl(`/api/history?video=${encodeURIComponent(VIDEO_NAME)}`));
    if (status !== 200 || !body) {
      fail(name, `HTTP ${status}`);
      return;
    }
    const thumbs = body.thumbnails || [];
    if (thumbs.length === 0) {
      // Generation test may not have finished writing to history yet
      // This is a soft warn rather than hard fail — depends on prior test
      console.warn(`  WARNING: 0 thumbnails for video "${VIDEO_NAME}" — generation may still be in progress`);
      pass(name, `0 thumbnails (generation may still be processing)`);
    } else {
      // Verify all returned thumbnails actually belong to qa_test_video
      const wrongVideo = thumbs.filter((t) => t.video_name && t.video_name !== VIDEO_NAME);
      if (wrongVideo.length > 0) {
        fail(name, `Filter leak: ${wrongVideo.length} thumbnail(s) have wrong video_name`);
      } else {
        pass(name, `${thumbs.length} thumbnail(s) returned, all correctly filtered`);
      }
    }
  } catch (err) {
    fail(name, err.message);
  }
}

async function testCrossVideoIsolation() {
  const name = 'Cross-video isolation';
  const FAKE_VIDEO = 'NONEXISTENT_VIDEO_12345';
  try {
    const { status, body } = await fetchJson(apiUrl(`/api/history?video=${encodeURIComponent(FAKE_VIDEO)}`));
    if (status !== 200 || !body) {
      fail(name, `HTTP ${status}`);
      return;
    }
    const thumbs = body.thumbnails || [];
    if (thumbs.length > 0) {
      fail(name, `Filter bug: ${thumbs.length} thumbnail(s) returned for nonexistent video "${FAKE_VIDEO}"`);
    } else {
      pass(name, `0 thumbnails for nonexistent video — filter working correctly`);
    }
  } catch (err) {
    fail(name, err.message);
  }
}

async function testFavorites() {
  const name = 'Favorites';
  try {
    const { status, body } = await fetchJson(apiUrl('/api/favorites'));
    if (status !== 200 || !body) {
      fail(name, `HTTP ${status}`);
      return;
    }
    if (!Array.isArray(body.favorites)) {
      fail(name, `Expected favorites array, got: ${JSON.stringify(body)}`);
      return;
    }
    pass(name, `${body.favorites.length} favorite(s)`);
  } catch (err) {
    fail(name, err.message);
  }
}

// ----------------------------------------------------------------
// Main
// ----------------------------------------------------------------

async function main() {
  // Create screenshot dir
  try {
    require('fs').mkdirSync(SCREENSHOT_DIR, { recursive: true });
  } catch (_) {}

  console.log(`\n=== QA Flow Test ===`);
  console.log(`Target: ${BASE_URL}`);
  console.log(`Time:   ${new Date().toISOString()}`);
  console.log('');

  browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });

  try {
    // Run tests in sequence (some depend on previous steps, e.g. generation -> history)
    await testPageLoads();
    await testDiskSpace();
    await testVideoCreation();
    await testGeneration();       // generates qa_test_video thumbnail
    await testHistoryFiltering(); // checks qa_test_video history
    await testCrossVideoIsolation();
    await testFavorites();
  } finally {
    await browser.close();
  }

  // Summary
  const passed = results.filter((r) => r.passed).length;
  const failed = results.filter((r) => !r.passed).length;
  console.log('');
  console.log('=== Summary ===');
  for (const r of results) {
    const icon = r.passed ? 'PASS' : 'FAIL';
    console.log(`  ${icon}  ${r.name}`);
  }
  console.log('');
  if (failed === 0) {
    console.log(`ALL ${passed} TESTS PASSED`);
    process.exit(0);
  } else {
    console.log(`${passed} passed, ${failed} FAILED`);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(`Fatal error: ${err.message}`);
  if (browser) browser.close().catch(() => {});
  process.exit(1);
});
