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

// -- animations: the live climb, the match ticker and the grade reveal ------------------------
// The run is polled, so each poll is compared with the last one: new games become pips, a
// change of rank flips the badge, and the grades flip over once when they first arrive.
let A = {};
function resetArena() {
  A = {track: {}, rank: null, mmr: null, opps: {}, pools: new Set(), stamped: new Set(), graded: false, final: false, rows: {}};
}
// The track, the climb panel and the match ticker: shared by the deck page and the replay page.
function arenaHTML() {
  return `<div class="arena pre" id="arena">
      <div class="track" id="track"><div class="callout"></div><div class="wrap"><div class="lane"><div class="rail"><i></i></div><div class="token"><b></b></div></div></div>
        <div class="duels" id="duels"></div></div>
      <div class="climb" id="climb"><div class="badge"><div class="spin"></div></div>
        <div><div class="rk"></div><div class="mmrv"><span class="n"></span><span class="d"></span></div>
        <div class="xp"><i></i></div><div class="sub"></div><div class="live"></div></div>
        <div class="banner"></div></div>
      <div class="ticker"><h3>Match ticker</h3><div class="rows" id="ticks" aria-live="off"></div></div>
    </div>`;
}
const later = (ms, fn) => calm.matches ? fn() : setTimeout(fn, ms);
const replay = (el, cls) => { el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls); };
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
  }
}

// The league track: one node per league, left to right. The token walks along the rail while the
// league's opponents are being played, and the node pops when the league is cleared or cracks
// when the deck is stopped there.
function buildNodes(pools, deck) {
  const lane = $("#track .lane"), tok = lane.querySelector(".token");
  lane.querySelectorAll(".node").forEach(x => x.remove());
  lane.style.setProperty("--n", pools.length);
  pools.forEach(p => {
    const r = rankList.find(x => x.key === p.key) || {};
    const el = document.createElement("div");
    el.className = "node locked"; el.dataset.key = p.key;
    el.innerHTML = `${r.emblem || `<i class="gem rk-${esc(p.key)}"></i>`}<span class="nm">${esc(p.label)}</span><span class="st"></span>`;
    lane.appendChild(el);
  });
  tok.firstChild.textContent = (deck || "?").trim().charAt(0).toUpperCase() || "?";
  tok.title = deck || "";
  tok.style.left = ((-.4 + .5) / pools.length * 100).toFixed(2) + "%";
}

// Locking the deck in: the decklist lifts off as a card, flies onto the track and seals into the
// token that then walks the leagues. `keys` are the leagues about to be played, low to high.
function lockIn(keys, name) {
  Fx.wake(); Fx.play("lock");
  const list = rankList.filter(r => keys.includes(r.key));
  buildNodes(list.map(r => ({key: r.key, label: r.name})), name);
  const tok = $("#track .token"), src = $("#deck");
  if (calm.matches || !src.animate) return;
  tok.classList.add("unsealed");
  const a = src.getBoundingClientRect(), t = tok.getBoundingClientRect();
  tok.closest(".track").scrollIntoView({block: "nearest", behavior: "smooth"});
  const card = document.createElement("div");
  card.className = "lockcard";
  card.innerHTML = `<b>${esc(name || "my deck")}</b><span>Locking in…</span>`;
  Object.assign(card.style, {left: a.left + "px", top: a.top + "px", width: a.width + "px", height: Math.min(a.height, 220) + "px"});
  document.body.appendChild(card);
  src.classList.add("locked"); setTimeout(() => src.classList.remove("locked"), 1800);
  const done = () => {
    card.remove();
    const now = tok.getBoundingClientRect();
    tok.classList.remove("unsealed"); replay(tok, "seal");
    const c = $("#track .callout");
    c.textContent = "Deck locked in"; c.classList.remove("bad"); replay(c, "show");
    void now;
  };
  // the track may have scrolled into view meanwhile, so aim at where the token is when we land
  setTimeout(() => {
    const t2 = tok.getBoundingClientRect(), cx = t2.left + t2.width / 2, cy = t2.top + t2.height / 2;
    const h = parseFloat(card.style.height);
    const anim = card.animate([
      {transform: "none", opacity: 1, borderRadius: "16px"},
      {transform: `translate(${(cx - a.left - a.width / 2) * .5}px, ${(cy - a.top - h / 2) * .5 - 50}px) scale(.45) rotate(-5deg)`, opacity: 1, offset: .55},
      {transform: `translate(${cx - a.left - a.width / 2}px, ${cy - a.top - h / 2}px) scale(${34 / a.width}, ${34 / h}) rotate(0deg)`, opacity: .9, borderRadius: "50%"},
    ], {duration: 850, easing: "cubic-bezier(.5,0,.2,1)", fill: "forwards"});
    anim.onfinish = done;
    setTimeout(() => { if (card.isConnected) done(); }, 1600);
  }, 250);
}

