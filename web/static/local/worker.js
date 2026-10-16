// Runs the built-in Python engine inside the browser with Pyodide, off the main thread.
// Messages in:  {type: "run", deckA, deckB, games, seed, chunk}
// Messages out: {type: "ready", loadMs} | {type: "progress", result} | {type: "done", result} | {type: "error", message}
const params = new URL(self.location.href).searchParams;
const PYODIDE = params.get("pyodide") || "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/";
const BUILD = new URL("build/", self.location.href).href;

let ready = (async () => {
  const t0 = performance.now();
  importScripts(PYODIDE + "pyodide.js");
  const [py, zip, cards] = await Promise.all([
    loadPyodide({indexURL: PYODIDE}),
    fetch(BUILD + "mtgsim.zip").then(r => r.arrayBuffer()),
    fetch(BUILD + "cards.json").then(r => r.text()),
  ]);
  py.unpackArchive(zip, "zip", {extractDir: "/home/pyodide"});
  py.globals.set("CARDS_JSON", cards);
  py.runPython("import json, mtgsim.browser as mb; CARDS = json.loads(CARDS_JSON)");
  return {py, loadMs: performance.now() - t0};
})();

ready.then(({loadMs}) => postMessage({type: "ready", loadMs}),
           e => postMessage({type: "error", message: String(e)}));

onmessage = async ({data}) => {
  if (data.type !== "run") return;
  try {
    const {py} = await ready;
    const runChunk = py.runPython(`lambda a, b, n, seed: mb.run_local(CARDS, a.to_py(), b.to_py(), n, seed)`);
    const total = {games: 0, wins_a: 0, wins_b: 0, draws: 0, wins_a_on_play: 0, games_a_on_play: 0, turns: [], seconds: 0};
    const chunk = data.chunk || 10;
    for (let done = 0; done < data.games; done += chunk) {
      const n = Math.min(chunk, data.games - done);
      // Each chunk gets its own seed so a run is reproducible; seats alternate within a chunk.
      const r = runChunk(data.deckA, data.deckB, n, (data.seed ?? 0) * 1000003 + done).toJs({dict_converter: Object.fromEntries});
      for (const k of ["games", "wins_a", "wins_b", "draws", "wins_a_on_play", "games_a_on_play", "seconds"]) total[k] += r[k];
      total.turns.push(...r.turns);
      postMessage({type: done + n < data.games ? "progress" : "done", result: total});
    }
  } catch (e) {
    postMessage({type: "error", message: String(e)});
  }
};
