#!/usr/bin/env python3
"""What top-ranked players buy on each hero, from the Deadlock API's match statistics, into data/popular.json.

For every hero, over the last 30 days, in matches whose average rank is in roughly the top 5% (worked out each run from
the API's rank distribution), each shop item bought in at least MIN_P of the hero's matches, with:
  p   pick rate: the share of the hero's matches it was bought in
  t   average buy time (s)
  s   sell rate: the share of the matches it was bought in where it was later sold (only when SOLD_MIN or more)
  st  average sell time (s), with s
  w   bought together: up to 3 items bought much more often alongside this one than on the hero in general
  im  imbued on: for items imbued into an ability, [[ability class_name, share], ...] of the matches it was imbued in,
      most common first, abilities under IMBUE_MIN left out
The app splits them into a core build (bought in most matches, in buy order) and situational picks.

Run:  python3 tools/popular.py        (three requests per hero; the API allows 200 a minute)
"""
import json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
API = "https://api.deadlock-api.com/v1"
TOP = 0.05  # the share of matches to keep, by average rank
MIN_P = 0.08    # items bought in fewer of the hero's matches than this are left out
MAX_ITEMS = 40  # most items kept per hero
SOLD_MIN = 0.3  # an item counts as usually sold when at least this share of buyers sell it
PAIR_MIN = 0.35 # a partner is listed when at least this share of the item's buyers also buy it...
LIFT_MIN = 1.3  # ...and that's at least this many times its usual rate on the hero
IMBUE_MIN = 0.05  # an ability an item is imbued on in less than this share of its matches is left out


def get(path):
    for n in range(4):
        try:
            req = urllib.request.Request(API + path, headers={"User-Agent": "personal-deadlock-wiki (data update)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            if n == 3: raise
            print("  retry", path, e); time.sleep(2 ** (n + 1))


def load(name):
    d = json.load(open(os.path.join(DATA, name), encoding="utf-8"))
    return d if isinstance(d, list) else d.get(name.split(".")[0], d)


def main():
    heroes = [h for h in load("heroes.json") if h.get("id") and not h.get("disabled") and h.get("player_selectable", True)]
    allitems = load("items.json")
    items = {i["id"]: i for i in allitems if i.get("id") and i.get("type") == "upgrade"}
    abilities = {i["id"]: i for i in allitems if i.get("id") and i.get("type") == "ability"}

    # the lowest rank (badge) at which the matches from there up are still within the top 5%
    dist = sorted(get("/analytics/badge-distribution"), key=lambda x: -x["badge_level"])
    total, run, badge = sum(x["total_matches"] for x in dist), 0, None
    for x in dist:
        run += x["total_matches"]
        if run / total > TOP: break
        badge = x["badge_level"]
    share = sum(x["total_matches"] for x in dist if x["badge_level"] >= badge) / total
    q = "?min_average_badge=%d" % badge
    print("badge %d and up: top %.1f%% of matches" % (badge, share * 100))

    per = {x["hero_id"]: x["matches"] for x in get("/analytics/hero-stats" + q)}
    out = {}
    for h in heroes:
        n = per.get(h["id"])
        if not n: continue
        rows, by_id = [], {}
        for x in get("/analytics/item-stats%s&hero_id=%d&min_matches=20" % (q, h["id"])):
            it = items.get(x["item_id"])
            if not it or not x.get("matches") or x["matches"] / n < MIN_P: continue
            r = {"c": it["class_name"], "p": round(x["matches"] / n, 4), "t": round(x.get("avg_buy_time_s") or 0)}
            sr = (x.get("sold") or 0) / x["matches"]
            if sr >= SOLD_MIN and x.get("avg_sell_time_s"): r["s"] = round(sr, 2); r["st"] = round(x["avg_sell_time_s"])
            rows.append(r); by_id[x["item_id"]] = (r, x["matches"])
        rows.sort(key=lambda r: -r["p"]); rows = rows[:MAX_ITEMS]
        try:  # bought together: pairs of items bought in the same match
            pairs = get("/analytics/item-permutation-stats%s&hero_id=%d&comb_size=2&min_matches=50" % (q, h["id"]))
        except Exception as e:
            pairs = []; print("  pairs failed for %s: %s" % (h.get("name"), e))
        cand = {}
        for pr in pairs:
            ids = pr.get("item_ids") or []
            if len(ids) != 2 or ids[0] not in by_id or ids[1] not in by_id: continue
            for a, b in ((ids[0], ids[1]), (ids[1], ids[0])):
                (ra, na), (rb, _) = by_id[a], by_id[b]
                cond = pr["matches"] / na; lift = cond / rb["p"]
                if cond >= PAIR_MIN and lift >= LIFT_MIN: cand.setdefault(a, []).append((lift, rb["c"]))
        for a, lst in cand.items():
            lst.sort(reverse=True); by_id[a][0]["w"] = [c for _, c in lst[:3]]
        try:  # imbued on: which ability each imbue item was put on
            imb = get("/analytics/item-stats%s&hero_id=%d&bucket=imbued_ability" % (q, h["id"]))
        except Exception as e:
            imb = []; print("  imbues failed for %s: %s" % (h.get("name"), e))
        per_item = {}
        for x in imb:
            ab = abilities.get(x.get("bucket"))
            if ab and x["item_id"] in by_id and x.get("matches"): per_item.setdefault(x["item_id"], []).append((x["matches"], ab["class_name"]))
        for iid, lst in per_item.items():
            tot = sum(m for m, _ in lst); lst.sort(reverse=True)
            keep = [[c, round(m / tot, 3)] for m, c in lst if m / tot >= IMBUE_MIN]
            if keep: by_id[iid][0]["im"] = keep
        out[h["class_name"]] = {"matches": n, "items": rows}
        time.sleep(0.4)
    if not out:
        print("no data; keeping the old file"); return 1
    json.dump({"source": "api.deadlock-api.com (match statistics)", "days": 30, "badge": badge, "share": round(share, 3),
               "updated": time.strftime("%Y-%m-%d"), "heroes": out},
              open(os.path.join(DATA, "popular.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("%d heroes, median %d matches" % (len(out), sorted(v["matches"] for v in out.values())[len(out) // 2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
