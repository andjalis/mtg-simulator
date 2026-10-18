"""Live estimates must not masquerade as opponent-pool progression."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "Node.js needed for browser JavaScript regression")
class LiveRatingTests(unittest.TestCase):
    def test_named_rank_is_only_revealed_after_completion(self):
        script = r'''
const vm = require('vm'), fs = require('fs'), assert = require('assert');
const fields = new Map();
const element = name => {
  if (!fields.has(name)) fields.set(name, {textContent:'', innerHTML:'', hidden:false,
    style:{setProperty(){}}, classList:{add(){},remove(){},toggle(){}}, setAttribute(){}});
  return fields.get(name);
};
const climb = {querySelector: element, style:{setProperty(){}}, classList:{add(){},remove(){}}};
const context = {document:{querySelector:s=>s==='#climb'?climb:element(s)},
  matchMedia:()=>({matches:true})};
vm.createContext(context);
vm.runInContext(fs.readFileSync('web/static/arena.js','utf8'),context);
vm.runInContext('resetArena(); tweenMMR=()=>{}; updateScore=()=>{}; updateTicker=()=>{};',context);
const data = {status:'running',rank:'Silver',rank_color:'#aaa',mmr:1067,peak:1146,
  games:270,to_next:133,current:null,ranks:[{name:'Bronze',floor:0},{name:'Silver',floor:1000},{name:'Gold',floor:1200}]};
context.updateClimb(data);
assert.equal(element('.overline').textContent,'LIVE RATING');
assert.equal(element('.rk').textContent,'MMR estimate');
assert(!element('.spin').innerHTML.includes('rk-silver'));
assert(element('.xp').hidden);
assert(!element('.sub').textContent.includes('Gold'));
context.updateClimb({...data,status:'done'});
assert.equal(element('.overline').textContent,'FINAL MMR RANK');
assert.equal(element('.rk').textContent,'Silver');
assert(element('.spin').innerHTML.includes('rk-silver'));
assert(!element('.xp').hidden);
'''
        result = subprocess.run([shutil.which("node"), "-e", script],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
