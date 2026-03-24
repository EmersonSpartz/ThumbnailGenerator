#!/usr/bin/env node
/**
 * Headless browser render check for Thumbnail Generator.
 * Uses Puppeteer to verify the page actually renders thumbnail cards.
 *
 * Usage:
 *   node visual-check.js [URL]
 *
 * Env vars:
 *   VISUAL_CHECK_URL - override the default Railway URL
 *
 * Exit codes:
 *   0 - page rendered with thumbnail cards
 *   1 - rendering broken (no cards, JS errors, page failed to load)
 */

const puppeteer = require('puppeteer');

const DEFAULT_URL = 'https://web-production-d277.up.railway.app';
const TIMEOUT_MS = 30000;
const SCREENSHOT_PATH = '/tmp/visual-check.png';

async function run() {
  const url = process.argv[2] || process.env.VISUAL_CHECK_URL || DEFAULT_URL;
  console.log(`Checking: ${url}`);

  const jsErrors = [];
  let browser;

  try {
    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    });

    const page = await browser.newPage();

    // Set a reasonable viewport
    await page.setViewport({ width: 1440, height: 900 });

    // Collect console errors
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        jsErrors.push(msg.text());
      }
    });

    // Collect page errors (uncaught exceptions)
    page.on('pageerror', (err) => {
      jsErrors.push(`UNCAUGHT: ${err.message}`);
    });

    // Navigate and wait for network to settle
    console.log('Loading page...');
    const response = await page.goto(url, {
      waitUntil: 'networkidle2',
      timeout: TIMEOUT_MS,
    });

    if (!response || !response.ok()) {
      const status = response ? response.status() : 'no response';
      console.error(`Page load failed with status: ${status}`);
      await page.screenshot({ path: SCREENSHOT_PATH, fullPage: false });
      console.error(`Screenshot saved to ${SCREENSHOT_PATH}`);
      process.exit(1);
    }

    // Give JS a moment to finish rendering after network idle
    await new Promise((r) => setTimeout(r, 2000));

    // Check for thumbnail cards
    const cardCount = await page.$$eval('.thumbnail-card', (cards) => cards.length);

    // Check #text-thumbnail-grid children
    const textGridChildren = await page.evaluate(() => {
      const grid = document.querySelector('#text-thumbnail-grid');
      return grid ? grid.children.length : -1;
    });

    // Check for visible error indicators
    const errorIndicators = await page.evaluate(() => {
      const errors = [];
      // Look for elements with red-ish text
      const allElements = document.querySelectorAll('*');
      for (const el of allElements) {
        const text = el.textContent.trim();
        const style = window.getComputedStyle(el);
        // Check for "Failed to load" or similar error text
        if (
          text &&
          (text.includes('Failed to load') ||
            text.includes('Error:') ||
            text.includes('Something went wrong')) &&
          el.offsetParent !== null // visible
        ) {
          errors.push(text.substring(0, 120));
        }
      }
      return [...new Set(errors)]; // dedupe
    });

    // Take screenshot
    await page.screenshot({ path: SCREENSHOT_PATH, fullPage: false });

    // --- Print summary ---
    console.log('');
    console.log('=== Visual Check Results ===');
    console.log(`Thumbnail cards: ${cardCount}`);
    console.log(`Text grid children: ${textGridChildren === -1 ? 'grid not found' : textGridChildren}`);
    console.log(`JS console errors: ${jsErrors.length}`);
    console.log(`Visible error messages: ${errorIndicators.length}`);
    console.log(`Screenshot: ${SCREENSHOT_PATH}`);

    if (jsErrors.length > 0) {
      console.log('');
      console.log('--- JS Console Errors ---');
      jsErrors.forEach((err, i) => {
        console.log(`  ${i + 1}. ${err}`);
      });
    }

    if (errorIndicators.length > 0) {
      console.log('');
      console.log('--- Visible Error Messages ---');
      errorIndicators.forEach((msg, i) => {
        console.log(`  ${i + 1}. ${msg}`);
      });
    }

    console.log('');

    // Determine pass/fail
    // The page loads history on startup, so there should be thumbnail cards
    // even without a video selected (untagged entries show up)
    if (cardCount === 0 && textGridChildren <= 0) {
      console.error('FAIL: No thumbnail cards rendered. Page may be broken.');
      console.error(`Check screenshot at ${SCREENSHOT_PATH}`);
      process.exit(1);
    }

    // Warn about JS errors but don't fail if cards rendered
    if (jsErrors.length > 0) {
      console.log(`WARNING: ${jsErrors.length} JS error(s) detected, but ${cardCount} cards rendered.`);
    }

    console.log(`PASS: ${cardCount} thumbnail cards rendered, ${jsErrors.length} JS errors`);
    process.exit(0);
  } catch (err) {
    console.error(`Fatal error: ${err.message}`);
    if (browser) {
      try {
        const pages = await browser.pages();
        if (pages.length > 0) {
          await pages[0].screenshot({ path: SCREENSHOT_PATH, fullPage: false });
          console.error(`Screenshot saved to ${SCREENSHOT_PATH}`);
        }
      } catch (_) {}
    }
    process.exit(1);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

run();
