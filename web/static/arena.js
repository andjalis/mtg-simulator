// Shared by the deck page (index.html) and the replay on a saved run: the league track, the climb
// panel, the match ticker, sound and haptics, and the replay of a saved ladder run.
// Global names used by both pages: $, esc, pct, calm, rankList, passRate.
const $ = s => document.querySelector(s);
const pct = x => x == null ? "–" : (100 * x).toFixed(1) + "%";
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const calm = matchMedia("(prefers-reduced-motion: reduce)");
let rankList = [], passRate = 0.5;

// -- sound and haptics: off until the visitor turns them on (kept in this browser only) --------
const Fx = (() => {
  let ctx = null;
  const key = "mtgsim.fx";
  const get = () => { try { return localStorage.getItem(key) === "1"; } catch (e) { return false; } };
  const tone = (f, at, dur, type = "sine", vol = .09) => {
    const o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime + at;
    o.type = type; o.frequency.setValueAtTime(f, t);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol, t + .02); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(ctx.destination); o.start(t); o.stop(t + dur + .05);
  };
  const N = {c4: 262, e4: 330, g4: 392, a4: 440, c5: 523, e5: 659, g5: 784, c6: 1047, g3: 196, c3: 131, e3: 165};
  const sounds = {
    lock:    {buzz: [18, 40, 30], play: () => { tone(N.c3, 0, .35, "triangle", .16); tone(N.g3, .12, .25, "triangle", .1); tone(N.c6, .2, .12, "square", .04); }},
    cleared: {buzz: [25], play: () => [N.c5, N.e5, N.g5].forEach((f, i) => tone(f, i * .08, .22, "triangle"))},
    failed:  {buzz: [60, 40, 60], play: () => { tone(N.e3, 0, .3, "sawtooth", .06); tone(N.c3, .16, .4, "sawtooth", .06); }},
    promote: {buzz: [30, 40, 30, 40, 80], play: () => [N.c5, N.e5, N.g5, N.c6].forEach((f, i) => tone(f, i * .1, .3, "triangle", .1))},
    demote:  {buzz: [80], play: () => [N.g4, N.e4, N.c4].forEach((f, i) => tone(f, i * .12, .3, "triangle", .08))},
    final:   {buzz: [40, 60, 120], play: () => [N.c5, N.e5, N.g5, N.c6].forEach(f => tone(f, 0, .9, "sine", .06))},
  };
  return {
    get on() { return get(); },
    set(on) { try { localStorage.setItem(key, on ? "1" : "0"); } catch (e) {} if (on) this.wake(); },
    wake() {  // browsers only start audio after a click or key press
      try { ctx = ctx || new (window.AudioContext || window.webkitAudioContext)(); if (ctx.state === "suspended") ctx.resume(); } catch (e) { ctx = null; }
    },
    play(name) {
      if (!get() || !sounds[name]) return;
      if (ctx) try { sounds[name].play(); } catch (e) {}
      if (!calm.matches && navigator.vibrate) try { navigator.vibrate(sounds[name].buzz); } catch (e) {}
    },
    // wire a checkbox: it shows and sets the saved choice
    bind(input) {
      input.checked = get();
      input.addEventListener("change", () => { this.set(input.checked); if (input.checked) this.play("cleared"); });
    },
  };
})();

