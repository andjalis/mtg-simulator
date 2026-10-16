// Time the in-browser engine (web/static/local) in headless Chromium, desktop and phone-emulated.
//
//   python3 -m mtgsim.browser                       # build web/static/local/build first
//   NODE_PATH=$(npm root -g) node scripts/browser_bench.cjs [--pyodide DIR] [--games 20]
//       [--a 3-gold/boros_burn] [--b 3-gold/dimir_control]
//
// --pyodide serves a local Pyodide release (e.g. an unpacked `npm pack pyodide`) instead of the CDN.
// The phone profile is Playwright's Pixel 7 (mobile viewport, touch, user agent) on this machine's
// CPU: it checks the page works on a phone, not phone speed. Chrome's CPU throttling doesn't reach
// Web Workers, so phone speed has to be measured on a real device.
const http = require("http");
const fs = require("fs");
const path = require("path");
const {chromium, devices} = require("playwright");

const arg = (k, d) => { const i = process.argv.indexOf("--" + k); return i > 0 ? process.argv[i + 1] : d; };
const STATIC = path.resolve(__dirname, "..", "web", "static");
const PYODIDE = arg("pyodide");
const GAMES = +arg("games", 20);
const TYPES = {".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
               ".json": "application/json", ".zip": "application/zip", ".wasm": "application/wasm"};

function serve() {
  return new Promise(res => {
    const srv = http.createServer((req, resp) => {
      let url = decodeURIComponent(req.url.split("?")[0]);
      let root = STATIC;
      if (PYODIDE && url.startsWith("/pyodide/")) { root = path.resolve(PYODIDE); url = url.slice(8); }
      const file = path.join(root, url.endsWith("/") ? url + "index.html" : url);
      if (!file.startsWith(root) || !fs.existsSync(file)) { resp.writeHead(404); return resp.end(); }
      resp.writeHead(200, {"Content-Type": TYPES[path.extname(file)] || "application/octet-stream"});
      fs.createReadStream(file).pipe(resp);
    }).listen(0, "127.0.0.1", () => res(srv));
  });
}

async function run(browser, base, label, context, workers) {
  const ctx = await browser.newContext(context);
  const page = await ctx.newPage();
  let bytes = 0;
  page.on("response", async r => { try { bytes += (await r.body()).length; } catch {} });
  const q = "?workers=" + workers + (PYODIDE ? "&pyodide=" + encodeURIComponent(base + "/pyodide/") : "");
  await page.goto(base + "/local/" + q);
  await page.waitForFunction(() => window.engineLoadMs || window.runError, null, {timeout: 300000});
  const loadMs = await page.evaluate(() => window.engineLoadMs);
  await page.selectOption("#a", arg("a", "3-gold/boros_burn"));
  await page.selectOption("#b", arg("b", "3-gold/dimir_control"));
  await page.fill("#n", String(GAMES));
  await page.click("#go");
  await page.waitForFunction(() => window.runResult || window.runError, null, {timeout: 600000});
  const [r, err] = await page.evaluate(() => [window.runResult, window.runError]);
  if (err) throw new Error(err);
  console.log(`${label}: engine load ${(loadMs / 1000).toFixed(1)} s, ` +
              `${(1000 * r.seconds / r.games).toFixed(0)} ms/game engine, ${(1000 * r.wall / r.games).toFixed(0)} ms/game wall, ${r.workers} worker(s), ` +
              `${r.games} games, A won ${r.wins_a}, ${(bytes / 1048576).toFixed(1)} MB downloaded (uncompressed)`);
  await ctx.close();
}

(async () => {
  const srv = await serve();
  const base = "http://127.0.0.1:" + srv.address().port;
  const browser = await chromium.launch();
  try {
    await run(browser, base, "desktop, 1 worker", {}, 1);
    await run(browser, base, "desktop, 4 workers", {}, 4);
    await run(browser, base, "Pixel 7 emulation, 1 worker", devices["Pixel 7"], 1);
  } finally {
    await browser.close();
    srv.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
