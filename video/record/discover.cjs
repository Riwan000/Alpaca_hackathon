'use strict';
const { chromium } = require('playwright');

const BASE_URL = process.env.QA_BASE_URL || 'http://localhost:5180';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();
  page.on('console', (m) => console.log('[console]', m.type(), m.text()));
  page.on('pageerror', (e) => console.log('[pageerror]', e.message));

  for (const route of ['/', '/adaptation', '/configuration']) {
    console.log('\n=== ROUTE', route, '===');
    await page.goto(`${BASE_URL}${route}`, { waitUntil: 'load', timeout: 20000 }).catch((e) => console.log('goto error', e.message));
    await page.waitForTimeout(1500);
    const title = await page.title();
    console.log('title:', title);
    const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 800));
    console.log('bodyTextSample:', bodyText.replace(/\n+/g, ' | '));
    const testIds = await page.evaluate(() =>
      Array.from(document.querySelectorAll('[data-testid]')).map((el) => el.getAttribute('data-testid'))
    );
    console.log('testIds:', JSON.stringify(testIds));
    const navLinks = await page.evaluate(() =>
      Array.from(document.querySelectorAll('a')).map((a) => ({ href: a.getAttribute('href'), text: a.textContent.trim().slice(0, 30) }))
    );
    console.log('links:', JSON.stringify(navLinks));
  }

  await browser.close();
})();