// Live trials and saved replays use the same arena rendering and motion.
let A = {};
function resetArena() {
  if (A.timers) A.timers.forEach(clearTimeout);
  if (A.frame) cancelAnimationFrame(A.frame);
  A = {track: {}, rank: null, mmr: null, displayedMMR: null, opps: {}, pools: new Set(), stamped: new Set(), graded: false, final: false, rows: {}, timers: new Set(), duels: {}, totals: {wins: 0, losses: 0, draws: 0}};
}
function arenaHTML() {
  return `<div class="arena pre" id="arena">
      <div class="climb" id="climb"><div class="badge"><div class="orbit"></div><div class="spin"></div></div>
        <div><div class="overline">CURRENT RATING</div><div class="rk"></div><div class="mmrv"><span class="n"></span><span class="d"></span></div>
        <div class="xp" role="progressbar" aria-label="Progress to next rank" aria-valuemin="0" aria-valuemax="100"><i></i></div><div class="sub"></div><div class="live"></div></div>
        <div class="banner" role="status" aria-live="polite"></div></div>
      <div class="scoreboard"><div><span>WINS</span><b id="winCount">0</b></div><div><span>LOSSES</span><b id="lossCount">0</b></div><div><span>DRAWS</span><b id="drawCount">0</b></div><div><span>SCORE</span><b id="scoreCount">—</b></div><p class="batch-update" role="status" aria-live="polite">Awaiting the first results</p></div>
      <div class="track" id="track"><div class="track-heading"><h3>LEAGUE MAP</h3><span>Win ${Math.round(passRate * 100)}% to advance</span></div><div class="callout" role="status" aria-live="polite"></div><div class="wrap"><div class="lane"><div class="rail"><i></i></div><div class="token"><b></b></div></div></div>
        <div class="duels" id="duels"></div></div>
      <div class="ticker"><div class="ticker-head"><h3>Battle feed</h3><span><i class="legend-win"></i> Win <i class="legend-loss"></i> Loss <i class="legend-draw"></i> Draw</span></div><div class="rows" id="ticks" aria-live="off"></div><p class="feed-note">Results arrive in batches. Tiles show the latest outcomes, not play order.</p></div>
    </div>`;
}
const later = (ms, fn) => {
  const run = A;
  if (calm.matches) { fn(); return; }
  const timer = setTimeout(() => { run.timers.delete(timer); if (A === run) fn(); }, ms);
  run.timers.add(timer);
};
const replay = (el, cls) => {
  if (calm.matches) return;
  el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls);
};
const oppName = n => n.split("/").pop().replace(/_/g, " ");

function stamp(key) {  // a rank row's cleared / failed chip lands with a stamp the first time it shows
  if (A.stamped.has(key)) return "";
  A.stamped.add(key);
  return calm.matches ? "" : " fresh";
}

function updateArena(s) {
  if (s.rank) { updateTrack(s); updateClimb(s.rank.data); }
  if (s.assessment && !A.graded) {
    A.graded = true;
    const g = $("#grades");
    g.innerHTML = s.assessment.html;
    g.querySelectorAll(".card").forEach((c, i) => c.style.setProperty("--i", i));
    if (!calm.matches) g.classList.add("reveal");
    $("#arena").classList.add("rewards");
  }
}

// The league track: one node per league, left to right. The token walks along the rail while the
// league's opponents are being played, and the node pops when the league is cleared or cracks
// when the deck is stopped there.
function buildNodes(pools, deck) {
  const lane = $("#track .lane"), tok = lane.querySelector(".token");
  lane.querySelectorAll(".node").forEach(x => x.remove());
  lane.style.setProperty("--n", Math.max(1, pools.length));
  pools.forEach((p, i) => {
    const r = rankList.find(x => x.key === p.key) || {};
    const el = document.createElement("div");
    el.className = "node locked"; el.dataset.key = p.key;
    el.innerHTML = `<span class="node-number">${String(i + 1).padStart(2, "0")}</span>${r.emblem || `<i class="gem rk-${esc(p.key)}"></i>`}<span class="nm">${esc(p.label)}</span><span class="st"></span>`;
    lane.appendChild(el);
  });
  tok.firstChild.textContent = (deck || "?").trim().charAt(0).toUpperCase() || "?";
  tok.title = deck || "";
  tok.style.left = ((-.4 + .5) / Math.max(1, pools.length) * 100).toFixed(2) + "%";
}

// Seal the deck token locally: the loadout is hidden once the arena opens.
// `keys` are the leagues about to be played, low to high.
function lockIn(keys, name) {
  Fx.play("lock");
  const list = rankList.filter(r => keys.includes(r.key));
  buildNodes(list.map(r => ({key: r.key, label: r.name})), name);
  replay($("#track .token"), "seal");
}

