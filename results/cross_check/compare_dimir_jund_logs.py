"""Compare Forge worker logs (from mtgsim.forge.run_forge_match(log_dir=...)) with built-in games of
Dimir Control vs Jund Sacrifice: cards cast per game, game length, wins. Paths are hard-coded."""
import re, glob, collections, sys
sys.path.insert(0, "/home/user/mtg-simulator")
# Forge side
games=[]; cur=None
for f in sorted(glob.glob("/tmp/claude-0/forge_logs/worker-*.log")):
    for line in open(f, errors="replace"):
        m=re.match(r"Turn: Turn (\d+) \(Ai\(\d\)-(\w+)\)", line)
        if m:
            if cur is None: cur={"turns":0,"casts":collections.Counter(),"lands":collections.Counter(),"win":None,"attacks":collections.Counter(), "first":None}
            cur["turns"]=int(m.group(1))
            if cur["first"] is None: cur["first"]=m.group(2)
        if cur is None: continue
        m=re.match(r"Add To Stack: Ai\(\d\)-(\w+) cast (.+)", line)
        if m: cur["casts"][(m.group(1),re.sub(r" targeting.*| \(\d+\).*|\s*\(.*","",m.group(2)).strip())]+=1
        m=re.match(r"Land: Ai\(\d\)-(\w+) played", line)
        if m: cur["lands"][m.group(1)]+=1
        m=re.match(r"Combat: Ai\(\d\)-(\w+) assigned", line)
        if m: cur["attacks"][m.group(1)]+=1
        m=re.match(r"Game Result: .* (\w+)\s*has won|Game Outcome: Ai\(\d\)-(\w+) has won", line)
        m=re.match(r"Game Outcome: Ai\(\d\)-(\w+) has won", line)
        if m: cur["win"]=m.group(1); games.append(cur); cur=None
n=len(games); print("FORGE games",n, collections.Counter(g["win"] for g in games))
print("avg turns", sum(g["turns"] for g in games)/n)
for who in ("dimir_control","jund_sacrifice"):
    print(who, "lands/game %.1f"%(sum(g["lands"][who] for g in games)/n), "attack-assignments/game %.1f"%(sum(g["attacks"][who] for g in games)/n),
          "spells/game %.1f"%(sum(c for g in games for (w,_),c in g["casts"].items() if w==who)/n))
tot=collections.Counter()
for g in games:
    for k,c in g["casts"].items(): tot[k]+=c
for who in ("dimir_control","jund_sacrifice"):
    print(who, [(k[1],round(c/n,2)) for k,c in tot.most_common() if k[0]==who][:14])
# Dimir wins vs losses turns
for w in ("dimir_control","jund_sacrifice"):
    gs=[g for g in games if g["win"]==w]; print("won by",w,len(gs),"avg turns", sum(g["turns"] for g in gs)/max(1,len(gs)))
# our engine
from mtgsim.carddb import CardDB
from mtgsim.decklist import load_deck
from mtgsim.crosscheck import build_deck
from mtgsim.runner import run_match
db=CardDB(offline=True)
a=build_deck(db, load_deck("decks/ranks/6-master/dimir_control.txt")[1]); b=build_deck(db, load_deck("decks/ranks/7-grandmaster/jund_sacrifice.txt")[1])
logs=[]
res,_=run_match("dimir_control",a,"jund_sacrifice",b,games=100,seed=11,log_game=lambda i,l: logs.append([str(x) for x in l]))
print("OURS", res.wins_a, res.wins_b, "logs", len(logs))

og=[]
for lg in logs:
    g={"turns":0,"casts":collections.Counter(),"lands":collections.Counter(),"attacks":collections.Counter(),"win":None}
    for line in lg:
        m=re.match(r"T(\d+) (\w+): (.*)", line)
        if not m: continue
        g["turns"]=int(m.group(1)); w=m.group(2); t=m.group(3)
        if t.startswith("casts "): g["casts"][(w,re.sub(r" \(.*|\s*->.*","",t[6:]).strip())]+=1
        elif t.startswith("plays "): g["lands"][w]+=1
        elif t.startswith("attacks with"): g["attacks"][w]+=len(re.findall(r"\(\d+/\d+\)", t.split("({")[0]))
        elif t.startswith("game over, winner:"): g["win"]=t.split(":")[1].strip()
    og.append(g)
n=len(og); print("OURS games",n, collections.Counter(g["win"] for g in og)); print("avg turns", sum(g["turns"] for g in og)/n)
for who in ("dimir_control","jund_sacrifice"):
    print(who, "lands/game %.1f"%(sum(g["lands"][who] for g in og)/n), "attackers/game %.1f"%(sum(g["attacks"][who] for g in og)/n),
          "spells/game %.1f"%(sum(c for g in og for (w,_),c in g["casts"].items() if w==who)/n))
tot=collections.Counter()
for g in og:
    for k,c in g["casts"].items(): tot[k]+=c
for who in ("dimir_control","jund_sacrifice"):
    print(who, [(k[1],round(c/n,2)) for k,c in tot.most_common() if k[0]==who][:14])
for w in ("dimir_control","jund_sacrifice"):
    gs=[g for g in og if g["win"]==w]; print("won by",w,len(gs),"avg turns", sum(g["turns"] for g in gs)/max(1,len(gs)))

print("---- TABLE per game: forge | ours")
def agg(gs):
    t=collections.Counter()
    for g in gs:
        for k,c in g["casts"].items(): t[k]+=c
    return {k:c/len(gs) for k,c in t.items()}
F=agg(games); O=agg(og)
for who in ("dimir_control","jund_sacrifice"):
    print(who)
    for name in sorted({k[1] for k in list(F)+list(O) if k[0]==who}, key=lambda n:-max(F.get((who,n),0),O.get((who,n),0))):
        print(f"  {name:36s} {F.get((who,name),0):5.2f} | {O.get((who,name),0):5.2f}")
