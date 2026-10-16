// Plays game chunks for the main page on the visitor's own device: the built-in Python engine,
// run by Pyodide off the main thread. The page starts one worker per spare core.
// In:  {type: "cards", cards} once, then {type: "play", id, me, opp, games, seed}
// Out: {type: "ready", loadMs} | {type: "result", id, result} | {type: "error", id?, message}
const params = new URL(self.location.href).searchParams;
const PYODIDE = params.get("pyodide") || "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/";

// The result has the same keys as web/sim.py's _play_chunk, so the server can't tell them apart.
const GLUE = `
from mtgsim.carddb import CardDB
from mtgsim.runner import build_deck, run_match

DB = CardDB(offline=True)

def add_cards(cards):
    for card in cards:
        DB.raw[card["name"].lower()] = card

def play(me, opp, games, seed):
    res, _ = run_match("me", build_deck(DB, me), "opp", build_deck(DB, opp), games=games, seed=seed)
    return {"games": res.games, "wins": res.wins_a, "losses": res.wins_b, "draws": res.draws,
            "on_play_wins": res.wins_a_on_play, "on_play_games": res.games_a_on_play,
            "turns": sum(res.turns)}
`;

const ready = (async () => {
  const t0 = performance.now();
  importScripts(PYODIDE + "pyodide.js");
  const [py, zip] = await Promise.all([
    loadPyodide({indexURL: PYODIDE}),
    fetch(new URL("/engine/mtgsim.zip", self.location.href)).then(r => {
      if (!r.ok) throw new Error("engine download failed: " + r.status);
      return r.arrayBuffer();
    }),
  ]);
  py.unpackArchive(zip, "zip", {extractDir: "/home/pyodide"});
  py.runPython(GLUE);
  return {py, loadMs: performance.now() - t0};
})();

ready.then(({loadMs}) => postMessage({type: "ready", loadMs}),
           e => postMessage({type: "error", message: String(e)}));

onmessage = async ({data}) => {
  let id;
  try {
    const {py} = await ready;
    if (data.type === "cards") {
      py.globals.get("add_cards")(py.toPy(data.cards));
    } else if (data.type === "play") {
      id = data.id;
      const r = py.globals.get("play")(py.toPy(data.me), py.toPy(data.opp), data.games, data.seed);
      postMessage({type: "result", id, result: r.toJs({dict_converter: Object.fromEntries})});
      r.destroy();
    }
  } catch (e) {
    postMessage({type: "error", id, message: String(e)});
  }
};