function updateTrack(s) {
  const d = s.rank.data, pools = d.pools, n = pools.length, gpo = s.games_per_opponent || 1;
  const tr = $("#track"), lane = tr.querySelector(".lane"), tok = lane.querySelector(".token");
  if (!n) return;
  if ([...lane.querySelectorAll(".node")].map(el => el.dataset.key).join() !== pools.map(p => p.key).join()) buildNodes(pools, d.deck);
  const finished = d.status === "done";
  const odds = p => d.opponents.filter(o => o.pool === p.key);
  const prog = pools.map(p => p.done ? 1 : Math.min(.92, odds(p).reduce((a, o) => a + o.games, 0) / Math.max(1, odds(p).length * gpo)));
  let cur = pools.findIndex(p => !p.done), pos;
  // Once a ladder run is over, the token ends on the league of the final rank, the same rank the
  // climb panel shows. Leagues above it whose matches were won stay marked as such, not as ranks.
  const lastCleared = pools.reduce((a, p, i) => p.done && p.cleared === true ? i : a, -1);
  const finalIdx = finished && d.ladder ? pools.findIndex(p => p.key === d.rank.toLowerCase()) : -1;
  const atRank = finalIdx >= 0 && finalIdx <= lastCleared;
  if (finished || cur < 0) {
    cur = -1;
    const last = pools.reduce((a, p, i) => p.done ? i : a, -1);
    pos = atRank ? finalIdx : last < 0 ? -.4 : pools[last].cleared === false ? last - .4 : last;
  } else {
    const prev = cur > 0 ? cur - 1 : -.4;
    pos = prev + prog[cur] * (cur - prev);
  }
  const left = ((pos + .5) / n * 100).toFixed(2) + "%";
  if (tok.style.left && tok.style.left !== left && !calm.matches) {  // a footprint where the token was
    const t = document.createElement("u");
    t.className = "trail"; t.style.left = tok.style.left;
    lane.appendChild(t); later(900, () => t.remove());
  }
  tok.style.left = left;
  tok.classList.toggle("rest", finished);
  lane.querySelector(".rail > i").style.width = Math.max(0, Math.min(100, pos / Math.max(1, n - 1) * 100)).toFixed(1) + "%";
  const nodes = [...lane.querySelectorAll(".node")];
  pools.forEach((p, i) => {
    const el = nodes[i];
    let st = p.done ? (p.cleared === true ? "cleared" : p.cleared === false ? "failed" : "played") : i === cur ? "current" : "locked";
    if (atRank && st === "cleared") st = i === finalIdx ? "final" : i > finalIdx ? "beat" : st;
    if (A.track[p.key] !== st) {
      const before = A.track[p.key];
      A.track[p.key] = st;
      el.className = "node " + st;
      el.querySelector(".st").textContent = {cleared: "Cleared", failed: "Stopped", played: "Played", current: "In play", locked: "", final: "Final rank", beat: "Matches won"}[st];
      if (st === "cleared" || st === "played" || st === "final") burst(el, tr, st === "final" ? `Final rank · ${p.label}` : st === "cleared" ? `${p.label} cleared` : `${p.label} played`, false);
      else if (st === "failed") burst(el, tr, `Stopped at ${p.label}`, true);
      void before;
    }
  });
  // the opponents in the league being played (or the last one, once the run is over)
  const focus = cur >= 0 ? pools[cur] : [...pools].reverse().find(p => p.done);
  const duels = $("#duels");
  const focused = focus ? odds(focus) : [];
  const names = new Set(focused.map(o => o.name));
  for (const [name, el] of Object.entries(A.duels)) if (!names.has(name)) { el.remove(); delete A.duels[name]; }
  focused.forEach(o => {
    let el = A.duels[o.name];
    if (!el) {
      el = A.duels[o.name] = document.createElement("div");
      el.innerHTML = `<i></i><span></span><b></b>`;
      el.querySelector("span").textContent = oppName(o.name);
      duels.appendChild(el);
    }
    const decided = focus.done || o.games >= gpo;
    const cls = o.games === 0 ? "" : !decided ? "live" : o.win_rate >= passRate ? "win" : "loss";
    el.className = "duel " + cls;
    el.querySelector("b").textContent = o.games ? `${Math.round(100 * o.win_rate)}% · ${o.games}/${gpo}` : "Waiting";
    el.title = `${oppName(o.name)}: ${o.games} games, ${cls === "win" ? "threshold met" : cls === "loss" ? "below threshold" : cls === "live" ? "in progress" : "waiting"}`;
  });
  const wrap = tr.querySelector(".wrap"), cx = (pos + .5) / n * lane.offsetWidth;
  if (lane.offsetWidth > wrap.clientWidth && Math.abs(cx - wrap.clientWidth / 2 - wrap.scrollLeft) > wrap.clientWidth / 4)
    wrap.scrollTo({left: Math.max(0, cx - wrap.clientWidth / 2), behavior: calm.matches ? "auto" : "smooth"});
}

