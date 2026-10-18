// Optional real-browser regression pass. No application dependencies are added.
// Start an isolated server: MTGSIM_HISTORY=/tmp/ui-history.sqlite3 python3 -m web --offline --jobs 2 --port 8137
// npm install --prefix /tmp/mtgsim-ui playwright
// NODE_PATH=/tmp/mtgsim-ui/node_modules node scripts/ui_qa.cjs
// Override UI_URL, CHROMIUM_PATH, and UI_ARTIFACTS if needed.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const base = process.env.UI_URL || 'http://127.0.0.1:8137';
const artifacts = process.env.UI_ARTIFACTS || '/tmp/mtgsim-ui-artifacts';

(async () => {
  await fs.mkdir(artifacts, {recursive: true});
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true});
  try {
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    // External fonts aren't needed to verify behavior, and offline failures shouldn't stall navigation.
    await context.route('https://fonts.googleapis.com/**', r => r.abort());
    let failSetup = true;
    await page.route('**/api/tiers', r => failSetup ? r.abort() : r.continue());
    await page.goto(base + '/?run=server', {waitUntil: 'domcontentloaded'});
    await page.locator('#retrySetup').waitFor({state: 'visible'});
    await page.locator('#deck').fill('60 Mountain');
    await page.waitForFunction(() => document.querySelector('#check').textContent.includes('60 cards'));
    assert(await page.locator('#go').isDisabled(), 'cannot start before ranks load');
    failSetup = false;
    await page.locator('#retrySetup').click();
    await page.waitForFunction(() => !document.querySelector('#go').disabled);
    assert.equal(await page.locator('#tierList input').count(), 7);
    assert.match(await page.locator('#engine').innerText(), /server/);
    for (const deck of ['0 Mountain', '999999999999999 Mountain']) {
      await page.locator('#deck').fill(deck);
      await page.locator('#check .err').waitFor({state: 'visible'});
      assert(await page.locator('#go').isDisabled(), 'invalid deck remains blocked');
    }
    await page.locator('#deck').fill('60 Mountain');
    await page.waitForFunction(() => !document.querySelector('#go').disabled);
    await page.locator('[data-mode=tiers]').click();
    for (const input of await page.locator('#tierList input').all()) await input.uncheck();
    await page.locator('#go').click();
    assert(await page.locator('#runError').isVisible());
    await page.locator('#tierList input[value=bronze]').check();
    assert(await page.locator('#runError').isHidden(), 'correcting rank choice clears stale error');
    await page.locator('#games').fill('2');
    await page.locator('#grade').uncheck();
    await page.locator('#name').fill('UI regression');
    let posts = 0;
    page.on('request', r => { if (r.url().endsWith('/api/run')) posts++; });
    await page.locator('#go').click();
    await page.waitForFunction(() => document.querySelector('.trial-page').dataset.screen === 'results', null, {timeout: 120000});
    assert.equal(await page.evaluate(() => document.activeElement.id), 'resultTitle');
    assert.match(await page.locator('.run-metrics').innerText(), /10/);
    await page.reload({waitUntil: 'domcontentloaded'});
    await page.waitForFunction(() => document.querySelector('.trial-page').dataset.screen === 'results');
    assert.equal(posts, 1, 'refresh restores the existing trial without submitting another');
    await page.screenshot({path: artifacts + '/desktop-results.png', fullPage: true});
    await page.locator('#nextTrial').click();
    assert.equal(await page.evaluate(() => document.activeElement.id), 'loadoutTitle');
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({width, height: 900});
      assert(await page.locator('.leaderboard-link').isVisible(), 'leaderboard navigation visible at ' + width);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'no loadout horizontal overflow at ' + width);
      assert(await page.locator('#ladder').evaluate(el => {
        const labels = [...el.querySelectorAll('.step b')].map(b => b.getBoundingClientRect());
        return labels.every((a, i) => labels.every((b, j) => i === j || a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top));
      }), 'league names do not overlap at ' + width);
      if (width < 600) {
        for (const selector of ['#fullscreen', '#mode button', 'label:has(#fx)']) {
          assert((await page.locator(selector).first().boundingBox()).height >= 44, 'mobile touch target: ' + selector);
        }
      }
      await page.screenshot({path: artifacts + '/loadout-' + width + '.png', fullPage: true});
    }
    await page.goto(base + '/leaderboard', {waitUntil: 'domcontentloaded'});
    await page.setViewportSize({width: 320, height: 900});
    await page.waitForFunction(() => getComputedStyle(document.querySelector('.masthead .in')).display === 'flex');
    await page.screenshot({path: artifacts + '/leaderboard-320.png', fullPage: true});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'no leaderboard header overflow');
    assert.deepEqual(errors, [], 'no unhandled browser errors');
    await context.close();
    console.log('PASS: forms, bootstrap recovery, real trial, saved-session restore, navigation, responsive layout');

    const recovery = await browser.newContext();
    await recovery.route('https://fonts.googleapis.com/**', r => r.abort());
    await recovery.addInitScript(() => sessionStorage.setItem('mtgsim.trial', 'qa-recovery'));
    const p = await recovery.newPage();
    let failPoll = false, gets = 0;
    await p.route('**/api/runs/qa-recovery', r => {
      gets++;
      return failPoll ? r.abort() : r.fulfill({json: {status: 'running', deck: 'Recovery QA', tiers: [], current: 'Bronze', total: 100, done: 0, pass_rate: .5, games_per_opponent: 100, ladder: true, where: 'server'}});
    });
    await p.goto(base + '/?run=server', {waitUntil: 'domcontentloaded'});
    await p.waitForFunction(() => document.querySelector('.trial-page').dataset.screen === 'arena');
    await p.reload({waitUntil: 'domcontentloaded'});
    await p.waitForFunction(() => document.querySelector('.trial-page').dataset.screen === 'arena');
    assert(gets >= 2, 'active session restores polling after reload');
    failPoll = true;
    await p.locator('#retryTrial').waitFor({state: 'visible'});
    assert.doesNotMatch(await p.locator('#arenaActionHint').innerText(), /completed arena/);
    failPoll = false;
    await p.locator('#retryTrial').click();
    await p.waitForFunction(() => document.querySelector('#retryTrial').hidden && document.querySelector('#configure').disabled);
    await recovery.close();
    console.log('PASS: mocked active-trial refresh, interrupted polling, reconnect');

    const expired = await browser.newContext();
    await expired.addInitScript(() => sessionStorage.setItem('mtgsim.trial', 'expired'));
    const missing = await expired.newPage();
    await missing.route('**/api/runs/expired', r => r.fulfill({status: 404, json: {error: 'no such run'}}));
    await missing.goto(base + '/?run=server', {waitUntil: 'domcontentloaded'});
    await missing.locator('#runError').filter({hasText: 'no longer available'}).waitFor();
    assert.equal(await missing.evaluate(() => sessionStorage.getItem('mtgsim.trial')), null);
    assert(await missing.locator('#retryTrial').isHidden());
    await expired.close();
    console.log('PASS: expired session clears stale trial and explains recovery');

    const fallback = await browser.newContext();
    await fallback.route('https://cdn.jsdelivr.net/**', r => r.abort());
    const devicePage = await fallback.newPage();
    await devicePage.goto(base + '/', {waitUntil: 'domcontentloaded'});
    await devicePage.locator('#engine').filter({hasText: "Games run on the server: this browser couldn't run the engine"}).waitFor();
    await devicePage.locator('#deck').fill('60 Mountain');
    await devicePage.waitForFunction(() => !document.querySelector('#go').disabled);
    await fallback.close();
    console.log('PASS: blocked browser-engine download explains server fallback');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
