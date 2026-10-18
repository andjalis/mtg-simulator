"""The live close-up follows opponent pools independently of MMR rank."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "Node.js needed for browser JavaScript regression")
class PoolFocusTests(unittest.TestCase):
    def test_pool_selection_progress_and_score(self):
        script = r'''
const vm = require('vm'), fs = require('fs'), assert = require('assert');
const ctx = {document:{},matchMedia:()=>({matches:true})};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('web/static/arena.js','utf8'),ctx);
const d = {status:'running',rank:'Silver',mmr:1067,pools:[
  {key:'bronze',label:'Bronze',done:true,rate:.7},
  {key:'gold',label:'Gold',done:false},
  {key:'platinum',label:'Platinum',done:false}],opponents:[
  {name:'bronze/a',pool:'bronze',games:20,total:20,wins:14,draws:0},
  {name:'gold/a',pool:'gold',games:20,total:20,wins:20,draws:0},
  {name:'gold/b',pool:'gold',games:100,total:100,wins:0,draws:0},
  {name:'gold/c',pool:'gold',games:0,total:100,wins:0,draws:0},
  {name:'platinum/a',pool:'platinum',games:0,total:100,wins:0,draws:0}]};
const live = ctx.poolFocusData(d,null,100);
assert.equal(live.pool.key,'gold'); // a Silver MMR must not move the view away from Gold
assert.equal(live.games,120);
assert.equal(live.completed,2); // early-stopped 20/20 matchup is finished
assert.equal(live.score,.5); // same equal-matchup weighting as the pool clearance rule
assert.equal(live.opponents[1].losses,100);
const review = ctx.poolFocusData(d,'bronze',100);
assert.equal(review.pool.key,'bronze'); assert.equal(review.live.key,'gold');
assert.equal(review.score,.7);
const future = ctx.poolFocusData(d,'platinum',100);
assert.equal(future.score,null); assert.equal(future.completed,0);
assert.equal(ctx.poolFocusData(d,'missing',100).pool.key,'gold');
const advanced = {...d,pools:d.pools.map(p=>({...p,done:p.key!=='platinum'}))};
assert.equal(ctx.activePool(advanced).key,'platinum');
const done = {...advanced,status:'done'};
assert.equal(ctx.activePool(done).key,'gold');
assert.equal(ctx.poolFocusData({...d,pools:[],opponents:[]},null),null);
const html = ctx.arenaHTML();
assert(html.includes('POOL CLOSE-UP'));
assert(!html.includes('LIVE RATING') && !html.includes('MMR estimate'));
'''
        result = subprocess.run([shutil.which("node"), "-e", script],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