function burst(node, tr, text, bad) {
  if (A.quiet) return;
  Fx.play(bad ? "failed" : /^Final/.test(text) ? "final" : "cleared");
  if (calm.matches) return;
  if (bad) replay(node, "crack");
  else {
    replay(node, "pop");
    for (let i = 0; i < 10; i++) {
      const b = document.createElement("b");
      b.className = "sp"; b.style.setProperty("--a", (i * 36) + "deg"); b.style.setProperty("--distance", (24 + (i % 3) * 12) + "px");
      node.appendChild(b); later(1000, () => b.remove());
    }
  }
  const c = tr.querySelector(".callout");
  c.textContent = text; c.classList.toggle("bad", !!bad); replay(c, "show");
}

function updateClimb(d) {
  $("#arena").classList.remove("pre");
  const c = $("#climb"), idx = d.ranks.findIndex(r => r.name === d.rank);
  c.querySelector(".overline").textContent = d.status === "done" ? "FINAL RATING" : "CURRENT RATING";
  const info = rankList.find(r => r.name === d.rank) || {};
  const nxt = d.ranks[idx + 1], floor = d.ranks[idx].floor;
  const pct = nxt ? Math.max(0, Math.min(100, (d.mmr - floor) / (nxt.floor - floor) * 100)) : 100;
  const bar = c.querySelector(".xp > i");
  const changed = A.rank !== null && idx !== A.rank;
  c.style.setProperty("--rc", d.rank_color);
  if (A.rank === null || changed) {
    c.querySelector(".spin").innerHTML = info.emblem || `<i class="gem rk-${esc(d.rank.toLowerCase())}"></i>`;
    c.querySelector(".rk").textContent = d.rank;
  }
  bar.style.width = pct + "%";
  c.querySelector(".xp").setAttribute("aria-valuenow", String(Math.round(pct)));
  c.querySelector(".xp").setAttribute("aria-valuetext", nxt ? `${d.to_next} MMR to ${nxt.name}` : "Top rank");
  if (changed) {
    const up = idx > A.rank;
    if (!A.quiet) Fx.play(up ? "promote" : "demote");
    c.classList.remove("up", "down");
    replay(c, up ? "up" : "down");
    const b = c.querySelector(".banner");
    b.textContent = up ? `Rank up · ${d.rank}` : `Rating adjusted · ${d.rank}`;
    b.classList.toggle("down", !up);
    replay(b, "show");
  }
  A.rank = idx;

  tweenMMR(d.mmr);
  c.querySelector(".sub").textContent = `${nxt ? `${d.to_next} MMR to ${nxt.name}` : "Top rank"} · peak ${d.peak} · ${d.games} games`;
  const cur = d.current;
  c.querySelector(".live").textContent = d.status === "running" && cur ? `Now playing ${oppName(cur.opponent)} · ${cur.games}/${cur.total}` : "";
  if (d.status === "done" && !A.final) {
    A.final = true;
    c.classList.add("final");
    const b = c.querySelector(".banner");
    later(changed ? 1400 : 0, () => { b.textContent = `Final rank · ${d.rank}`; b.classList.remove("down"); replay(b, "show"); });
  }
  updateScore(d);
  updateTicker(d);
}

function tweenMMR(to) {
  const n = $("#climb .mmrv .n"), dEl = $("#climb .mmrv .d");
  if (A.mmr === to) return;
  if (A.frame) cancelAnimationFrame(A.frame);
  const previous = A.mmr, from = A.displayedMMR ?? to;
  A.mmr = to;
  if (previous !== null && previous !== to) {
    const diff = to - previous;
    dEl.textContent = (diff > 0 ? "+" : "") + diff;
    dEl.className = "d " + (diff > 0 ? "pos" : "neg");
    replay(dEl, "show");
  }
  if (previous === null || calm.matches) { n.textContent = `${to} MMR`; A.displayedMMR = to; return; }
  const t0 = performance.now(), run = A;
  const step = t => {
    if (A !== run) return;
    const k = Math.min(1, (t - t0) / 650), e = 1 - Math.pow(1 - k, 4);
    A.displayedMMR = from + (to - from) * e;
    n.textContent = `${Math.round(A.displayedMMR)} MMR`;
    if (k < 1) A.frame = requestAnimationFrame(step);
  };
  A.frame = requestAnimationFrame(step);
}

