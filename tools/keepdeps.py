"""Some responses from the asset API leave out `dependent_abilities` (the link from an ultimate or ability to the abilities it swaps in,
which hero pages use for Silver's Lycan Curse and similar forms). When an item had it in the previous snapshot and the new
download doesn't, carry the old value over so the feature doesn't silently vanish.  usage: keepdeps.py PREV_DIR DATA_DIR"""
import json, os, sys
prev, data = sys.argv[1], sys.argv[2]
try:
    old = json.load(open(os.path.join(prev, "items.json")))
    path = os.path.join(data, "items.json"); new = json.load(open(path))
except Exception as e:
    print("keepdeps: skipped (%s)" % e); sys.exit(0)
oldby = {i.get("class_name"): i for i in old if isinstance(i, dict)}
n = 0
for i in new:
    o = oldby.get(i.get("class_name"))
    if isinstance(i, dict) and o and o.get("dependent_abilities") and not i.get("dependent_abilities"):
        i["dependent_abilities"] = o["dependent_abilities"]; n += 1
if n:
    json.dump(new, open(path, "w"), ensure_ascii=False, separators=(",", ":"))
print("keepdeps: restored dependent_abilities on %d item(s)" % n)
