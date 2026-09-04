'use strict';
const { chromium } = require('playwright');

const BASE_URL = process.env.QA_BASE_URL || 'http://localhost:5180';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();
  page.on('response', (res) => {
    if (res.status() >= 400) {
      console.log(res.status(), res.request().method(), res.url());
    }
  });
  await page.goto(`${BASE_URL}/`, { waitUntil: 'load', timeout: 20000 });
  await page.waitForTimeout(4000);
  await browser.close();
})();