function updateScore(d) {
  const totals = d.opponents.reduce((a, o) => ({wins: a.wins + o.wins, losses: a.losses + o.games - o.wins - o.draws, draws: a.draws + o.draws}), {wins: 0, losses: 0, draws: 0});
  const entries = [["wins", "#winCount"], ["losses", "#lossCount"], ["draws", "#drawCount"]];
  const changes = [];
  for (const [key, selector] of entries) {
    const el = $(selector), diff = totals[key] - A.totals[key];
    el.textContent = totals[key].toLocaleString();
    if (diff > 0) { replay(el, "count-up"); changes.push(`+${diff} ${key}`); }
  }
  const games = totals.wins + totals.losses + totals.draws;
  $("#scoreCount").textContent = games ? `${Math.round(100 * (totals.wins + totals.draws * .5) / games)}%` : "—";
  if (changes.length) {
    const el = $(".batch-update");
    el.textContent = `Latest batch · ${changes.join(" · ")}`;
    replay(el, "arrive");
  }
  A.totals = totals;
}

// New games since the last poll, as win / draw / loss pips. Games come back in chunks, so the
// order inside one poll is spread evenly rather than the true game order.
function spread(w, dr, l) {
  const out = [], n = w + dr + l, want = {w, d: dr, l}, got = {w: 0, d: 0, l: 0};
  for (let i = 1; i <= n; i++) {
    const k = ["w", "d", "l"].reduce((best, x) => want[x] * i / n - got[x] > want[best] * i / n - got[best] ? x : best, "w");
    got[k]++; out.push(k);
  }
  return out;
}

const MAX_PIPS = 48;
function updateTicker(d) {
  const box = $("#ticks");
  const oldRects = new Map([...box.children].map(el => [el, el.getBoundingClientRect()]));
  for (const o of d.opponents) {
    const prev = A.opps[o.name] || {games: 0, wins: 0, draws: 0};
    if (o.games <= prev.games) continue;
    const dw = o.wins - prev.wins, dd = o.draws - prev.draws, dl = o.games - prev.games - dw - dd;
    A.opps[o.name] = {games: o.games, wins: o.wins, draws: o.draws};
    let row = A.rows[o.name];
    if (!row) {
      row = A.rows[o.name] = document.createElement("div");
      row.className = "row";
      row.innerHTML = `<span class="nm"><i class="gem rk-${esc(o.pool)}"></i>${esc(oppName(o.name))}</span><span class="tl"></span><div class="strip"></div>`;
      box.prepend(row);
    }
    const losses = o.games - o.wins - o.draws;
    row.querySelector(".tl").innerHTML = `<b>${o.wins}</b>–${losses}${o.draws ? "–" + o.draws : ""} · ${Math.round(100 * o.win_rate)}%`;
    const strip = row.querySelector(".strip"), pips = spread(dw, dd, dl);
    const gap = Math.min(40, 700 / pips.length);
    pips.slice(-MAX_PIPS).forEach((k, i) => {
      const u = document.createElement("u");
      u.className = k;
      u.textContent = {w: "✓", d: "−", l: "×"}[k];
      u.title = {w: "win", d: "draw", l: "loss"}[k];
      u.style.animationDelay = (calm.matches ? 0 : i * gap).toFixed(0) + "ms";
      strip.appendChild(u);
    });
    while (strip.children.length > MAX_PIPS) strip.firstChild.remove();
  }
  for (const p of d.pools) {
    if (!p.done || A.pools.has(p.key)) continue;
    A.pools.add(p.key);
    const ev = document.createElement("div"), rate = p.rate == null ? "" : ` · ${Math.round(100 * p.rate)}%`;
    ev.className = "ev " + (p.cleared == null ? "na" : p.cleared ? "ok" : "no");
    ev.textContent = `${p.label} pool ${p.cleared == null ? "played" : p.cleared ? "cleared" : "failed"}${rate}`;
    box.prepend(ev);
  }
  // Animate only rows displaced by a new result; unchanged rows keep their DOM and focus.
  if (!calm.matches) for (const [el, rect] of oldRects) {
    const dy = rect.top - el.getBoundingClientRect().top;
    if (dy && el.animate) el.animate([{transform: `translateY(${dy}px)`}, {transform: "translateY(0)"}], {duration: 380, easing: "cubic-bezier(.22,1,.36,1)"});
  }

}

