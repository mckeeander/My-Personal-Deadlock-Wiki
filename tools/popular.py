#!/usr/bin/env python3
"""What top-ranked players buy on each hero, from the Deadlock API's match statistics, into data/popular.json.

For every hero: each shop item's pick rate (share of that hero's matches it was bought in) and its average buy time,
over the last 30 days, in matches whose average rank is in roughly the top 5% (worked out each run from the API's
rank distribution). The app files them as early (bought before 10 min), mid (10-20) and late (20+).

Run:  python3 tools/popular.py        (about 46 requests; the API allows 200 a minute)
"""
import json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
API = "https://api.deadlock-api.com/v1"
TOP = 0.05  # the share of matches to keep, by average rank
KEEP = 10   # items kept per hero for each phase (early, mid, late); the app shows six, after dropping parts of items already shown


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
    items = {i["id"]: i for i in load("items.json") if i.get("id") and i.get("type") == "upgrade"}

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
        rows = []
        for x in get("/analytics/item-stats%s&hero_id=%d&min_matches=20" % (q, h["id"])):
            it = items.get(x["item_id"])
            if not it or not x.get("matches"): continue
            rows.append({"c": it["class_name"], "p": round(x["matches"] / n, 4), "t": round(x.get("avg_buy_time_s") or 0)})
        rows.sort(key=lambda r: -r["p"])
        ph = lambda r: 0 if r["t"] < 600 else 1 if r["t"] < 1200 else 2  # early, mid, late: the app's three sections
        out[h["class_name"]] = {"matches": n, "items": [r for k in range(3) for r in [x for x in rows if ph(x) == k][:KEEP]]}
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