function updateTrack(s) {
  const d = s.rank.data, pools = d.pools, n = pools.length, gpo = s.games_per_opponent || 1;
  const tr = $("#track"), lane = tr.querySelector(".lane"), tok = lane.querySelector(".token");
  if (lane.querySelectorAll(".node").length !== n) buildNodes(pools, d.deck);
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
    lane.appendChild(t); setTimeout(() => t.remove(), 1300);
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
  if (!focus) { duels.innerHTML = ""; }
  else {
    duels.innerHTML = odds(focus).map(o => {
      const decided = focus.done || o.games >= gpo;
      const cls = o.games === 0 ? "" : !decided ? "live" : o.win_rate >= passRate ? "win" : "loss";
      return `<span class="duel ${cls}" title="${esc(oppName(o.name))}"><i></i>${esc(oppName(o.name))}</span>`;
    }).join("");
  }
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
      b.className = "sp"; b.style.setProperty("--a", (i * 36) + "deg");
      node.appendChild(b); setTimeout(() => b.remove(), 1000);
    }
  }
  const c = tr.querySelector(".callout");
  c.textContent = text; c.classList.toggle("bad", !!bad); replay(c, "show");
}

function updateClimb(d) {
  $("#arena").classList.remove("pre");
  const c = $("#climb"), idx = d.ranks.findIndex(r => r.name === d.rank);
  const info = rankList.find(r => r.name === d.rank) || {};
  const nxt = d.ranks[idx + 1], floor = d.ranks[idx].floor;
  const pct = nxt ? Math.max(0, Math.min(100, (d.mmr - floor) / (nxt.floor - floor) * 100)) : 100;
  const bar = c.querySelector(".xp > i");
  const paint = () => {
    c.style.setProperty("--rc", d.rank_color);
    c.querySelector(".spin").innerHTML = info.emblem || `<i class="gem rk-${esc(d.rank.toLowerCase())}"></i>`;
    c.querySelector(".rk").textContent = d.rank;
  };
  if (A.rank === null) { paint(); bar.style.width = pct + "%"; }
  else if (idx !== A.rank) {
    const up = idx > A.rank;
    if (!A.quiet) Fx.play(up ? "promote" : "demote");
    c.classList.remove("up", "down");
    replay(c, up ? "up" : "down");
    later(up ? 300 : 280, paint);                         // swap the badge while it is edge-on
    bar.style.width = up ? "100%" : "0%";                 // finish (or empty) the old bar first
    later(450, () => {
      bar.style.transition = "none"; bar.style.width = up ? "0%" : "100%"; void bar.offsetWidth;
      bar.style.transition = ""; bar.style.width = pct + "%";
    });
    const b = c.querySelector(".banner");
    b.textContent = up ? `Promoted · ${d.rank}` : `Demoted · ${d.rank}`;
    b.classList.toggle("down", !up);
    replay(b, "show");
  } else bar.style.width = pct + "%";
  A.rank = idx;

  tweenMMR(d.mmr);
  c.querySelector(".sub").textContent = `${nxt ? `${d.to_next} MMR to ${nxt.name}` : "Top rank"} · peak ${d.peak} · ${d.games} games`;
  const cur = d.current;
  c.querySelector(".live").textContent = d.status === "running" && cur ? `Now playing ${oppName(cur.opponent)} · ${cur.games}/${cur.total}` : "";
  if (d.status === "done" && !A.final) {
    A.final = true;
    c.classList.add("final");
    const b = c.querySelector(".banner");
    later(A.mmr === null ? 0 : 900, () => { b.textContent = `Final rank · ${d.rank}`; b.classList.remove("down"); replay(b, "show"); });
  }
  updateTicker(d);
}

function tweenMMR(to) {
  const n = $("#climb .mmrv .n"), dEl = $("#climb .mmrv .d"), from = A.mmr;
  A.mmr = to;
  if (from === null || from === to || calm.matches) { n.textContent = `${to} MMR`; return; }
  const diff = to - from;
  dEl.textContent = (diff > 0 ? "+" : "") + diff;
  dEl.className = "d " + (diff > 0 ? "pos" : "neg");
  replay(dEl, "show");
  const t0 = performance.now(), dur = 550;
  const step = t => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    n.textContent = `${Math.round(from + diff * e)} MMR`;
    if (k < 1 && A.mmr === to) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
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
      u.title = {w: "win", d: "draw", l: "loss"}[k];
      u.style.animationDelay = (i * gap).toFixed(0) + "ms";
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
      for (let k = 1; k <= per; k++) {
        const g = Math.round(src.games * k / per), wins = Math.round(src.wins * k / per), draws = Math.round(src.draws * k / per);
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