// -- replaying a saved ladder run: the same walk, rebuilt from the run's own numbers -----------
// `d` is the saved tracker (pools, opponents, MMR history). Each step is a snapshot as the live
// page would have seen it part-way through, fed to the same functions the live run uses.
function replaySteps(d, per = 2) {
  const hist = d.history && d.history.length ? d.history : [[0, 1000]];
  const mmrAt = n => hist.reduce((m, [g, v]) => g <= n ? v : m, hist[0][1]);
  const ranks = d.ranks, rankAt = m => [...ranks].reverse().find(r => m >= r.floor) || ranks[0];
  const opps = d.opponents.map(o => ({...o, games: 0, wins: 0, draws: 0, win_rate: null}));
  const pools = d.pools.map(p => ({...p, done: false, cleared: null, games: 0, rate: null}));
  const steps = [];
  let played = 0, peak = hist[0][1];
  d.pools.forEach((p, pi) => {
    opps.forEach((o, oi) => {
      const src = d.opponents[oi];
      if (o.pool !== p.key || !src.games) return;
      // Use one consistent outcome sequence for every prefix. Rounding wins and draws
      // independently can produce more outcomes than games (and scores above 100%).
      const outcomes = spread(src.wins, src.draws, src.games - src.wins - src.draws);
      for (let k = 1; k <= per; k++) {
        const g = Math.round(src.games * k / per);
        if (g <= o.games) continue;
        const prefix = outcomes.slice(0, g);
        const wins = prefix.filter(x => x === "w").length, draws = prefix.filter(x => x === "d").length;
        played += g - o.games;
        Object.assign(o, {games: g, wins, draws, win_rate: (wins + .5 * draws) / g});
        const m = mmrAt(played), r = rankAt(m), nxt = ranks[ranks.indexOf(r) + 1];
        peak = Math.max(peak, m);
        steps.push({...d, status: "running", pools: pools.map(x => ({...x})), opponents: opps.map(x => ({...x})),
          mmr: Math.round(m), peak: Math.round(peak), rank: r.name, rank_color: r.color, next_rank: nxt ? nxt.name : null,
          to_next: nxt ? Math.round(nxt.floor - m) : null, games: played,
          current: {opponent: o.name, games: g, total: src.games, win_rate: o.win_rate}});
      }
    });
    if (d.pools[pi].done) pools[pi] = {...d.pools[pi]};
    if (steps.length) steps[steps.length - 1].pools = pools.map(x => ({...x}));
  });
  steps.push(d);
  return steps;
}

let replayTimer = null;
function showReplay(d, {play = true, ms = 300} = {}) {
  clearTimeout(replayTimer);
  const host = $("#rp-host");
  resetArena();
  host.innerHTML = arenaHTML();
  const gpo = Math.max(1, ...d.opponents.map(o => o.games));
  const feed = st => updateArena({rank: {data: st}, games_per_opponent: gpo});
  buildNodes(d.pools, d.deck);
  const tok = $("#track .token");
  if (!play) {  // just the finished picture
    A.quiet = true; feed(d); A.quiet = false;
    return;
  }
  Fx.wake();
  const steps = replaySteps(d);
  tok.classList.add("unsealed");
  let i = 0;
  const tick = () => {
    feed(steps[i++]);
    if (i < steps.length) replayTimer = setTimeout(tick, ms);
  };
  later(calm.matches ? 0 : 450, () => {
    tok.classList.remove("unsealed"); replay(tok, "seal");
    const c = $("#track .callout");
    c.textContent = "Deck locked in"; c.classList.remove("bad"); replay(c, "show");
    Fx.play("lock");
    replayTimer = setTimeout(tick, calm.matches ? 0 : 900);
  });
}

async function initReplay() {
  const data = JSON.parse($("#run-data").textContent);
  try { rankList = (await (await fetch("/api/tiers")).json()).ranks || []; } catch (e) {}
  Fx.bind($("#fx"));
  $("#rp-play").onclick = () => showReplay(data);
  $("#rp-skip").onclick = () => showReplay(data, {play: false});
  showReplay(data, {play: false});
  if (new URLSearchParams(location.search).get("replay")) {
    $("#rp-host").scrollIntoView({block: "center"});
    showReplay(data);
  }
}
